from datetime import datetime

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.quiz import (
    CollaboratorPermission,
    QuestionType,
    QuizStatus,
    QuizVisibility,
)


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
    explanation: str | None = Field(default=None, max_length=5000)
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

    @field_validator("explanation")
    @classmethod
    def normalize_explanation(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None

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

class QuizUpdate(QuizCreate):
    # base_version remains accepted while existing clients migrate to the V3
    # optimistic-locking name.
    expected_revision: int = Field(
        ge=1,
        strict=True,
        validation_alias=AliasChoices("expected_revision", "base_version"),
    )


class QuizCollaboratorCreate(QuizRequestModel):
    email: str = Field(max_length=320)
    permission: CollaboratorPermission = CollaboratorPermission.EDITOR

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not value or "@" not in value:
            raise ValueError("A valid email address is required.")
        return value


class QuizCollaboratorResponse(BaseModel):
    quiz_id: int
    account_id: int
    email: str
    display_name: str
    permission: CollaboratorPermission
    shared_by_id: int
    created_at: datetime


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
    explanation: str | None = None
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
    class_id: int | None
    revision: int
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
