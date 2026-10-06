from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.quiz import QuestionType, QuizStatus, QuizVisibility


class QuizRequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnswerChoiceCreate(QuizRequestModel):
    choice_text: str = Field(max_length=500)
    is_correct: bool = False

    @field_validator("choice_text")
    @classmethod
    def choice_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Choice text must not be blank.")
        return value


class QuestionCreate(QuizRequestModel):
    question_text: str
    time_limit_seconds: int = Field(default=20, ge=1, le=65_535)
    base_points: int = Field(default=1000, ge=1, le=4_294_967_295)
    choices: list[AnswerChoiceCreate] = Field(min_length=2, max_length=255)

    @field_validator("question_text")
    @classmethod
    def question_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question text must not be blank.")
        return value

    @model_validator(mode="after")
    def must_have_a_correct_choice(self) -> "QuestionCreate":
        if not any(choice.is_correct for choice in self.choices):
            raise ValueError("Each question must have at least one correct choice.")
        return self


class QuizCreate(QuizRequestModel):
    title: str = Field(max_length=200)
    description: str | None = None
    questions: list[QuestionCreate] = Field(min_length=1, max_length=65_535)

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Quiz title must not be blank.")
        return value

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


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
    published_at: datetime
    questions: list[QuestionResponse]


class QuizResponse(BaseModel):
    quiz_id: int
    author_id: int
    status: QuizStatus
    visibility: QuizVisibility
    created_at: datetime
    updated_at: datetime
    version: QuizVersionResponse


class QuizListItem(BaseModel):
    quiz_id: int
    author_id: int
    status: QuizStatus
    title: str
    description: str | None
    question_count: int
    created_at: datetime
