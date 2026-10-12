from collections import Counter
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.errors import APIError
from app.models import (
    Account,
    AnswerChoice,
    Response,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.schemas.results import (
    AnswerChoiceResult,
    ClosedQuestionResultsSnapshot,
    ParticipantQuestionResult,
)


@dataclass(frozen=True)
class StoredQuestionResponse:
    session_participant_id: int
    choice_id: int | None
    is_correct: bool
    points_awarded: int


@dataclass(frozen=True)
class ClosedQuestionResultData:
    session_id: int
    session_question_id: int
    correct_choice_ids: list[int]
    choices: list[AnswerChoiceResult]
    responses: list[StoredQuestionResponse]


@dataclass(frozen=True)
class UnrankedParticipantResult:
    session_participant_id: int
    display_name: str
    selected_choice_id: int | None
    is_correct: bool
    points_awarded: int
    cumulative_score: int


def get_closed_question_result_data(
    db: Session,
    session_id: int,
    session_question_id: int,
) -> ClosedQuestionResultData:
    session_question = db.get(SessionQuestion, session_question_id)
    if session_question is None or session_question.session_id != session_id:
        raise APIError(
            404,
            "session_question_not_found",
            "The question was not found in this session.",
        )
    if session_question.status != SessionQuestionStatus.CLOSED:
        raise APIError(
            409,
            "question_results_unavailable",
            "Results are available only after the question closes.",
        )

    answer_choices = db.scalars(
        select(AnswerChoice)
        .where(AnswerChoice.question_id == session_question.question_id)
        .order_by(AnswerChoice.choice_order)
    ).all()
    response_rows = db.execute(
        select(
            Response.session_participant_id,
            Response.choice_id,
            Response.is_correct,
            Response.points_awarded,
        )
        .where(Response.session_question_id == session_question_id)
        .order_by(Response.session_participant_id)
    ).all()
    stored_responses = [
        StoredQuestionResponse(
            session_participant_id=session_participant_id,
            choice_id=choice_id,
            is_correct=is_correct,
            points_awarded=points_awarded,
        )
        for (
            session_participant_id,
            choice_id,
            is_correct,
            points_awarded,
        ) in response_rows
    ]
    response_counts = Counter(
        response.choice_id
        for response in stored_responses
        if response.choice_id is not None
    )
    choice_results = [
        AnswerChoiceResult(
            choice_id=choice.choice_id,
            response_count=response_counts[choice.choice_id],
            is_correct=choice.is_correct,
        )
        for choice in answer_choices
    ]

    return ClosedQuestionResultData(
        session_id=session_id,
        session_question_id=session_question_id,
        correct_choice_ids=[
            choice.choice_id for choice in answer_choices if choice.is_correct
        ],
        choices=choice_results,
        responses=stored_responses,
    )


def get_closed_question_results(
    db: Session,
    session_id: int,
    session_question_id: int,
) -> ClosedQuestionResultsSnapshot:
    result_data = get_closed_question_result_data(
        db,
        session_id,
        session_question_id,
    )
    participant_rows = db.execute(
        select(
            SessionParticipant.session_participant_id,
            Account.display_name,
        )
        .join(Account, Account.account_id == SessionParticipant.account_id)
        .where(SessionParticipant.session_id == session_id)
    ).all()
    cumulative_score_rows = db.execute(
        select(
            Response.session_participant_id,
            func.sum(Response.points_awarded),
        )
        .join(
            SessionQuestion,
            SessionQuestion.session_question_id == Response.session_question_id,
        )
        .join(
            SessionParticipant,
            SessionParticipant.session_participant_id
            == Response.session_participant_id,
        )
        .where(
            SessionParticipant.session_id == session_id,
            SessionQuestion.session_id == session_id,
            SessionQuestion.status == SessionQuestionStatus.CLOSED,
        )
        .group_by(Response.session_participant_id)
    ).all()

    current_response_by_participant = {
        response.session_participant_id: response
        for response in result_data.responses
    }
    cumulative_score_by_participant = {
        session_participant_id: int(cumulative_score)
        for session_participant_id, cumulative_score in cumulative_score_rows
    }
    unranked_participants = []
    for session_participant_id, display_name in participant_rows:
        response = current_response_by_participant.get(session_participant_id)
        unranked_participants.append(
            UnrankedParticipantResult(
                session_participant_id=session_participant_id,
                display_name=display_name,
                selected_choice_id=response.choice_id if response else None,
                is_correct=response.is_correct if response else False,
                points_awarded=response.points_awarded if response else 0,
                cumulative_score=cumulative_score_by_participant.get(
                    session_participant_id, 0
                ),
            )
        )

    unranked_participants.sort(
        key=lambda participant: (
            -participant.cumulative_score,
            participant.display_name.casefold(),
            participant.display_name,
            participant.session_participant_id,
        )
    )
    participants = []
    previous_score: int | None = None
    previous_rank = 0
    for position, participant in enumerate(unranked_participants, start=1):
        if participant.cumulative_score != previous_score:
            previous_rank = position
            previous_score = participant.cumulative_score
        participants.append(
            ParticipantQuestionResult(
                session_participant_id=participant.session_participant_id,
                display_name=participant.display_name,
                selected_choice_id=participant.selected_choice_id,
                is_correct=participant.is_correct,
                points_awarded=participant.points_awarded,
                cumulative_score=participant.cumulative_score,
                rank=previous_rank,
            )
        )

    return ClosedQuestionResultsSnapshot(
        session_id=result_data.session_id,
        session_question_id=result_data.session_question_id,
        correct_choice_ids=result_data.correct_choice_ids,
        choices=result_data.choices,
        participants=participants,
    )
