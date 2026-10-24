from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    Account,
    LiveSession,
    LiveSessionStatus,
    Response,
    Result,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.schemas.live_question import QuestionClosedEvent
from app.schemas.results import FinalResults, FinalStanding
from app.services.live_questions import close_open_question_for_host

ENDED_STATUSES = (LiveSessionStatus.COMPLETED, LiveSessionStatus.CANCELLED)


@dataclass(frozen=True)
class SessionEnded:
    """What the hub broadcasts after end_session() commits."""

    closed_question: QuestionClosedEvent | None
    results: FinalResults


@dataclass(frozen=True)
class ParticipantLeft:
    session_id: int
    session_participant_id: int
    display_name: str
    participant_count: int


def _utc_now() -> datetime:
    now = datetime.now(UTC).replace(tzinfo=None)
    return now.replace(microsecond=(now.microsecond // 1_000) * 1_000)


def _lock_session(db: Session, session_id: int) -> LiveSession | None:
    return db.scalar(
        select(LiveSession)
        .where(LiveSession.session_id == session_id)
        .with_for_update()
    )


def _lock_hosted_session(
    db: Session, account: CurrentAccount, session_id: int
) -> LiveSession:
    session = _lock_session(db, session_id)
    if session is None:
        raise APIError(404, "session_not_found", "Session not found.")
    if session.host_id != account.account_id:
        raise APIError(
            403,
            "session_host_denied",
            "Only this session's host can do that.",
        )
    if session.status in ENDED_STATUSES:
        raise APIError(
            409,
            "session_already_ended",
            "This session has already ended.",
        )
    return session


def compute_final_standings(db: Session, session_id: int) -> list[FinalStanding]:
    """Rank every participant by total score, with RANK() ties (1, 1, 3).

    Ordering within a tie matches the running leaderboard in results.py, so
    the final board never reshuffles people the last question left tied.
    """
    participants = db.execute(
        select(SessionParticipant.session_participant_id, Account.display_name)
        .join(Account, Account.account_id == SessionParticipant.account_id)
        .where(SessionParticipant.session_id == session_id)
    ).all()
    totals = {
        session_participant_id: (int(score or 0), int(correct or 0))
        for session_participant_id, score, correct in db.execute(
            select(
                Response.session_participant_id,
                func.sum(Response.points_awarded),
                func.sum(case((Response.is_correct, 1), else_=0)),
            )
            .join(
                SessionQuestion,
                SessionQuestion.session_question_id == Response.session_question_id,
            )
            .where(
                SessionQuestion.session_id == session_id,
                SessionQuestion.status == SessionQuestionStatus.CLOSED,
            )
            .group_by(Response.session_participant_id)
        ).all()
    }

    rows = sorted(
        (
            (
                session_participant_id,
                display_name,
                *totals.get(session_participant_id, (0, 0)),
            )
            for session_participant_id, display_name in participants
        ),
        key=lambda row: (-row[2], row[1].casefold(), row[1], row[0]),
    )
    standings = []
    previous_score: int | None = None
    rank = 0
    for position, (participant_id, name, score, correct) in enumerate(rows, start=1):
        if score != previous_score:
            rank = position
            previous_score = score
        standings.append(
            FinalStanding(
                session_participant_id=participant_id,
                display_name=name,
                total_score=score,
                correct_count=correct,
                final_rank=rank,
            )
        )
    return standings


def _end_session(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    ended_at: datetime,
) -> SessionEnded:
    session = _lock_hosted_session(db, account, session_id)
    if session.status != LiveSessionStatus.ACTIVE:
        raise APIError(
            409,
            "session_not_started",
            "Start the quiz before ending it, or cancel it instead.",
        )
    return _complete_session(db, session, ended_at)


def _complete_session(
    db: Session, session: LiveSession, ended_at: datetime
) -> SessionEnded:
    """Close any open question, write results, and mark the locked ACTIVE
    session COMPLETED. Commits."""
    session_id = session.session_id
    closed_question = None
    open_question_id = db.scalar(
        select(SessionQuestion.session_question_id).where(
            SessionQuestion.session_id == session_id,
            SessionQuestion.status == SessionQuestionStatus.OPEN,
        )
    )
    if open_question_id is not None:
        # None here means an answer or the deadline closed it a moment ago;
        # that path broadcasts its own question_closed.
        closed_question = close_open_question_for_host(
            db, session_id, open_question_id, ended_at
        )

    standings = compute_final_standings(db, session_id)
    db.add_all(
        Result(
            session_participant_id=row.session_participant_id,
            total_score=row.total_score,
            correct_count=row.correct_count,
            final_rank=row.final_rank,
            computed_at=ended_at,
        )
        for row in standings
    )
    session.status = LiveSessionStatus.COMPLETED
    session.ended_at = ended_at
    db.commit()

    return SessionEnded(
        closed_question=closed_question,
        results=FinalResults(
            session_id=session_id,
            status=LiveSessionStatus.COMPLETED.value,
            ended_at=ended_at,
            standings=standings,
        ),
    )


def _run(db: Session, error_code: str, message: str, fn, *args):
    try:
        return fn(db, *args)
    except APIError:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, error_code, message) from exc


def end_session(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    *,
    ended_at: datetime | None = None,
) -> SessionEnded:
    """Host ends an ACTIVE session: close any open question, write the final
    result rows, and mark it COMPLETED, all in one transaction."""
    return _run(
        db,
        "session_end_failed",
        "Could not end the session.",
        _end_session,
        account,
        session_id,
        ended_at or _utc_now(),
    )


def _cancel_session(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    ended_at: datetime,
) -> FinalResults:
    session = _lock_hosted_session(db, account, session_id)
    if session.status != LiveSessionStatus.LOBBY:
        raise APIError(
            409,
            "session_not_cancellable",
            "Only a session that has not started can be cancelled. End it instead.",
        )
    return _mark_cancelled(db, session, ended_at)


def _mark_cancelled(
    db: Session, session: LiveSession, ended_at: datetime
) -> FinalResults:
    session_id = session.session_id
    session.status = LiveSessionStatus.CANCELLED
    session.ended_at = ended_at
    db.commit()
    return FinalResults(
        session_id=session_id,
        status=LiveSessionStatus.CANCELLED.value,
        ended_at=ended_at,
        standings=[],
    )


def cancel_session(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    *,
    ended_at: datetime | None = None,
) -> FinalResults:
    """Host cancels a session still in the LOBBY."""
    return _run(
        db,
        "session_cancel_failed",
        "Could not cancel the session.",
        _cancel_session,
        account,
        session_id,
        ended_at or _utc_now(),
    )


def live_session_ids(db: Session) -> list[int]:
    """Every LOBBY or ACTIVE session, for the abandoned-session reaper."""
    return list(
        db.scalars(
            select(LiveSession.session_id).where(
                LiveSession.status.in_(
                    (LiveSessionStatus.LOBBY, LiveSessionStatus.ACTIVE)
                )
            )
        )
    )


def _abandon_session(
    db: Session, session_id: int, ended_at: datetime
) -> SessionEnded | None:
    session = _lock_session(db, session_id)
    if session is None or session.status in ENDED_STATUSES:
        db.rollback()
        return None
    if session.status == LiveSessionStatus.LOBBY:
        return SessionEnded(
            closed_question=None,
            results=_mark_cancelled(db, session, ended_at),
        )
    return _complete_session(db, session, ended_at)


def abandon_session(
    db: Session,
    session_id: int,
    *,
    ended_at: datetime | None = None,
) -> SessionEnded | None:
    """End a session whose host has gone (system action, no host check).

    A LOBBY session is CANCELLED; an ACTIVE one is ended exactly as the host's
    End would. Returns None if it already ended.
    """
    return _run(
        db,
        "session_end_failed",
        "Could not end the session.",
        _abandon_session,
        session_id,
        ended_at or _utc_now(),
    )


def _leave_session(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    left_at: datetime,
) -> ParticipantLeft:
    # Lock the session so a leave can't interleave with end_session's results.
    session = db.scalar(
        select(LiveSession)
        .where(LiveSession.session_id == session_id)
        .with_for_update()
    )
    if session is None:
        raise APIError(404, "session_not_found", "Session not found.")
    if session.status in ENDED_STATUSES:
        raise APIError(
            409,
            "session_already_ended",
            "This session has already ended.",
        )

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
            "session_access_denied",
            "You are not a participant in this session.",
        )
    participant.left_at = left_at
    db.flush()

    display_name = db.scalar(
        select(Account.display_name).where(Account.account_id == account.account_id)
    )
    participant_count = int(
        db.scalar(
            select(func.count(SessionParticipant.session_participant_id)).where(
                SessionParticipant.session_id == session_id,
                SessionParticipant.left_at.is_(None),
            )
        )
        or 0
    )
    left = ParticipantLeft(
        session_id=session_id,
        session_participant_id=participant.session_participant_id,
        display_name=display_name or "",
        participant_count=participant_count,
    )
    db.commit()
    return left


