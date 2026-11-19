import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.live.auth import authenticate_token
from app.live.protocol import CloseCode, LiveCloseError
from app.models.account import Account
from app.notifications import NotificationConnection, NotificationHub

logger = logging.getLogger(__name__)
router = APIRouter(tags=["notifications"])
AUTH_TIMEOUT_SECONDS = 5
# Clients ping every 25 s; the slack covers hidden tabs whose timers the
# browser throttles.
IDLE_TIMEOUT_SECONDS = 120


def account_is_active(db: Session, account_id: int) -> bool:
    return bool(
        db.scalar(select(Account.is_active).where(Account.account_id == account_id))
    )


@router.websocket("/ws/notifications")
async def notifications_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    hub: NotificationHub = websocket.app.state.notification_hub
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS
        )
        message = json.loads(raw)
        if not isinstance(message, dict) or message.get("type") != "auth":
            raise ValueError
        token = message.get("token")
        if not isinstance(token, str) or not token:
            await websocket.close(code=CloseCode.UNAUTHORIZED, reason="missing_token")
            return
        account = await hub.run_db(
            authenticate_token, websocket.app.state.settings, token
        )
    except asyncio.TimeoutError:
        await websocket.close(code=CloseCode.UNAUTHORIZED, reason="auth_timeout")
        return
    except (json.JSONDecodeError, ValueError):
        await websocket.close(code=CloseCode.MALFORMED, reason="expected_auth")
        return
    except WebSocketDisconnect:
        return
    except LiveCloseError as exc:
        await websocket.close(code=exc.close_code, reason=exc.reason)
        return
    except Exception:
        logger.exception("Notification socket connect failed")
        await websocket.close(code=CloseCode.SERVER_ERROR, reason="server_error")
        return

    connection = NotificationConnection(websocket, account)
    try:
        if not await hub.connect(connection):
            return
        while True:
            raw = await asyncio.wait_for(
                websocket.receive_text(), timeout=IDLE_TIMEOUT_SECONDS
            )
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.close(code=CloseCode.MALFORMED, reason="invalid_json")
                return
            if message == {"type": "ping"}:
                # Pings also recheck the account so a deactivated account
                # cannot keep a quiet socket open forever.
                if not await hub.run_db(account_is_active, account.account_id):
                    await websocket.close(
                        code=CloseCode.FORBIDDEN, reason="inactive_account"
                    )
                    return
                if not await hub.send(connection, {"type": "pong"}):
                    return
            else:
                await websocket.close(code=CloseCode.MALFORMED, reason="invalid_message")
                return
    except asyncio.TimeoutError:
        await websocket.close(code=CloseCode.GOING_AWAY, reason="idle_timeout")
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(connection)
