import json
from datetime import UTC, datetime
from enum import IntEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class CloseCode(IntEnum):
    """WebSocket close codes from LIVE_PROTOCOL.md §7."""

    NORMAL = 1000
    GOING_AWAY = 1001  # idle timeout / restart: the client reconnects
    SERVER_ERROR = 1011
    MALFORMED = 4400
    UNAUTHORIZED = 4401
    FORBIDDEN = 4403
    NOT_FOUND = 4404
    REPLACED = 4409
    SESSION_OVER = 4410


class LiveCloseError(Exception):
    """Raised during connect when the socket must be closed instead of served."""

    def __init__(self, close_code: CloseCode, reason: str):
        super().__init__(reason)
        self.close_code = close_code
        self.reason = reason


# Expected HTTP-style failures from shared services -> close codes (§7).
_STATUS_CLOSE_CODES = {
    400: CloseCode.MALFORMED,
    401: CloseCode.UNAUTHORIZED,
    403: CloseCode.FORBIDDEN,
    404: CloseCode.NOT_FOUND,
}


def close_code_for_status(status_code: int) -> CloseCode:
    """Map an APIError status to a close code; anything else is a server error."""
    return _STATUS_CLOSE_CODES.get(status_code, CloseCode.SERVER_ERROR)


class InboundMessage(BaseModel):
    """Clients only ever send IDs; never scores, roles, or times."""

    model_config = ConfigDict(extra="forbid")

    request_id: str | None = Field(default=None, max_length=64)


class AuthMessage(InboundMessage):
    type: Literal["auth"]
    token: str = Field(min_length=1)


class PingMessage(InboundMessage):
    type: Literal["ping"]


class OpenQuestionMessage(InboundMessage):
    type: Literal["open_question"]
    question_order: int = Field(gt=0)


class SubmitAnswerMessage(InboundMessage):
    type: Literal["submit_answer"]
    session_question_id: int = Field(gt=0)
    choice_id: int = Field(gt=0)


class CloseQuestionMessage(InboundMessage):
    """Host skip: close the open question now (reason HOST)."""

    type: Literal["close_question"]
    session_question_id: int = Field(gt=0)


class EndSessionMessage(InboundMessage):
    type: Literal["end_session"]


class CancelSessionMessage(InboundMessage):
    type: Literal["cancel_session"]


class LeaveMessage(InboundMessage):
    type: Literal["leave"]


CommandMessage = Annotated[
    PingMessage
    | OpenQuestionMessage
    | SubmitAnswerMessage
    | CloseQuestionMessage
    | EndSessionMessage
    | CancelSessionMessage
    | LeaveMessage,
    Field(discriminator="type"),
]
command_adapter: TypeAdapter[CommandMessage] = TypeAdapter(CommandMessage)


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        # DB timestamps are naive UTC; the protocol sends ISO-8601 with a Z.
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        return value.isoformat(timespec="milliseconds") + "Z"
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def encode(payload: BaseModel | dict[str, Any]) -> str:
    if isinstance(payload, BaseModel):
        payload = payload.model_dump()
    return json.dumps(payload, default=_json_default)


def error_message(request_id: str | None, code: str, message: str) -> dict:
    return {
        "type": "error",
        "request_id": request_id,
        "code": code,
        "message": message,
    }
