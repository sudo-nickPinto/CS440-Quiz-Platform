from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.quiz_submission import SubmissionStatus


class QuizSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuizSubmissionCreate(QuizSubmissionRequest):
    quiz_version_id: int = Field(gt=0, strict=True)


class QuizSubmissionDecision(QuizSubmissionRequest):
    status: Literal[SubmissionStatus.APPROVED, SubmissionStatus.REJECTED]
    rejection_comment: str | None = Field(default=None, max_length=1000)

    @field_validator("rejection_comment", mode="before")
    @classmethod
    def normalize_rejection_comment(cls, value: object) -> object:
        return (value.strip() or None) if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_rejection_comment(self) -> "QuizSubmissionDecision":
        if self.rejection_comment is not None and self.status != SubmissionStatus.REJECTED:
            raise ValueError("Only rejections can include a comment.")
        return self


class QuizSubmissionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    submission_id: int = Field(gt=0, strict=True)
    class_id: int = Field(gt=0, strict=True)
    quiz_version_id: int = Field(gt=0, strict=True)
    submitted_by_id: int = Field(gt=0, strict=True)
    status: SubmissionStatus
    decided_by_id: int | None = Field(default=None, gt=0, strict=True)
    submitted_at: datetime
    decided_at: datetime | None = None
    rejection_comment: str | None = None


class ApprovedQuizResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submission_id: int = Field(gt=0, strict=True)
    quiz_id: int = Field(gt=0, strict=True)
    quiz_version_id: int = Field(gt=0, strict=True)
    version_number: int = Field(gt=0, strict=True)
    title: str
    author_id: int = Field(gt=0, strict=True)
    approved_at: datetime
    approved_by_id: int = Field(gt=0, strict=True)
