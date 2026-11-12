from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    Account,
    AnswerChoice,
    LiveSession,
    LiveSessionStatus,
    Question,
    Response,
    Result,
    SessionAnswerCorrection,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.schemas.session_correction import (
    CorrectChoiceSummary,
    ParticipantRescorePreview,
    SessionAnswerCorrectionPreview,
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
    current_choice: AnswerChoice
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

    if session_question.corrected_choice_id is not None:
        current = next(
            (
                choice
                for choice in choices
                if choice.choice_id == session_question.corrected_choice_id
            ),
            None,
        )
    else:
        original = [choice for choice in choices if choice.is_correct]
        current = original[0] if len(original) == 1 else None
    if current is None:
        raise APIError(
            500,
            "results_incomplete",
            "The session question does not have exactly one effective correct answer.",
        )
    if current.choice_id == proposed.choice_id:
        raise APIError(
            409,
            "correct_answer_unchanged",
            "Choose a different answer before previewing a rescore.",
        )

    return CorrectionContext(
        session=session,
        session_question=session_question,
        question=question,
        current_choice=current,
        proposed_choice=proposed,
    )


def _rank_by_score(rows: list[tuple[int, str, int]]) -> dict[int, int]:
    ordered = sorted(rows, key=lambda row: (-row[2], row[1].casefold(), row[1], row[0]))
    ranks: dict[int, int] = {}
    previous_score: int | None = None
    rank = 0
    for position, (participant_id, _, score) in enumerate(ordered, start=1):
        if score != previous_score:
            rank = position
            previous_score = score
        ranks[participant_id] = rank
    return ranks


def _build_preview(
    db: Session, context: CorrectionContext
) -> SessionAnswerCorrectionPreview:
    result_rows = db.execute(
        select(
            SessionParticipant.session_participant_id,
            Account.display_name,
            Result.total_score,
            Result.correct_count,
            Result.final_rank,
        )
        .join(
            Account, Account.account_id == SessionParticipant.account_id
        )
        .join(
            Result,
            Result.session_participant_id
            == SessionParticipant.session_participant_id,
        )
        .where(SessionParticipant.session_id == context.session.session_id)
    ).all()
    if not result_rows:
        raise APIError(
            500, "results_incomplete", "This completed session has no saved results."
        )

    responses = {
        response.session_participant_id: response
        for response in db.scalars(
            select(Response).where(
                Response.session_question_id
                == context.session_question.session_question_id
            )
        ).all()
    }

    projected: dict[int, tuple[bool, int, int, int]] = {}
    new_rank_rows: list[tuple[int, str, int]] = []
    for row in result_rows:
        response = responses.get(row.session_participant_id)
        old_correct = bool(response.is_correct) if response else False
        old_points = int(response.points_awarded) if response else 0
        new_correct = bool(
            response and response.choice_id == context.proposed_choice.choice_id
        )
        new_points = (
            calculate_points(
                is_correct=new_correct,
                response_time_ms=response.response_time_ms,
                time_limit_seconds=context.question.time_limit_seconds,
                max_points=context.question.base_points,
            )
            if response
            else 0
        )
        new_total = int(row.total_score) - old_points + new_points
        new_correct_count = int(row.correct_count) - int(old_correct) + int(new_correct)
        projected[row.session_participant_id] = (
            new_correct,
            new_points,
            new_total,
            new_correct_count,
        )
        new_rank_rows.append(
            (row.session_participant_id, row.display_name, new_total)
        )

    new_ranks = _rank_by_score(new_rank_rows)
    affected: list[ParticipantRescorePreview] = []
    for row in result_rows:
        response = responses.get(row.session_participant_id)
        old_correct = bool(response.is_correct) if response else False
        old_points = int(response.points_awarded) if response else 0
        new_correct, new_points, new_total, _ = projected[
            row.session_participant_id
        ]
        new_rank = new_ranks[row.session_participant_id]
        if (
            old_correct == new_correct
            and old_points == new_points
            and int(row.total_score) == new_total
            and int(row.final_rank) == new_rank
        ):
            continue
        affected.append(
            ParticipantRescorePreview(
                session_participant_id=row.session_participant_id,
                display_name=row.display_name,
                old_correct=old_correct,
                new_correct=new_correct,
                old_question_points=old_points,
                new_question_points=new_points,
                old_total_score=int(row.total_score),
                new_total_score=new_total,
                old_rank=int(row.final_rank),
                new_rank=new_rank,
            )
        )

    affected.sort(key=lambda item: (item.new_rank, item.display_name.casefold()))
    return SessionAnswerCorrectionPreview(
        session_id=context.session.session_id,
        session_question_id=context.session_question.session_question_id,
        question_order=context.question.question_order,
        question_text=context.question.question_text,
        score_revision=context.session.score_revision,
        current_correct_choice=CorrectChoiceSummary(
            choice_id=context.current_choice.choice_id,
            text=context.current_choice.choice_text,
        ),
        proposed_correct_choice=CorrectChoiceSummary(
            choice_id=context.proposed_choice.choice_id,
            text=context.proposed_choice.choice_text,
        ),
        affected_response_count=sum(
            1
            for item in affected
            if item.old_correct != item.new_correct
            or item.old_question_points != item.new_question_points
        ),
        affected_participants=affected,
    )


def preview_session_answer_correction(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    session_question_id: int,
    proposed_choice_id: int,
) -> SessionAnswerCorrectionPreview:
    context = _load_context(
        db,
        account,
        session_id,
        session_question_id,
        proposed_choice_id,
        lock=False,
    )
    return _build_preview(db, context)


def correct_session_answer(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    session_question_id: int,
    proposed_choice_id: int,
    reason: str,
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
                "The session was rescored after this preview was loaded.",
                details={"current_revision": context.session.score_revision},
            )

        preview = _build_preview(db, context)
        corrected_at = _utc_now()
        new_revision = context.session.score_revision + 1

        responses = db.scalars(
            select(Response).where(
                Response.session_question_id == session_question_id
            )
        ).all()
        for response in responses:
            response.is_correct = (
                response.choice_id == context.proposed_choice.choice_id
            )
            response.points_awarded = calculate_points(
                is_correct=response.is_correct,
                response_time_ms=response.response_time_ms,
                time_limit_seconds=context.question.time_limit_seconds,
                max_points=context.question.base_points,
            )

        context.session_question.corrected_choice_id = (
            context.proposed_choice.choice_id
        )
        context.session.score_revision = new_revision
        context.session.rescored_at = corrected_at
        context.session.rescored_by_id = account.account_id
        audit = SessionAnswerCorrection(
            session_id=session_id,
            session_question_id=session_question_id,
            previous_correct_choice_id=context.current_choice.choice_id,
            corrected_choice_id=context.proposed_choice.choice_id,
            reason=reason,
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
            **preview.model_dump(exclude={"score_revision"}),
            score_revision=new_revision,
            correction_id=audit.correction_id,
            corrected_at=corrected_at,
            corrected_by_id=account.account_id,
            reason=reason,
        )
    except APIError:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500, "session_rescore_failed", "Could not rescore the session."
        ) from exc
