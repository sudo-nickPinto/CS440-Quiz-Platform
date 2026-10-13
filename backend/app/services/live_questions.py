from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    LiveSession,
    LiveSessionStatus,
    Question,
    Response,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.schemas.live_question import (
    QuestionChoiceEvent,
    QuestionClosedEvent,
    QuestionCloseReason,
    QuestionOpenedEvent,
)


@dataclass(frozen=True, slots=True)
class AnswerProgress:
    eligible_count: int
    answered_count: int

    @property
    def everyone_answered(self) -> bool:
        return self.eligible_count > 0 and self.answered_count == self.eligible_count


def _utc_now() -> datetime:
    """Return naive UTC to match the project's MySQL DATETIME columns."""
    now = datetime.now(UTC).replace(tzinfo=None)
    return _stored_time(now)


def _stored_time(value: datetime) -> datetime:
    """Match the millisecond precision of the persisted MySQL timestamps."""
    return value.replace(microsecond=(value.microsecond // 1_000) * 1_000)


def answer_progress(
    db: Session,
    session_id: int,
    session_question_id: int,
) -> AnswerProgress:
    """Count answers against the participant roster frozen at opening time."""
    session_question = db.scalar(
        select(SessionQuestion).where(
            SessionQuestion.session_question_id == session_question_id,
            SessionQuestion.session_id == session_id,
        )
    )
    if session_question is None:
        raise APIError(
            404,
            "session_question_not_found",
            "The question was not found in this session.",
        )
    if session_question.opened_at is None:
        raise APIError(
            409,
            "question_not_opened",
            "Answer progress is unavailable before the question opens.",
        )

    opened_at = session_question.opened_at
    eligible_count, answered_count = db.execute(
        select(
            func.count(
                func.distinct(SessionParticipant.session_participant_id)
            ),
            func.count(func.distinct(Response.session_participant_id)),
        )
        .select_from(SessionParticipant)
        .outerjoin(
            Response,
            and_(
                Response.session_participant_id
                == SessionParticipant.session_participant_id,
                Response.session_question_id == session_question_id,
            ),
        )
        .where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.joined_at <= opened_at,
            or_(
                SessionParticipant.left_at.is_(None),
                SessionParticipant.left_at >= opened_at,
            ),
        )
    ).one()

    return AnswerProgress(
        eligible_count=int(eligible_count),
        answered_count=int(answered_count),
    )


def _close_question_if_ready(
    db: Session,
    session_id: int,
    session_question_id: int,
    checked_at: datetime | None,
) -> QuestionClosedEvent | None:
    target = db.execute(
        select(SessionQuestion, Question.question_order)
        .join(Question, Question.question_id == SessionQuestion.question_id)
        .where(
            SessionQuestion.session_question_id == session_question_id,
            SessionQuestion.session_id == session_id,
        )
    ).one_or_none()
    if target is None:
        raise APIError(
            404,
            "session_question_not_found",
            "The question was not found in this session.",
        )

    session_question, question_order = target
    if session_question.status != SessionQuestionStatus.OPEN:
        return None
    if (
        session_question.opened_at is None
        or session_question.closes_at is None
        or session_question.closes_at <= session_question.opened_at
    ):
        raise APIError(
            500,
            "invalid_question_timing",
            "The open question does not have valid server timestamps.",
        )

    effective_checked_at = _stored_time(
        checked_at if checked_at is not None else _utc_now()
    )
    if effective_checked_at < session_question.opened_at:
        raise APIError(
            500,
            "invalid_question_timing",
            "The closure check cannot be earlier than the opening time.",
        )

    progress = answer_progress(db, session_id, session_question_id)
    if effective_checked_at >= session_question.closes_at:
        reason = QuestionCloseReason.DEADLINE
    elif progress.everyone_answered:
        reason = QuestionCloseReason.ALL_ANSWERED
    else:
        return None

    event = QuestionClosedEvent(
        session_id=session_id,
        session_question_id=session_question_id,
        question_order=question_order,
        reason=reason,
        answered_count=progress.answered_count,
        eligible_count=progress.eligible_count,
        opened_at=session_question.opened_at,
        closes_at=session_question.closes_at,
        closed_at=effective_checked_at,
    )
    transition = db.execute(
        update(SessionQuestion)
        .where(
            SessionQuestion.session_question_id == session_question_id,
            SessionQuestion.session_id == session_id,
            SessionQuestion.status == SessionQuestionStatus.OPEN,
        )
        .values(
            status=SessionQuestionStatus.CLOSED,
            closed_at=effective_checked_at,
        )
        .execution_options(synchronize_session=False)
    )
    if transition.rowcount != 1:
        db.rollback()
        return None

    db.commit()
    return event


def close_question_if_ready(
    db: Session,
    session_id: int,
    session_question_id: int,
    *,
    checked_at: datetime | None = None,
) -> QuestionClosedEvent | None:
    """Close an open question once when answers or its deadline make it ready."""
    try:
        return _close_question_if_ready(
            db,
            session_id,
            session_question_id,
            checked_at,
        )
    except APIError:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "question_close_failed",
            "Could not close the question.",
        ) from exc


