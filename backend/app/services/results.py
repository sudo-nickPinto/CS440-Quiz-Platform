from collections import Counter
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import APIError
from app.models import AnswerChoice, Response, SessionQuestion, SessionQuestionStatus
from app.schemas.results import AnswerChoiceResult


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
