from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ResultsModel(BaseModel):
    """Strict base model for internal closed-question result data."""

    model_config = ConfigDict(extra="forbid")


class AnswerChoiceResult(ResultsModel):
    """Response total and correctness for one answer choice."""

    choice_id: int = Field(gt=0)
    response_count: int = Field(ge=0)
    is_correct: bool


class ParticipantQuestionResult(ResultsModel):
    """One participant's result and standing after the question closes."""

    session_participant_id: int = Field(gt=0)
    display_name: str
    selected_choice_id: int | None = Field(default=None, gt=0)
    is_correct: bool
    points_awarded: int = Field(ge=0)
    cumulative_score: int = Field(ge=0)
    rank: int = Field(gt=0)


class ClosedQuestionResultsSnapshot(ResultsModel):
    """Complete internal result data for one closed session question."""

    session_id: int = Field(gt=0)
    session_question_id: int = Field(gt=0)
    correct_choice_ids: list[Annotated[int, Field(gt=0)]] = Field(min_length=1)
    choices: list[AnswerChoiceResult]
    participants: list[ParticipantQuestionResult]

    @model_validator(mode="after")
    def ranks_must_follow_rank_behavior(self) -> "ClosedQuestionResultsSnapshot":
        ordered_scores = sorted(
            (participant.cumulative_score for participant in self.participants),
            reverse=True,
        )
        expected_rank_by_score: dict[int, int] = {}
        for position, score in enumerate(ordered_scores, start=1):
            expected_rank_by_score.setdefault(score, position)

        for participant in self.participants:
            if participant.rank != expected_rank_by_score[participant.cumulative_score]:
                raise ValueError(
                    "Ranks must use RANK behavior based on cumulative score."
                )
        return self
