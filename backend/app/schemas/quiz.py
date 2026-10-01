from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import QuestionType, QuizStatus, QuizVisibility


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuizCreate(StrictSchema):
    title: str = Field(default="Untitled Quiz", max_length=200)
    description: str | None = None
    visibility: QuizVisibility = QuizVisibility.PRIVATE

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("Title must not be blank.")
        return title


class AnswerChoiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    choice_id: int
    choice_order: int
    choice_text: str
    is_correct: bool


class QuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    question_id: int
    question_order: int
    question_type: QuestionType
    question_text: str
    explanation: str | None
    time_limit_seconds: int
    base_points: int
    choices: list[AnswerChoiceResponse]


class QuizVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    quiz_version_id: int
    version_number: int
    title: str
    description: str | None
    created_at: datetime
    published_at: datetime | None
    questions: list[QuestionResponse]


class QuizResponse(BaseModel):
    quiz_id: int
    author_id: int
    status: QuizStatus
    visibility: QuizVisibility
    created_at: datetime
    updated_at: datetime
    current_version: QuizVersionResponse


class QuizListItem(BaseModel):
    quiz_id: int
    author_id: int
    status: QuizStatus
    visibility: QuizVisibility
    title: str
    version_number: int
    created_at: datetime
    updated_at: datetime