def leave_session(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    *,
    left_at: datetime | None = None,
) -> ParticipantLeft:
    """A participant leaves. They still count for the question that is open
    now, and drop out of the roster from the next question (§5)."""
    return _run(
        db,
        "session_leave_failed",
        "Could not leave the session.",
        _leave_session,
        account,
        session_id,
        left_at or _utc_now(),
    )


def get_final_results(
    db: Session,
    account: CurrentAccount,
    session_id: int,
) -> tuple[FinalResults, int | None]:
    """Stored final results plus the caller's session_participant_id.

    The caller's participant id is None for the host or an Admin, who see
    every row; the route cuts the rows down for participants.
    """
    session = db.get(LiveSession, session_id)
    if session is None:
        raise APIError(404, "session_not_found", "Session not found.")

    viewer_participant_id = None
    if session.host_id != account.account_id and not account.is_admin:
        # Anyone who played sees the results, even if they left early.
        viewer_participant_id = db.scalar(
            select(SessionParticipant.session_participant_id).where(
                SessionParticipant.session_id == session_id,
                SessionParticipant.account_id == account.account_id,
            )
        )
        if viewer_participant_id is None:
            raise APIError(
                403,
                "session_access_denied",
                "You cannot access this session.",
            )

    if session.status not in ENDED_STATUSES:
        raise APIError(
            409,
            "results_not_ready",
            "Final results are available once the session ends.",
        )

    rows = db.execute(
        select(
            Result.session_participant_id,
            Account.display_name,
            Result.total_score,
            Result.correct_count,
            Result.final_rank,
        )
        .join(
            SessionParticipant,
            SessionParticipant.session_participant_id == Result.session_participant_id,
        )
        .join(Account, Account.account_id == SessionParticipant.account_id)
        .where(SessionParticipant.session_id == session_id)
    ).all()
    standings = sorted(
        (
            FinalStanding(
                session_participant_id=row.session_participant_id,
                display_name=row.display_name,
                total_score=row.total_score,
                correct_count=row.correct_count,
                final_rank=row.final_rank,
            )
            for row in rows
        ),
        key=lambda row: (
            row.final_rank,
            row.display_name.casefold(),
            row.display_name,
            row.session_participant_id,
        ),
    )
    return (
        FinalResults(
            session_id=session_id,
            status=session.status.value,
            ended_at=session.ended_at,
            standings=standings,
        ),
        viewer_participant_id,
    )