def _opened_event(
    session_question: SessionQuestion,
    question: Question,
    total_questions: int,
) -> QuestionOpenedEvent:
    if session_question.opened_at is None or session_question.closes_at is None:
        raise APIError(
            500,
            "invalid_question_timing",
            "The open question does not have valid server timestamps.",
        )

    return QuestionOpenedEvent(
        session_id=session_question.session_id,
        session_question_id=session_question.session_question_id,
        question_order=question.question_order,
        total_questions=total_questions,
        question_text=question.question_text,
        choices=[
            QuestionChoiceEvent(
                choice_id=choice.choice_id,
                choice_order=choice.choice_order,
                choice_text=choice.choice_text,
            )
            for choice in sorted(
                question.choices,
                key=lambda choice: (choice.choice_order, choice.choice_id),
            )
        ],
        opened_at=session_question.opened_at,
        closes_at=session_question.closes_at,
    )


def _open_question(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    question_order: int,
    opened_at: datetime | None,
) -> QuestionOpenedEvent:
    session = db.scalar(
        select(LiveSession)
        .where(LiveSession.session_id == session_id)
        .with_for_update()
    )
    if session is None:
        raise APIError(404, "session_not_found", "Session not found.")
    if session.host_id != account.account_id:
        raise APIError(
            403,
            "session_host_denied",
            "Only this session's host can open questions.",
        )
    if session.status not in (
        LiveSessionStatus.LOBBY,
        LiveSessionStatus.ACTIVE,
    ):
        raise APIError(
            409,
            "session_not_openable",
            "Completed or cancelled sessions cannot open questions.",
        )

    question = db.scalar(
        select(Question)
        .where(
            Question.quiz_version_id == session.quiz_version_id,
            Question.question_order == question_order,
        )
        .options(selectinload(Question.choices))
    )
    if question is None:
        raise APIError(
            404,
            "question_not_found",
            "That question order does not exist in this session's quiz.",
        )

    total_questions = int(
        db.scalar(
            select(func.count(Question.question_id)).where(
                Question.quiz_version_id == session.quiz_version_id
            )
        )
        or 0
    )
    existing = db.scalar(
        select(SessionQuestion).where(
            SessionQuestion.session_id == session_id,
            SessionQuestion.question_id == question.question_id,
        )
    )
    if existing is not None:
        if existing.status == SessionQuestionStatus.OPEN:
            return _opened_event(existing, question, total_questions)
        if existing.status == SessionQuestionStatus.CLOSED:
            raise APIError(
                409,
                "question_already_closed",
                "A closed question cannot be reopened.",
            )

    open_question_id = db.scalar(
        select(SessionQuestion.session_question_id).where(
            SessionQuestion.session_id == session_id,
            SessionQuestion.status == SessionQuestionStatus.OPEN,
        )
    )
    if open_question_id is not None:
        raise APIError(
            409,
            "question_already_open",
            "Close the current question before opening another one.",
        )

    expected_order = (
        1
        if session.current_question_order is None
        else session.current_question_order + 1
    )
    if question_order != expected_order:
        raise APIError(
            409,
            "question_order_invalid",
            "Questions must open in order without being skipped.",
        )

    if question_order == 1:
        active_participant_id = db.scalar(
            select(SessionParticipant.session_participant_id)
            .where(
                SessionParticipant.session_id == session_id,
                SessionParticipant.left_at.is_(None),
            )
            .limit(1)
        )
        if active_participant_id is None:
            raise APIError(
                409,
                "session_has_no_participants",
                "At least one active participant is required to start the quiz.",
            )
    else:
        previous_status = db.scalar(
            select(SessionQuestion.status)
            .join(Question, Question.question_id == SessionQuestion.question_id)
            .where(
                SessionQuestion.session_id == session_id,
                Question.question_order == question_order - 1,
            )
        )
        if previous_status != SessionQuestionStatus.CLOSED:
            raise APIError(
                409,
                "previous_question_not_closed",
                "The previous question must be closed first.",
            )

    effective_opened_at = _stored_time(
        opened_at if opened_at is not None else _utc_now()
    )
    closes_at = effective_opened_at + timedelta(
        seconds=question.time_limit_seconds
    )
    if existing is None:
        existing = SessionQuestion(
            session_id=session_id,
            question_id=question.question_id,
        )
        db.add(existing)
    existing.status = SessionQuestionStatus.OPEN
    existing.opened_at = effective_opened_at
    existing.closes_at = closes_at
    existing.closed_at = None

    if question_order == 1 and session.status == LiveSessionStatus.LOBBY:
        session.status = LiveSessionStatus.ACTIVE
        session.started_at = effective_opened_at
    session.current_question_order = question_order

    db.flush()
    event = _opened_event(existing, question, total_questions)
    db.commit()
    return event


def open_question(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    question_order: int,
    *,
    opened_at: datetime | None = None,
) -> QuestionOpenedEvent:
    """Open one quiz question using timestamps owned by the server."""
    try:
        return _open_question(
            db,
            account,
            session_id,
            question_order,
            opened_at,
        )
    except APIError:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "question_open_failed",
            "Could not open the question.",
        ) from exc
