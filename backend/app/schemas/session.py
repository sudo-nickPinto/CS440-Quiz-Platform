from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.session import LiveSessionStatus


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
