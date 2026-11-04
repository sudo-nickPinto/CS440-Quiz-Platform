import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.errors import APIError
from app.live.auth import authenticate_token
from app.live.protocol import CloseCode, LiveCloseError, close_code_for_status
from app.quiz_editing import QuizEditConnection, QuizEditHub
from app.services.quizzes import require_quiz_editor_access

logger = logging.getLogger(__name__)
router = APIRouter(tags=["quiz editing"])
AUTH_TIMEOUT_SECONDS = 5
IDLE_TIMEOUT_SECONDS = 60


@router.websocket("/ws/quizzes/{quiz_id}")
async def quiz_editor_socket(websocket: WebSocket, quiz_id: int) -> None:
    await websocket.accept()
    hub: QuizEditHub = websocket.app.state.quiz_edit_hub
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
        await hub.run_db(require_quiz_editor_access, account, quiz_id)
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
    except APIError as exc:
        await websocket.close(
            code=close_code_for_status(exc.status_code), reason=exc.code
        )
        return
    except Exception:
        logger.exception("Quiz editor connect failed for quiz %s", quiz_id)
        await websocket.close(code=CloseCode.SERVER_ERROR, reason="server_error")
        return

    connection = QuizEditConnection(websocket, quiz_id, account)
    try:
        await hub.connect(connection)
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
                await hub.send(connection, {"type": "pong"})
            else:
                await websocket.close(code=CloseCode.MALFORMED, reason="invalid_message")
                return
    except asyncio.TimeoutError:
        await websocket.close(code=CloseCode.GOING_AWAY, reason="idle_timeout")
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(connection)
