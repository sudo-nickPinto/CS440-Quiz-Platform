from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    AnswerChoice,
    LiveSessionStatus,
    Response,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.schemas.response import ResponseReceipt, ResponseSubmit
from app.services.scoring import calculate_points


def _utc_now() -> datetime:
    """Return naive UTC to match the project's MySQL DATETIME columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def _duplicate_error() -> APIError:
    return APIError(
        409,
        "response_already_submitted",
        "Only the first response to a question is accepted.",
    )


def _response_time_ms(opened_at: datetime, submitted_at: datetime) -> int:
    elapsed = submitted_at - opened_at
    return (
        elapsed.days * 86_400_000
        + elapsed.seconds * 1_000
        + elapsed.microseconds // 1_000
    )


def _evaluate_response(
    session_question: SessionQuestion,
    choice: AnswerChoice,
    submitted_at: datetime,
) -> tuple[int, bool, int]:
    """Validate timing and return response time, correctness, and points."""
    if session_question.session.status != LiveSessionStatus.ACTIVE:
        raise APIError(409, "session_not_active", "The quiz session is not active.")
    if session_question.status != SessionQuestionStatus.OPEN:
        raise APIError(409, "question_not_open", "This question is not open.")
    if session_question.opened_at is None or session_question.closes_at is None:
        raise APIError(
            500,
            "invalid_question_timing",
            "The open question does not have valid server timestamps.",
        )
    if submitted_at < session_question.opened_at:
        raise APIError(
            500,
            "invalid_question_timing",
            "The response time is earlier than the question opening time.",
        )
    if submitted_at > session_question.closes_at:
        raise APIError(
            409,
            "response_deadline_passed",
            "The response arrived after the question deadline.",
        )
    if choice.question_id != session_question.question_id:
        raise APIError(
            422,
            "choice_not_for_question",
            "The selected choice does not belong to this question.",
        )

    response_time_ms = _response_time_ms(
        session_question.opened_at, submitted_at
    )
    is_correct = choice.is_correct
    try:
        points_awarded = calculate_points(
            is_correct=is_correct,
            response_time_ms=response_time_ms,
            time_limit_seconds=session_question.question.time_limit_seconds,
            max_points=session_question.question.base_points,
        )
    except ValueError as exc:
        raise APIError(
            500,
            "invalid_question_timing",
            "The question timing is inconsistent with its configured time limit.",
        ) from exc

    return response_time_ms, is_correct, points_awarded


def submit_response(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    session_question_id: int,
    payload: ResponseSubmit,
    *,
    submitted_at: datetime | None = None,
) -> ResponseReceipt:
    """Validate, score, and persist one multiple-choice response."""
    # Capture the server time at the beginning of request processing so database
    # query latency cannot turn an on-time response into a late response.
    received_at = submitted_at or _utc_now()

    participant = db.scalar(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.account_id == account.account_id,
            SessionParticipant.left_at.is_(None),
        )
    )
    if participant is None:
        raise APIError(
            403,
            "not_session_participant",
            "You are not an active participant in this session.",
        )
    participant_id = participant.session_participant_id

    session_question = db.scalar(
        select(SessionQuestion)
        .where(
            SessionQuestion.session_question_id == session_question_id,
            SessionQuestion.session_id == session_id,
        )
        .options(
            joinedload(SessionQuestion.session),
            joinedload(SessionQuestion.question),
        )
    )
    if session_question is None:
        raise APIError(
            404,
            "session_question_not_found",
            "The question was not found in this session.",
        )

    existing_response_id = db.scalar(
        select(Response.response_id).where(
            Response.session_participant_id
            == participant_id,
            Response.session_question_id == session_question_id,
        )
    )
    if existing_response_id is not None:
        raise _duplicate_error()

    choice = db.scalar(
        select(AnswerChoice).where(AnswerChoice.choice_id == payload.choice_id)
    )
    if choice is None or choice.question_id != session_question.question_id:
        raise APIError(
            422,
            "choice_not_for_question",
            "The selected choice does not belong to this question.",
        )

    response_time_ms, is_correct, points_awarded = _evaluate_response(
        session_question, choice, received_at
    )
    response = Response(
        session_participant_id=participant_id,
        session_question_id=session_question_id,
        choice_id=choice.choice_id,
        submitted_at=received_at,
        response_time_ms=response_time_ms,
        is_correct=is_correct,
        points_awarded=points_awarded,
    )
    db.add(response)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        duplicate = db.scalar(
            select(Response.response_id).where(
                Response.session_participant_id
                == participant_id,
                Response.session_question_id == session_question_id,
            )
        )
        if duplicate is not None:
            raise _duplicate_error() from exc
        raise
    except SQLAlchemyError:
        db.rollback()
        raise

    db.refresh(response)
    return ResponseReceipt.model_validate(response)
