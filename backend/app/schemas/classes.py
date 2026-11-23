from datetime import datetime
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.classes import ClassRole, MembershipStatus


class ClassRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


SEMESTER_PATTERN = re.compile(r"(spring|summer|fall)\s+(\d{4})", re.IGNORECASE)


def semester_label(value):
    """A real semester such as "Fall 2026", written the same way every time.

    The app only offers Spring, Summer and Fall, so free text is refused.
    """
    if not isinstance(value, str):
        return value
    match = SEMESTER_PATTERN.fullmatch(value.strip())
    if match is None or not 2000 <= int(match.group(2)) <= 2100:
        raise ValueError("Pick a semester such as Fall 2026.")
    return f"{match.group(1).capitalize()} {match.group(2)}"


def _blank_to_none(value):
    # The semester is optional on a class; an empty box means no semester.
    if isinstance(value, str):
        value = value.strip()
        return semester_label(value) if value else None
    return value


class ClassCreate(ClassRequestModel):
    name: str = Field(min_length=1, max_length=100)
    semester: str | None = Field(default=None, max_length=30)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("semester", mode="before")
    @classmethod
    def normalize_semester(cls, value):
        return _blank_to_none(value)


class ClassUpdate(ClassRequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    # null (or "") clears the semester.
    semester: str | None = Field(default=None, max_length=30)
    joining_open: bool | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("semester", mode="before")
    @classmethod
    def normalize_semester(cls, value):
        return _blank_to_none(value)

    @model_validator(mode="after")
    def require_supplied_non_null_field(self) -> "ClassUpdate":
        if not self.model_fields_set:
            raise ValueError("At least one class field must be supplied.")
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("Class name cannot be null.")
        if "joining_open" in self.model_fields_set and self.joining_open is None:
            raise ValueError("joining_open cannot be null.")
        return self


class ClassSemesterCreate(ClassRequestModel):
    semester: str = Field(min_length=1, max_length=30)

    @field_validator("semester", mode="before")
    @classmethod
    def normalize_semester(cls, value):
        return semester_label(value)


class ClassSemester(BaseModel):
    class_id: int
    semester: str | None
    archived: bool


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
    semester: str | None = None
    parent_class_id: int | None = None
    semesters: list[ClassSemester] = []
    created_by_id: int
    join_code: str | None
    joining_open: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_role: ClassRole | None
    membership_status: MembershipStatus | None
