from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.session import LiveSessionStatus


class SessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # None: an open session anyone with the join code can join.
    class_id: int | None = Field(default=None, ge=1)


class SessionJoinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    join_code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")

    @field_validator("join_code", mode="before")
    @classmethod
    def normalize_join_code(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class SessionResponse(BaseModel):
    session_id: int
    quiz_id: int
    quiz_version_id: int
    quiz_title: str
    host_id: int
    # The class the host picked; None is an open session.
    class_id: int | None
    join_code: str
    status: LiveSessionStatus
    current_question_order: int | None
    created_at: datetime
    started_at: datetime | None
    ended_at: datetime | None


class SessionParticipantResponse(BaseModel):
    session_participant_id: int
    account_id: int
    display_name: str
    joined_at: datetime


class SessionJoinResponse(BaseModel):
    session: SessionResponse
    participant: SessionParticipantResponse


class ClassActiveSessionResponse(BaseModel):
    """A lobby or running session shown on its class page."""

    session_id: int
    class_id: int
    quiz_id: int
    quiz_title: str
    host_id: int
    is_host: bool
    # The caller already joined, so the Live button can go straight in.
    joined: bool
    # A participant row is permanent. Once the caller leaves, they cannot
    # rejoin this session and the class page must not offer a working button.
    left: bool
    join_code: str
    status: LiveSessionStatus
    current_question_order: int | None
    question_count: int
    created_at: datetime
    started_at: datetime | None
