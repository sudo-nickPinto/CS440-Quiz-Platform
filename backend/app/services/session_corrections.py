from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    AnswerChoice,
    LiveSession,
    LiveSessionStatus,
    Question,
    Response,
    Result,
    SessionCorrectionMode,
    SessionAnswerCorrection,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionCorrectChoice,
    SessionQuestionStatus,
)
from app.schemas.session_correction import (
    CorrectChoiceSummary,
    SessionAnswerCorrectionResult,
)
from app.services.class_authorization import require_class_organizer
from app.services.scoring import calculate_points
from app.services.session_end import compute_final_standings


@dataclass(frozen=True)
class CorrectionContext:
    session: LiveSession
    session_question: SessionQuestion
    question: Question
    current_choices: tuple[AnswerChoice, ...]
    proposed_choice: AnswerChoice


def _utc_now() -> datetime:
    now = datetime.now(UTC).replace(tzinfo=None)
    return now.replace(microsecond=(now.microsecond // 1_000) * 1_000)


def can_correct_session(
    db: Session, account: CurrentAccount, session: LiveSession
) -> bool:
    if session.class_id is None or session.status != LiveSessionStatus.COMPLETED:
        return False
    try:
        require_class_organizer(db, account, session.class_id)
    except APIError:
        return False
    return True


def _load_context(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    session_question_id: int,
    proposed_choice_id: int,
    *,
    lock: bool,
) -> CorrectionContext:
    session_query = select(LiveSession).where(LiveSession.session_id == session_id)
    if lock:
        session_query = session_query.with_for_update()
    session = db.scalar(session_query)
    if session is None:
        raise APIError(404, "session_not_found", "Session not found.")
    if session.status != LiveSessionStatus.COMPLETED:
        raise APIError(
            409,
            "session_not_completed",
            "Correct answers can only be changed after a session is completed.",
        )
    if session.class_id is None:
        raise APIError(
            409,
            "session_class_required",
            "This historical session is not attached to a class.",
        )
    require_class_organizer(db, account, session.class_id)

    question_query = select(SessionQuestion).where(
        SessionQuestion.session_question_id == session_question_id,
        SessionQuestion.session_id == session_id,
    )
    if lock:
        question_query = question_query.with_for_update()
    session_question = db.scalar(question_query)
    if session_question is None:
        raise APIError(
            404, "session_question_not_found", "Session question not found."
        )
    if session_question.status != SessionQuestionStatus.CLOSED:
        raise APIError(
            409,
            "session_question_not_closed",
            "Only a played and closed question can be corrected.",
        )

    question = db.get(Question, session_question.question_id)
    if question is None:
        raise APIError(500, "results_incomplete", "The question is unavailable.")

    choices = list(
        db.scalars(
            select(AnswerChoice)
            .where(AnswerChoice.question_id == question.question_id)
            .order_by(AnswerChoice.choice_order)
        ).all()
    )
    proposed = next(
        (choice for choice in choices if choice.choice_id == proposed_choice_id),
        None,
    )
    if proposed is None:
        raise APIError(
            422,
            "choice_not_in_question",
            "The proposed answer choice does not belong to this question.",
        )

    override_ids = set(
        db.scalars(
            select(SessionQuestionCorrectChoice.choice_id).where(
                SessionQuestionCorrectChoice.session_question_id
                == session_question_id
            )
        ).all()
    )
    current = tuple(
        choice
        for choice in choices
        if (
            choice.choice_id in override_ids
            if override_ids
            else choice.is_correct
        )
    )
    if not current:
        raise APIError(
            500,
            "results_incomplete",
            "The session question does not have an effective correct answer.",
        )

    return CorrectionContext(
        session=session,
        session_question=session_question,
        question=question,
        current_choices=current,
        proposed_choice=proposed,
    )


def correct_session_answer(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    session_question_id: int,
    proposed_choice_id: int,
    mode: SessionCorrectionMode,
    expected_score_revision: int,
) -> SessionAnswerCorrectionResult:
    try:
        context = _load_context(
            db,
            account,
            session_id,
            session_question_id,
            proposed_choice_id,
            lock=True,
        )
        if context.session.score_revision != expected_score_revision:
            raise APIError(
                409,
                "score_revision_conflict",
                "The session was rescored after this report was loaded.",
                details={"current_revision": context.session.score_revision},
            )

        previous_ids = [choice.choice_id for choice in context.current_choices]
        if mode == SessionCorrectionMode.ADD:
            if context.proposed_choice.choice_id in previous_ids:
                raise APIError(
                    409,
                    "correct_answer_unchanged",
                    "That answer is already accepted as correct.",
                )
            corrected_choices = (*context.current_choices, context.proposed_choice)
        elif mode == SessionCorrectionMode.REMOVE:
            if context.proposed_choice.choice_id not in previous_ids:
                raise APIError(
                    409,
                    "correct_answer_unchanged",
                    "Only an accepted answer can be removed.",
                )
            if len(context.current_choices) == 1:
                raise APIError(
                    409,
                    "last_correct_answer",
                    "At least one answer must remain correct.",
                )
            corrected_choices = tuple(
                choice
                for choice in context.current_choices
                if choice.choice_id != context.proposed_choice.choice_id
            )
        else:
            corrected_choices = (context.proposed_choice,)
            if previous_ids == [context.proposed_choice.choice_id]:
                raise APIError(
                    409,
                    "correct_answer_unchanged",
                    "Choose a different answer before rescoring the session.",
                )
        corrected_ids = [choice.choice_id for choice in corrected_choices]
        corrected_id_set = set(corrected_ids)

        corrected_at = _utc_now()
        new_revision = context.session.score_revision + 1

        responses = db.scalars(
            select(Response).where(
                Response.session_question_id == session_question_id
            )
        ).all()
        for response in responses:
            response.is_correct = response.choice_id in corrected_id_set
            response.points_awarded = calculate_points(
                is_correct=response.is_correct,
                response_time_ms=response.response_time_ms,
                time_limit_seconds=context.question.time_limit_seconds,
                max_points=context.question.base_points,
            )

        db.execute(
            delete(SessionQuestionCorrectChoice).where(
                SessionQuestionCorrectChoice.session_question_id
                == session_question_id
            )
        )
        db.add_all(
            SessionQuestionCorrectChoice(
                session_question_id=session_question_id,
                choice_id=choice_id,
            )
            for choice_id in corrected_ids
        )
        context.session.score_revision = new_revision
        context.session.rescored_at = corrected_at
        context.session.rescored_by_id = account.account_id
        audit = SessionAnswerCorrection(
            session_id=session_id,
            session_question_id=session_question_id,
            selected_choice_id=context.proposed_choice.choice_id,
            correction_mode=mode,
            previous_correct_choice_ids=previous_ids,
            corrected_choice_ids=corrected_ids,
            corrected_by_id=account.account_id,
            score_revision=new_revision,
            corrected_at=corrected_at,
        )
        db.add(audit)
        db.flush()

        standings = compute_final_standings(db, session_id)
        saved_results = {
            result.session_participant_id: result
            for result in db.scalars(
                select(Result)
                .join(
                    SessionParticipant,
                    SessionParticipant.session_participant_id
                    == Result.session_participant_id,
                )
                .where(SessionParticipant.session_id == session_id)
            ).all()
        }
        for standing in standings:
            result = saved_results.get(standing.session_participant_id)
            if result is None:
                raise APIError(
                    500,
                    "results_incomplete",
                    "A saved participant result is missing.",
                )
            result.total_score = standing.total_score
            result.correct_count = standing.correct_count
            result.final_rank = standing.final_rank
            result.computed_at = corrected_at

        db.commit()
        return SessionAnswerCorrectionResult(
            session_id=session_id,
            session_question_id=session_question_id,
            score_revision=new_revision,
            correction_id=audit.correction_id,
            correction_mode=mode,
            selected_choice=CorrectChoiceSummary(
                choice_id=context.proposed_choice.choice_id,
                text=context.proposed_choice.choice_text,
            ),
            previous_correct_choices=[
                CorrectChoiceSummary(choice_id=choice.choice_id, text=choice.choice_text)
                for choice in context.current_choices
            ],
            corrected_choices=[
                CorrectChoiceSummary(choice_id=choice.choice_id, text=choice.choice_text)
                for choice in corrected_choices
            ],
            corrected_at=corrected_at,
            corrected_by_id=account.account_id,
        )
    except APIError:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500, "session_rescore_failed", "Could not rescore the session."
        ) from exc
