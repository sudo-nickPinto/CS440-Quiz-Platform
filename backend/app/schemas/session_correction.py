from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class CorrectSessionAnswerRequest(BaseModel):
    choice_id: int = Field(gt=0)
    reason: str = Field(
        default="Corrected by class organizer.",
        max_length=500,
    )
    expected_score_revision: int = Field(ge=0)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = value.strip()
        return normalized or "Corrected by class organizer."


class CorrectChoiceSummary(BaseModel):
    choice_id: int
    text: str


class ParticipantRescorePreview(BaseModel):
    session_participant_id: int
    display_name: str
    old_correct: bool
    new_correct: bool
    old_question_points: int
    new_question_points: int
    old_total_score: int
    new_total_score: int
    old_rank: int
    new_rank: int


class SessionAnswerCorrectionPreview(BaseModel):
    session_id: int
    session_question_id: int
    question_order: int
    question_text: str
    score_revision: int
    current_correct_choice: CorrectChoiceSummary
    proposed_correct_choice: CorrectChoiceSummary
    affected_response_count: int
    affected_participants: list[ParticipantRescorePreview]


class SessionAnswerCorrectionResult(SessionAnswerCorrectionPreview):
    correction_id: int
    corrected_at: datetime
    corrected_by_id: int
    reason: str
