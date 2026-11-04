import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from fastapi import FastAPI, WebSocket
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.auth import CurrentAccount
from app.errors import APIError
from app.live.protocol import CloseCode, encode

logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(eq=False)
class QuizEditConnection:
    websocket: WebSocket
    quiz_id: int
    account: CurrentAccount
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class QuizEditHub:
    """Best-effort live notifications for collaborative quiz editing.

    Notifications improve freshness, but question revisions in MySQL remain
    the source of truth. This in-memory hub intentionally carries no locks or
    unsaved editor state.
    """

    def __init__(self, app: FastAPI):
        self._app = app
        self._quizzes: dict[int, set[QuizEditConnection]] = {}

    async def run_db(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        def call() -> T:
            with self._app.state.database.session_factory() as db:
                return fn(db, *args, **kwargs)

        return await run_in_threadpool(call)

    async def connect(self, connection: QuizEditConnection) -> None:
        self._quizzes.setdefault(connection.quiz_id, set()).add(connection)
        await self.send(
            connection,
            {"type": "quiz_editor_state", "quiz_id": connection.quiz_id},
        )

    async def disconnect(self, connection: QuizEditConnection) -> None:
        connections = self._quizzes.get(connection.quiz_id)
        if connections is None:
            return
        connections.discard(connection)
        if not connections:
            self._quizzes.pop(connection.quiz_id, None)

    async def send(
        self,
        connection: QuizEditConnection,
        payload: BaseModel | dict,
    ) -> None:
        try:
            async with connection.send_lock:
                await connection.websocket.send_text(encode(payload))
        except Exception:
            logger.debug("Dropped quiz edit notification", exc_info=True)

    async def broadcast(self, quiz_id: int, payload: BaseModel | dict) -> None:
        targets = list(self._quizzes.get(quiz_id, set()))
        await asyncio.gather(*(self._send_if_authorized(target, payload) for target in targets))

    async def _send_if_authorized(
        self,
        connection: QuizEditConnection,
        payload: BaseModel | dict,
    ) -> None:
        # Membership and collaborator access may be revoked while a socket is
        # open. Re-check before exposing any later edit notification.
        from app.services.quizzes import require_quiz_editor_access

        try:
            await self.run_db(
                require_quiz_editor_access,
                connection.account,
                connection.quiz_id,
            )
        except APIError:
            await self.disconnect(connection)
            try:
                await connection.websocket.close(
                    code=CloseCode.FORBIDDEN,
                    reason="quiz_edit_denied",
                )
            except Exception:
                logger.debug("Revoked quiz editor socket already closed", exc_info=True)
            return
        except Exception:
            logger.exception("Could not re-authorize quiz editor notification")
            return
        await self.send(connection, payload)

    async def close_account(self, quiz_id: int, account_id: int) -> None:
        targets = [
            connection
            for connection in self._quizzes.get(quiz_id, set())
            if connection.account.account_id == account_id
        ]
        for connection in targets:
            await self.disconnect(connection)
            try:
                await connection.websocket.close(
                    code=CloseCode.FORBIDDEN,
                    reason="quiz_edit_denied",
                )
            except Exception:
                logger.debug("Revoked quiz editor socket already closed", exc_info=True)

    async def shutdown(self) -> None:
        targets = [
            connection
            for connections in self._quizzes.values()
            for connection in connections
        ]
        self._quizzes.clear()
        await asyncio.gather(
            *(
                connection.websocket.close(
                    code=CloseCode.GOING_AWAY,
                    reason="server_shutdown",
                )
                for connection in targets
            ),
            return_exceptions=True,
        )
