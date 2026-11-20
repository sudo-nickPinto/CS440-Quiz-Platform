from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.quiz import QuestionType
from app.schemas.pagination import PageInfo
from app.schemas.quiz import AnswerChoiceCreate, QuestionCreate, QuizResponse


class BankScope(str, Enum):
    CLASS = "class"
    MINE = "mine"


class QuestionBankItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    bank_question_id: int
    owner_id: int
    source_class_id: int | None
    source_quiz_id: int | None = None
    question_type: QuestionType
    question_text: str
    explanation: str | None
    choices: list[AnswerChoiceCreate]
    updated_at: datetime


class QuestionBankPage(BaseModel):
    items: list[QuestionBankItemResponse]
    pagination: PageInfo


class BankSelection(BaseModel):
    bank_question_ids: list[int] = Field(min_length=1, max_length=500)

    @field_validator("bank_question_ids")
    @classmethod
    def unique_ids(cls, value: list[int]) -> list[int]:
        if any(item < 1 for item in value) or len(value) != len(set(value)):
            raise ValueError("Question IDs must be unique positive integers.")
        return value


class CsvPreviewRequest(BaseModel):
    csv_text: str = Field(min_length=1, max_length=2_000_000)


class CsvPreviewRow(BaseModel):
    row_number: int
    valid: bool
    question: QuestionCreate | None = None
    errors: list[str] = Field(default_factory=list)


class CsvPreviewResponse(BaseModel):
    rows: list[CsvPreviewRow]
    valid_count: int
    invalid_count: int


class CsvImportRow(BaseModel):
    row_number: int
    question: QuestionCreate


class CsvImportRequest(BaseModel):
    rows: list[CsvImportRow] = Field(min_length=1, max_length=500)
    save_unselected_to_bank: bool = False
    bank_only_rows: list[CsvImportRow] = Field(default_factory=list, max_length=500)


class CsvImportResponse(BaseModel):
    quiz: QuizResponse
    added_to_quiz: int
    saved_to_bank_only: int


class CsvBankSaveRequest(BaseModel):
    rows: list[CsvImportRow] = Field(min_length=1, max_length=500)


class CsvBankSaveResponse(BaseModel):
    saved_to_bank: int


class DuplicateQuizResponse(BaseModel):
    quiz: QuizResponse


class BankSourceQuiz(BaseModel):
    quiz_id: int
    title: str
    question_count: int


class BankSourceCourse(BaseModel):
    class_id: int
    name: str
    archived: bool
    question_count: int
    # Questions saved straight to the bank (e.g. from a CSV) have no quiz.
    quizzes: list[BankSourceQuiz]


class BankSourcesResponse(BaseModel):
    courses: list[BankSourceCourse]


def _unique_positive(value: list[int], label: str) -> list[int]:
    if any(item < 1 for item in value) or len(value) != len(set(value)):
        raise ValueError(f"{label} must be unique positive integers.")
    return value


class BankExportRequest(BaseModel):
    """What to download from the account-wide bank.

    Every question visible in ``class_ids`` (optionally one quiz, optionally a
    search), or exactly ``bank_question_ids`` when given.
    """

    class_ids: list[int] = Field(min_length=1, max_length=200)
    quiz_id: int | None = Field(default=None, ge=1)
    search: str = Field(default="", max_length=200)
    bank_question_ids: list[int] | None = Field(default=None, min_length=1, max_length=5000)

    @field_validator("class_ids")
    @classmethod
    def unique_classes(cls, value: list[int]) -> list[int]:
        return _unique_positive(value, "Class IDs")

    @field_validator("bank_question_ids")
    @classmethod
    def unique_questions(cls, value: list[int] | None) -> list[int] | None:
        return None if value is None else _unique_positive(value, "Question IDs")
