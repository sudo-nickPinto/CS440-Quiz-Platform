from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.quiz_submission import SubmissionStatus


class QuizSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuizSubmissionCreate(QuizSubmissionRequest):
    quiz_version_id: int = Field(gt=0, strict=True)


class QuizSubmissionDecision(QuizSubmissionRequest):
    status: Literal[SubmissionStatus.APPROVED, SubmissionStatus.REJECTED]


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
