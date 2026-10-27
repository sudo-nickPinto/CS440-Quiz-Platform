from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.classes import ClassRole, MembershipStatus


class ClassRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClassCreate(ClassRequestModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class ClassUpdate(ClassRequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    joining_open: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_supplied_non_null_field(self) -> "ClassUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one class field must be supplied.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Class name cannot be null.")
        if "joining_open" in self.model_fields_set and self.joining_open is None:
            raise ValueError("joining_open cannot be null.")
        return self


class ClassJoin(ClassRequestModel):
    code: str = Field(min_length=1, max_length=20)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value):
        # Accept "abcd-2345", "ABCD 2345" or "abcd2345" for stored "ABCD2345".
        if not isinstance(value, str):
            return value
        return "".join(value.split()).replace("-", "").upper()


class ClassResponse(BaseModel):
    class_id: int
    name: str
    created_by_id: int
    join_code: str | None
    joining_open: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_role: ClassRole | None
    membership_status: MembershipStatus | None
