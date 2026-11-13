from datetime import datetime

from pydantic import BaseModel, Field

from app.models.session import SessionCorrectionMode


class CorrectSessionAnswerRequest(BaseModel):
    choice_id: int = Field(gt=0)
    mode: SessionCorrectionMode = SessionCorrectionMode.REPLACE
    expected_score_revision: int = Field(ge=0)


class CorrectChoiceSummary(BaseModel):
    choice_id: int
    text: str


class SessionAnswerCorrectionResult(BaseModel):
    correction_id: int
    session_id: int
    session_question_id: int
    score_revision: int
    correction_mode: SessionCorrectionMode
    selected_choice: CorrectChoiceSummary
    previous_correct_choices: list[CorrectChoiceSummary]
    corrected_choices: list[CorrectChoiceSummary]
    corrected_at: datetime
    corrected_by_id: int
