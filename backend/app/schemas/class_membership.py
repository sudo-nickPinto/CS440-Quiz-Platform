from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.classes import MembershipStatus


class ClassMemberRole(str, Enum):
    CLASS_ADMIN = "CLASS_ADMIN"
    MEMBER = "MEMBER"


class ClassMembershipRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClassMemberCreate(ClassMembershipRequest):
    email: str = Field(max_length=320)
    role: ClassMemberRole = ClassMemberRole.MEMBER

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("Email must not be blank.")
        return normalized


class ClassMemberUpdate(ClassMembershipRequest):
    role: ClassMemberRole


class ClassMemberResponse(BaseModel):
    membership_id: int
    class_id: int
    account_id: int
    email: str
    display_name: str
    role: ClassMemberRole
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime
