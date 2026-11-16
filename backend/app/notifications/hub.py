"""Per-account notification sockets (`/ws/notifications`).

The registry lives in memory, so like the live-session and quiz-edit hubs it
only reaches sockets held by this uvicorn worker. The app runs one worker
(LIVE_PROTOCOL.md §8.3); several workers would need a shared pub/sub.
"""

import asyncio
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from fastapi import FastAPI, WebSocket
from pydantic import BaseModel

from app.auth import CurrentAccount
from app.database import run_in_db_session
from app.live.protocol import CloseCode, encode

logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass(eq=False)
class NotificationConnection:
    websocket: WebSocket
    account: CurrentAccount
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class NotificationHub:
    """Best-effort pushes of small events to specific accounts.

    An account may hold several sockets (tabs, devices); none replaces another.
    Events only tell a client that something changed. MySQL stays the source
    of truth, so a client that missed an event refetches on reconnect. The hub
    never touches the database to pick recipients: callers resolve the
    account ids after their commit and pass them in.
    """

    def __init__(self, app: FastAPI):
        self._app = app
        self._accounts: dict[int, set[NotificationConnection]] = {}

    async def run_db(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        return await run_in_db_session(self._app, fn, *args, **kwargs)

    async def connect(self, connection: NotificationConnection) -> bool:
        # Register and send the ready message under the send lock, so an
        # event pushed meanwhile waits and arrives after notifications_ready.
        async with connection.send_lock:
            self._accounts.setdefault(connection.account.account_id, set()).add(
                connection
            )
            try:
                await connection.websocket.send_text(
                    encode({"type": "notifications_ready"})
                )
                return True
            except Exception:
                logger.debug("Notification socket closed before ready", exc_info=True)
        await self.disconnect(connection)
        return False

    async def disconnect(self, connection: NotificationConnection) -> None:
        account_id = connection.account.account_id
        connections = self._accounts.get(account_id)
        if connections is None:
            return
        connections.discard(connection)
        if not connections:
            self._accounts.pop(account_id, None)

    async def send(
        self,
        connection: NotificationConnection,
        payload: BaseModel | dict,
    ) -> bool:
        return await self._send_text(connection, encode(payload))

    async def _send_text(self, connection: NotificationConnection, text: str) -> bool:
        try:
            async with connection.send_lock:
                await connection.websocket.send_text(text)
            return True
        except Exception:
            logger.debug("Dropped notification", exc_info=True)
            await self.disconnect(connection)
            return False

    async def send_to_accounts(
        self,
        account_ids: Iterable[int],
        payload: BaseModel | dict,
    ) -> None:
        """Send one event to every open socket of each listed account.

        Duplicate ids are sent once. A failed send drops only that socket.
        """
        text = encode(payload)
        targets = [
            connection
            for account_id in set(account_ids)
            for connection in list(self._accounts.get(account_id, ()))
        ]
        if targets:
            await asyncio.gather(
                *(self._send_text(target, text) for target in targets)
            )

    async def close_account(
        self,
        account_id: int,
        code: CloseCode = CloseCode.FORBIDDEN,
        reason: str = "inactive_account",
    ) -> None:
        targets = list(self._accounts.pop(account_id, set()))
        for connection in targets:
            try:
                await connection.websocket.close(code=code, reason=reason)
            except Exception:
                logger.debug("Notification socket already closed", exc_info=True)

    async def shutdown(self) -> None:
        targets = [
            connection
            for connections in self._accounts.values()
            for connection in connections
        ]
        self._accounts.clear()
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
