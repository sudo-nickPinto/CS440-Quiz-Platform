import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.errors import APIError
from app.live.auth import authenticate_token
from app.live.hub import LiveConnection, LiveHub
from app.live.protocol import (
    UNSUPPORTED_COMMANDS,
    AuthMessage,
    CloseCode,
    LiveCloseError,
    OpenQuestionMessage,
    PingMessage,
    SubmitAnswerMessage,
    close_code_for_status,
    command_adapter,
    error_message,
)
from app.live.snapshot import build_session_state, resolve_membership
from app.schemas.response import ResponseSubmit
from app.services.live_questions import open_question
from app.services.responses import submit_response

logger = logging.getLogger(__name__)
router = APIRouter(tags=["live"])

AUTH_TIMEOUT_SECONDS = 5
IDLE_TIMEOUT_SECONDS = 60


class MalformedMessage(Exception):
    pass


def _parse_json(raw: str) -> dict:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MalformedMessage("invalid_json") from exc
    if not isinstance(data, dict) or not isinstance(data.get("type"), str):
        raise MalformedMessage("missing_type")
    return data


@router.websocket("/ws/sessions/{session_id}")
async def live_session_socket(websocket: WebSocket, session_id: int) -> None:
    await websocket.accept()
    hub: LiveHub = websocket.app.state.live_hub

    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(), timeout=AUTH_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        await websocket.close(code=CloseCode.UNAUTHORIZED, reason="auth_timeout")
        return
    except WebSocketDisconnect:
        return

    try:
        data = _parse_json(raw)
    except MalformedMessage:
        await websocket.close(code=CloseCode.MALFORMED, reason="expected_auth")
        return
    if data["type"] != "auth":
        await websocket.close(code=CloseCode.MALFORMED, reason="expected_auth")
        return
    token = data.get("token")
    if not isinstance(token, str) or not token:
        await websocket.close(code=CloseCode.UNAUTHORIZED, reason="missing_token")
        return
    try:
        auth = AuthMessage.model_validate(data)
    except ValidationError:
        await websocket.close(code=CloseCode.MALFORMED, reason="expected_auth")
        return

    try:
        account = await hub.run_db(
            authenticate_token, websocket.app.state.settings, auth.token
        )
        role, session_participant_id = await hub.run_db(
            resolve_membership, session_id, account
        )
        # Close overdue questions before registering, so the sweep's broadcasts
        # never race this socket's snapshot.
        await hub.sweep(session_id)
    except LiveCloseError as exc:
        await websocket.close(code=exc.close_code, reason=exc.reason)
        return
    except APIError as exc:
        await websocket.close(
            code=close_code_for_status(exc.status_code), reason=exc.code
        )
        return
    except Exception:
        logger.exception("Live connect failed for session %s", session_id)
        await websocket.close(code=CloseCode.SERVER_ERROR, reason="server_error")
        return

    conn = LiveConnection(
        websocket=websocket,
        session_id=session_id,
        account=account,
        role=role,
        session_participant_id=session_participant_id,
    )

    async def snapshot():
        return await hub.run_db(
            build_session_state,
            session_id,
            role,
            session_participant_id,
            hub.host_connected(session_id),
        )

    try:
        # session_state is the first server message; broadcasts queue behind it.
        await hub.connect(conn, snapshot)
        await _receive_loop(hub, conn)
    except WebSocketDisconnect:
        pass
    except LiveCloseError as exc:
        await websocket.close(code=exc.close_code, reason=exc.reason)
    except Exception:
        logger.exception("Live socket failed for session %s", session_id)
        await websocket.close(code=CloseCode.SERVER_ERROR, reason="server_error")
    finally:
        await hub.disconnect(conn)


async def _receive_loop(hub: LiveHub, conn: LiveConnection) -> None:
    websocket = conn.websocket
    while True:
        try:
            raw = await asyncio.wait_for(
                websocket.receive_text(), timeout=IDLE_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            await websocket.close(code=CloseCode.NORMAL, reason="idle_timeout")
            return

        try:
            data = _parse_json(raw)
        except MalformedMessage as exc:
            await websocket.close(code=CloseCode.MALFORMED, reason=str(exc))
            return

        request_id = data.get("request_id")
        request_id = request_id if isinstance(request_id, str) else None
        if data["type"] in UNSUPPORTED_COMMANDS:
            await hub.send(
                conn,
                error_message(
                    request_id,
                    "command_not_supported",
                    "This command is not available yet.",
                ),
            )
            continue

        try:
            message = command_adapter.validate_python(data)
        except ValidationError:
            await websocket.close(code=CloseCode.MALFORMED, reason="invalid_message")
            return

        try:
            await _handle(hub, conn, message)
        except APIError as exc:
            await hub.send(
                conn, error_message(message.request_id, exc.code, exc.message)
            )


async def _handle(hub: LiveHub, conn: LiveConnection, message) -> None:
    if isinstance(message, PingMessage):
        await hub.send(conn, {"type": "pong"})
        return

    if isinstance(message, OpenQuestionMessage):
        event = await hub.run_db(
            open_question, conn.account, conn.session_id, message.question_order
        )
        await hub.send(
            conn,
            {
                "type": "ack",
                "request_id": message.request_id,
                "session_question_id": event.session_question_id,
            },
        )
        await hub.broadcast(conn.session_id, event)
        hub.schedule_deadline(
            conn.session_id, event.session_question_id, event.closes_at
        )
        return

    if isinstance(message, SubmitAnswerMessage):
        receipt = await hub.run_db(
            submit_response,
            conn.account,
            conn.session_id,
            message.session_question_id,
            ResponseSubmit(choice_id=message.choice_id),
        )
        await hub.send(
            conn,
            {
                "type": "ack",
                "request_id": message.request_id,
                "receipt": receipt.model_dump(),
            },
        )
        await hub.after_answer(conn.session_id, message.session_question_id)
