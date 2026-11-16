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
    question_type: QuestionType
    question_text: str
    explanation: str | None
    time_limit_seconds: int
    base_points: int
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
