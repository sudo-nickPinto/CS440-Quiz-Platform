import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, TypeVar

from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.auth import CurrentAccount
from app.live.protocol import CloseCode, encode
from app.live.snapshot import (
    LiveRole,
    active_participant_count,
    host_results_view,
    open_question_deadlines,
    participant_results_view,
)
from app.schemas.live_question import QuestionClosedEvent
from app.schemas.results import FinalResults, participant_final_view
from app.services.live_questions import answer_progress, close_question_if_ready
from app.services.results import get_closed_question_results
from app.services.session_end import (
    ParticipantLeft,
    abandon_session,
    live_session_ids,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")
DEADLINE_SLACK_SECONDS = 0.25


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(eq=False)
class LiveConnection:
    websocket: WebSocket
    session_id: int
    account: CurrentAccount
    role: LiveRole
    session_participant_id: int | None
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # False until session_state has been sent; nothing else goes out before it.
    ready: bool = False
    # True once the server closed it on purpose (session ended, or left).
    closed: bool = False


class LiveHub:
    """In-memory registry of live sockets for one uvicorn worker (§8.3).

    The database stays the source of truth: every method that changes state
    commits through a service first, and only then sends news to sockets.
    """

    def __init__(self, app: FastAPI):
        self._app = app
        self._sessions: dict[int, dict[int, LiveConnection]] = {}
        self._timers: dict[int, asyncio.Task] = {}
        # When each live session was last seen without a host socket (§5).
        self._host_away_since: dict[int, datetime] = {}
        self._reaper: asyncio.Task | None = None

    # Database -----------------------------------------------------------

    async def run_db(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Run a sync service call with its own short-lived DB session (§8.1)."""

        def call() -> T:
            with self._app.state.database.session_factory() as db:
                return fn(db, *args, **kwargs)

        return await run_in_threadpool(call)

    # Registry -----------------------------------------------------------

    def host_connected(self, session_id: int) -> bool:
        return any(
            conn.role == "host"
            for conn in self._sessions.get(session_id, {}).values()
        )

    async def connect(
        self,
        conn: LiveConnection,
        build_snapshot: Callable[[], Awaitable[BaseModel | dict]],
    ) -> None:
        """Register a socket and send its session_state before anything else.

        The socket's send lock is held from registration until the snapshot is
        on the wire. A broadcast that targets it meanwhile waits on that lock
        (asyncio locks are FIFO), so it is delivered after session_state, in
        order. Nothing called while the lock is held may send to this socket.
        """
        async with conn.send_lock:
            connections = self._sessions.setdefault(conn.session_id, {})
            previous = connections.get(conn.account.account_id)
            connections[conn.account.account_id] = conn
            if previous is not None:
                await self._close(previous, CloseCode.REPLACED, "replaced")
            state = await build_snapshot()
            await conn.websocket.send_text(encode(state))
            conn.ready = True
        if conn.role == "host":
            self._host_away_since.pop(conn.session_id, None)
            await self.broadcast(
                conn.session_id,
                {"type": "host_status", "connected": True},
                role="participant",
            )

    async def disconnect(self, conn: LiveConnection) -> None:
        connections = self._sessions.get(conn.session_id)
        if not connections or connections.get(conn.account.account_id) is not conn:
            return  # already replaced by a newer socket
        del connections[conn.account.account_id]
        if not connections:
            del self._sessions[conn.session_id]
        if conn.role == "host" and not self.host_connected(conn.session_id):
            self._host_away_since[conn.session_id] = _utc_now()
        if conn.role == "host" and conn.ready:
            await self.broadcast(
                conn.session_id,
                {"type": "host_status", "connected": False},
                role="participant",
            )

    # Sending ------------------------------------------------------------

    async def send(self, conn: LiveConnection, payload: BaseModel | dict) -> None:
        try:
            async with conn.send_lock:
                if not conn.ready:
                    return  # snapshot never went out; the socket is closing
                await conn.websocket.send_text(encode(payload))
        except Exception:  # dead socket; its receive loop will clean it up
            logger.debug("Dropped message to a closed socket", exc_info=True)

    async def broadcast(
        self,
        session_id: int,
        payload: BaseModel | dict,
        *,
        role: LiveRole | None = None,
    ) -> None:
        targets = [
            conn
            for conn in list(self._sessions.get(session_id, {}).values())
            if role is None or conn.role == role
        ]
        await asyncio.gather(*(self.send(conn, payload) for conn in targets))

    async def _close(self, conn: LiveConnection, code: int, reason: str) -> None:
        try:
            await conn.websocket.close(code=code, reason=reason)
        except Exception:
            logger.debug("Socket was already closed", exc_info=True)

    # Question lifecycle -------------------------------------------------

    def schedule_deadline(
        self,
        session_id: int,
        session_question_id: int,
        closes_at: datetime,
    ) -> None:
        existing = self._timers.get(session_question_id)
        if existing is not None and not existing.done():
            return
        delay = (closes_at - _utc_now()).total_seconds() + DEADLINE_SLACK_SECONDS
        self._timers[session_question_id] = asyncio.create_task(
            self._deadline(session_id, session_question_id, max(delay, 0))
        )

    async def _deadline(
        self, session_id: int, session_question_id: int, delay: float
    ) -> None:
        try:
            await asyncio.sleep(delay)
            await self.try_close(session_id, session_question_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Deadline close failed for session question %s", session_question_id
            )
        finally:
            if self._timers.get(session_question_id) is asyncio.current_task():
                del self._timers[session_question_id]

    async def participant_joined(
        self,
        session_id: int,
        session_participant_id: int,
        display_name: str,
    ) -> None:
        """Hook run after a committed REST join; tells the host (§4)."""
        try:
            participant_count = await self.run_db(active_participant_count, session_id)
            await self.broadcast(
                session_id,
                {
                    "type": "participant_joined",
                    "session_participant_id": session_participant_id,
                    "display_name": display_name,
                    "participant_count": participant_count,
                },
                role="host",
            )
        except Exception:
            logger.exception("Join hook failed for session %s", session_id)

    async def after_answer(self, session_id: int, session_question_id: int) -> None:
        """Hook run after every committed answer, from WebSocket or REST."""
        try:
            progress = await self.run_db(
                answer_progress, session_id, session_question_id
            )
            await self.broadcast(
                session_id,
                {
                    "type": "answer_progress",
                    "session_question_id": session_question_id,
                    "answered_count": progress.answered_count,
                    "eligible_count": progress.eligible_count,
                },
                role="host",
            )
            await self.try_close(session_id, session_question_id)
        except Exception:
            logger.exception(
                "After-answer hook failed for session question %s",
                session_question_id,
            )

    async def try_close(self, session_id: int, session_question_id: int) -> bool:
        """Close if ready. Only the caller that wins the UPDATE broadcasts (§6)."""
        event = await self.run_db(
            close_question_if_ready, session_id, session_question_id
        )
        if event is None:
            return False
        await self.question_closed(session_id, event)
        return True

    async def question_closed(
        self, session_id: int, event: QuestionClosedEvent
    ) -> None:
        """Broadcast a committed close, then the results (§6).

        Only the caller that won the conditional UPDATE may call this.
        """
        timer = self._timers.pop(event.session_question_id, None)
        if timer is not None and timer is not asyncio.current_task():
            timer.cancel()
        await self.broadcast(session_id, event)
        await self.publish_results(session_id, event.session_question_id)

    async def session_ended(self, session_id: int, results: FinalResults) -> None:
        """Send everyone their final view, then close every socket with 1000."""
        connections = self._sessions.pop(session_id, {})
        self._host_away_since.pop(session_id, None)
        await asyncio.gather(
            *(
                self._finish(
                    conn,
                    {
                        "type": "session_ended",
                        "reason": results.status,
                        **(
                            results.model_dump()
                            if conn.role == "host"
                            else participant_final_view(
                                results, conn.session_participant_id
                            ).model_dump()
                        ),
                    },
                    reason="session_ended",
                )
                for conn in connections.values()
            )
        )

    async def participant_left(self, conn: LiveConnection, left: ParticipantLeft) -> None:
        """Close the leaver's socket, then tell the host (§4)."""
        connections = self._sessions.get(conn.session_id, {})
        if connections.get(conn.account.account_id) is conn:
            del connections[conn.account.account_id]
        await self._finish(conn, None, reason="left")
        await self.broadcast(
            conn.session_id,
            {
                "type": "participant_left",
                "session_participant_id": left.session_participant_id,
                "display_name": left.display_name,
                "participant_count": left.participant_count,
            },
            role="host",
        )

    async def _finish(
        self, conn: LiveConnection, payload: BaseModel | dict | None, *, reason: str
    ) -> None:
        """Send a last message (if any) and close normally, in that order."""
        async with conn.send_lock:
            try:
                if payload is not None and conn.ready:
                    await conn.websocket.send_text(encode(payload))
            except Exception:
                logger.debug("Dropped final message to a closed socket", exc_info=True)
            conn.ready = False
            conn.closed = True
            await self._close(conn, CloseCode.NORMAL, reason)

    async def publish_results(self, session_id: int, session_question_id: int) -> None:
        snapshot = await self.run_db(
            get_closed_question_results, session_id, session_question_id
        )
        connections = list(self._sessions.get(session_id, {}).values())
        await asyncio.gather(
            *(
                self.send(
                    conn,
                    host_results_view(snapshot)
                    if conn.role == "host"
                    else participant_results_view(
                        snapshot, conn.session_participant_id
                    ),
                )
                for conn in connections
            )
        )

    async def sweep(self, session_id: int | None = None) -> None:
        """Close overdue OPEN questions and re-arm timers lost on restart (§6)."""
        now = _utc_now()
        for sid, sqid, closes_at in await self.run_db(
            open_question_deadlines, session_id
        ):
            if closes_at is None:
                continue
            if closes_at <= now:
                await self.try_close(sid, sqid)
            else:
                self.schedule_deadline(sid, sqid, closes_at)

    # Abandoned sessions -------------------------------------------------

    async def reap_abandoned(self, abandon_after_seconds: float) -> None:
        """End every LOBBY/ACTIVE session whose host has been away too long.

        The clock starts when the host socket leaves, or, for a session never
        seen with a host since this process started, at the first pass that
        finds it host-less. A host who reconnects resets it (§5).
        """
        now = _utc_now()
        live = set(await self.run_db(live_session_ids))
        for session_id in list(self._host_away_since):
            if session_id not in live:
                del self._host_away_since[session_id]
        for session_id in live:
            if self.host_connected(session_id):
                continue
            away_since = self._host_away_since.setdefault(session_id, now)
            if (now - away_since).total_seconds() < abandon_after_seconds:
                continue
            try:
                ended = await self.run_db(abandon_session, session_id)
                if ended is None:
                    continue
                logger.info("Ended abandoned session %s", session_id)
                if ended.closed_question is not None:
                    await self.question_closed(session_id, ended.closed_question)
                await self.session_ended(session_id, ended.results)
            except Exception:
                logger.exception("Could not end abandoned session %s", session_id)

    def start_reaper(
        self, abandon_after_seconds: float, check_every_seconds: float
    ) -> None:
        async def loop() -> None:
            while True:
                await asyncio.sleep(check_every_seconds)
                try:
                    await self.reap_abandoned(abandon_after_seconds)
                except Exception:
                    logger.exception("Abandoned-session check failed")

        self._reaper = asyncio.create_task(loop())

    async def shutdown(self) -> None:
        if self._reaper is not None:
            self._reaper.cancel()
            await asyncio.gather(self._reaper, return_exceptions=True)
            self._reaper = None
        timers = list(self._timers.values())
        self._timers.clear()
        for timer in timers:
            timer.cancel()
        await asyncio.gather(*timers, return_exceptions=True)
