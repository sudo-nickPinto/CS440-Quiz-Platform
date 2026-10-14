from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LiveQuestionEventModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuestionChoiceEvent(LiveQuestionEventModel):
    choice_id: int = Field(gt=0)
    choice_order: int = Field(gt=0)
    choice_text: str


class QuestionOpenedEvent(LiveQuestionEventModel):
    type: Literal["question_opened"] = "question_opened"
    session_id: int = Field(gt=0)
    session_question_id: int = Field(gt=0)
    question_order: int = Field(gt=0)
    total_questions: int = Field(gt=0)
    question_text: str
    choices: list[QuestionChoiceEvent]
    opened_at: datetime
    closes_at: datetime

    @model_validator(mode="after")
    def closes_after_opening(self) -> "QuestionOpenedEvent":
        if self.closes_at <= self.opened_at:
            raise ValueError("closes_at must be later than opened_at.")
        return self


class QuestionCloseReason(str, Enum):
    ALL_ANSWERED = "ALL_ANSWERED"
    DEADLINE = "DEADLINE"


class QuestionClosedEvent(LiveQuestionEventModel):
    type: Literal["question_closed"] = "question_closed"
    session_id: int = Field(gt=0)
    session_question_id: int = Field(gt=0)
    question_order: int = Field(gt=0)
    reason: QuestionCloseReason
    answered_count: int = Field(ge=0)
    eligible_count: int = Field(ge=0)
    opened_at: datetime
    closes_at: datetime
    closed_at: datetime

    @model_validator(mode="after")
    def validate_counts_and_timestamps(self) -> "QuestionClosedEvent":
        if self.answered_count > self.eligible_count:
            raise ValueError("answered_count cannot exceed eligible_count.")
        if self.closes_at <= self.opened_at:
            raise ValueError("closes_at must be later than opened_at.")
        if self.closed_at < self.opened_at:
            raise ValueError("closed_at cannot be earlier than opened_at.")
        return self
