from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.classes import ClassRole, MembershipStatus


class ClassMembershipRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClassInviteCreate(ClassMembershipRequest):
    email: str = Field(max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Email must not be blank.")
        return normalized


class ClassMemberUpdate(ClassMembershipRequest):
    role: ClassRole


class ClassMemberResponse(BaseModel):
    membership_id: int
    class_id: int
    account_id: int
    email: str
    display_name: str
    role: ClassRole
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime
