import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.errors import APIError
from app.live.auth import authenticate_token
from app.live.hub import LiveConnection, LiveHub
from app.live.protocol import (
    AuthMessage,
    CancelSessionMessage,
    CloseCode,
    CloseQuestionMessage,
    EndSessionMessage,
    LeaveMessage,
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
from app.services.live_questions import close_question_now, open_question
from app.services.responses import submit_response
from app.services.session_end import cancel_session, end_session, leave_session

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
            # Not 1000: clients treat 1000 as "session over" (§7). 1001 is
            # retryable, so a client whose pings stalled just reconnects.
            await websocket.close(code=CloseCode.GOING_AWAY, reason="idle_timeout")
            return

        try:
            data = _parse_json(raw)
        except MalformedMessage as exc:
            await websocket.close(code=CloseCode.MALFORMED, reason=str(exc))
            return

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
        if conn.closed:
            return  # the session ended or this participant left


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
        return

    if isinstance(message, CloseQuestionMessage):
        _require_host(conn)
        event = await hub.run_db(
            close_question_now,
            conn.account,
            conn.session_id,
            message.session_question_id,
        )
        await hub.send(
            conn,
            {
                "type": "ack",
                "request_id": message.request_id,
                "session_question_id": message.session_question_id,
            },
        )
        # None: an answer or the deadline closed it first and already broadcast.
        if event is not None:
            await hub.question_closed(conn.session_id, event)
        return

    if isinstance(message, EndSessionMessage):
        _require_host(conn)
        ended = await hub.run_db(end_session, conn.account, conn.session_id)
        await hub.send(conn, {"type": "ack", "request_id": message.request_id})
        if ended.closed_question is not None:
            await hub.question_closed(conn.session_id, ended.closed_question)
        await hub.session_ended(conn.session_id, ended.results)
        return

    if isinstance(message, CancelSessionMessage):
        _require_host(conn)
        results = await hub.run_db(cancel_session, conn.account, conn.session_id)
        await hub.send(conn, {"type": "ack", "request_id": message.request_id})
        await hub.session_ended(conn.session_id, results)
        return

    if isinstance(message, LeaveMessage):
        if conn.role != "participant":
            raise APIError(
                403,
                "session_participant_denied",
                "Only a participant can leave; the host ends or cancels instead.",
            )
        left = await hub.run_db(leave_session, conn.account, conn.session_id)
        await hub.send(conn, {"type": "ack", "request_id": message.request_id})
        await hub.participant_left(conn, left)
        return


def _require_host(conn: LiveConnection) -> None:
    # The services check host_id too; this just gives a clearer error early.
    if conn.role != "host":
        raise APIError(
            403,
            "session_host_denied",
            "Only this session's host can do that.",
        )
