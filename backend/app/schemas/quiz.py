from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class QuizUpdate(StrictSchema):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    visibility: QuizVisibility | None = None

    @field_validator("title")
    @classmethod
    def title_must_be_present_and_nonblank(cls, value: str | None) -> str:
        if value is None or not value.strip():
            raise ValueError("Title must not be null or blank.")
        return value.strip()

    @field_validator("visibility")
    @classmethod
    def visibility_must_not_be_null(
        cls, value: QuizVisibility | None
    ) -> QuizVisibility:
        if value is None:
            raise ValueError("Visibility must not be null.")
        return value

    @model_validator(mode="after")
    def request_must_contain_an_update(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("At least one editable field is required.")
        return self


class AnswerChoiceWrite(StrictSchema):
    choice_text: str = Field(min_length=1, max_length=500)
    is_correct: bool = False

    @field_validator("choice_text")
    @classmethod
    def choice_text_must_not_be_blank(cls, value: str) -> str:
        choice_text = value.strip()
        if not choice_text:
            raise ValueError("Choice text must not be blank.")
        return choice_text


class QuestionWrite(StrictSchema):
    question_text: str
    explanation: str | None = None
    time_limit_seconds: int = Field(default=20, gt=0, le=65_535)
    base_points: int = Field(default=1000, gt=0, le=4_294_967_295)
    choices: list[AnswerChoiceWrite] = Field(min_length=2, max_length=255)

    @field_validator("question_text")
    @classmethod
    def question_text_must_not_be_blank(cls, value: str) -> str:
        question_text = value.strip()
        if not question_text:
            raise ValueError("Question text must not be blank.")
        return question_text

    @model_validator(mode="after")
    def at_least_one_choice_must_be_correct(self) -> Self:
        if not any(choice.is_correct for choice in self.choices):
            raise ValueError("At least one answer choice must be correct.")
        return self


class QuestionOrderUpdate(StrictSchema):
    question_ids: list[int] = Field(min_length=1, max_length=65_535)

    @field_validator("question_ids")
    @classmethod
    def question_ids_must_be_unique(cls, value: list[int]) -> list[int]:
        if any(question_id <= 0 for question_id in value):
            raise ValueError("Question IDs must be positive.")
        if len(value) != len(set(value)):
            raise ValueError("Question IDs must not contain duplicates.")
        return value


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
