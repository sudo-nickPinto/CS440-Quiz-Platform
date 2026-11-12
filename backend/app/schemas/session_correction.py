from datetime import datetime

from pydantic import BaseModel, Field


class CorrectSessionAnswerRequest(BaseModel):
    choice_id: int = Field(gt=0)
    expected_score_revision: int = Field(ge=0)


class CorrectChoiceSummary(BaseModel):
    choice_id: int
    text: str


class SessionAnswerCorrectionResult(BaseModel):
    correction_id: int
    session_id: int
    session_question_id: int
    score_revision: int
    previous_correct_choice: CorrectChoiceSummary
    corrected_choice: CorrectChoiceSummary
    corrected_at: datetime
    corrected_by_id: int
