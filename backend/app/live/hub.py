import asyncio
import logging
from collections.abc import Callable
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
    host_results_view,
    open_question_deadlines,
    participant_results_view,
)
from app.services.live_questions import answer_progress, close_question_if_ready
from app.services.results import get_closed_question_results

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


class LiveHub:
    """In-memory registry of live sockets for one uvicorn worker (§8.3).

    The database stays the source of truth: every method that changes state
    commits through a service first, and only then sends news to sockets.
    """

    def __init__(self, app: FastAPI):
        self._app = app
        self._sessions: dict[int, dict[int, LiveConnection]] = {}
        self._timers: dict[int, asyncio.Task] = {}

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

    async def connect(self, conn: LiveConnection) -> None:
        connections = self._sessions.setdefault(conn.session_id, {})
        previous = connections.get(conn.account.account_id)
        connections[conn.account.account_id] = conn
        if previous is not None:
            await self._close(previous, CloseCode.REPLACED, "replaced")
        if conn.role == "host":
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
        if conn.role == "host":
            await self.broadcast(
                conn.session_id,
                {"type": "host_status", "connected": False},
                role="participant",
            )

    # Sending ------------------------------------------------------------

    async def send(self, conn: LiveConnection, payload: BaseModel | dict) -> None:
        try:
            async with conn.send_lock:
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

        timer = self._timers.pop(session_question_id, None)
        if timer is not None and timer is not asyncio.current_task():
            timer.cancel()
        await self.broadcast(session_id, event)
        await self.publish_results(session_id, session_question_id)
        return True

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

    async def shutdown(self) -> None:
        timers = list(self._timers.values())
        self._timers.clear()
        for timer in timers:
            timer.cancel()
        await asyncio.gather(*timers, return_exceptions=True)
