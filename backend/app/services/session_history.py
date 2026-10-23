from datetime import UTC, datetime

from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    Account,
    LiveSession,
    LiveSessionStatus,
    Quiz,
    QuizVersion,
    SessionParticipant,
    Result,
    SessionQuestion,
    SessionQuestionStatus,
)


def _date(value: datetime | None) -> str | None:
    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.isoformat()


def _history_query():
    # Use the version attached to the session, not the quiz's latest version.
    return (
        select(
            LiveSession,
            QuizVersion.quiz_id,
            QuizVersion.title,
            QuizVersion.version_number,
            Account.display_name.label("host_name"),
        )
        .join(
            QuizVersion,
            QuizVersion.quiz_version_id == LiveSession.quiz_version_id,
        )
        .join(Account, Account.account_id == LiveSession.host_id)
    )


def _page(db: Session, statement, limit: int, offset: int) -> dict:
    rows = db.execute(
        statement.order_by(
            LiveSession.ended_at.desc(),
            LiveSession.session_id.desc(),
        )
        .offset(offset)
        .limit(limit + 1)
    ).all()

    items = []

    for session, quiz_id, title, version_number, host_name in rows[:limit]:
        items.append(
            {
                "session_id": session.session_id,
                "quiz_id": quiz_id,
                "quiz_title": title,
                "version_number": version_number,
                "host_name": host_name,
                "status": session.status.value,
                "created_at": _date(session.created_at),
                "started_at": _date(session.started_at),
                "ended_at": _date(session.ended_at),
            }
        )

    return {
        "items": items,
        "has_more": len(rows) > limit,
    }


def list_taken_sessions(
    db: Session,
    account: CurrentAccount,
    *,
    limit: int = 20,
    offset: int = 0,
    q: str = "",
    sort: str = "recent",
) -> dict:
    participant_counts = (
        select(
            SessionParticipant.session_id,
            func.count().label("total_participants"),
        )
        .group_by(SessionParticipant.session_id)
        .subquery()
    )

    played_counts = (
        select(
            SessionQuestion.session_id,
            func.count().label("played_count"),
        )
        .where(SessionQuestion.status == SessionQuestionStatus.CLOSED)
        .group_by(SessionQuestion.session_id)
        .subquery()
    )

    statement = (
        select(
            LiveSession.session_id,
            QuizVersion.quiz_id,
            QuizVersion.title.label("quiz_title"),
            QuizVersion.version_number,
            Account.display_name.label("host_name"),
            LiveSession.ended_at,
            Result.final_rank,
            Result.correct_count,
            Result.total_score,
            participant_counts.c.total_participants,
            func.coalesce(played_counts.c.played_count, 0).label("played_count"),
        )
        .select_from(LiveSession)
        .join(
            QuizVersion,
            QuizVersion.quiz_version_id == LiveSession.quiz_version_id,
        )
        .join(Account, Account.account_id == LiveSession.host_id)
        .join(
            SessionParticipant,
            SessionParticipant.session_id == LiveSession.session_id,
        )
        .outerjoin(
            Result,
            Result.session_participant_id == SessionParticipant.session_participant_id,
        )
        .join(
            participant_counts,
            participant_counts.c.session_id == LiveSession.session_id,
        )
        .outerjoin(
            played_counts,
            played_counts.c.session_id == LiveSession.session_id,
        )
        .where(
            SessionParticipant.account_id == account.account_id,
            LiveSession.status == LiveSessionStatus.COMPLETED,
        )
    )

    if q.strip():
        statement = statement.where(
            func.lower(QuizVersion.title).contains(
                q.strip().lower(),
                autoescape=True,
            )
        )

    recent = (
        LiveSession.ended_at.desc(),
        LiveSession.session_id.desc(),
    )

    if sort == "az":
        statement = statement.order_by(
            func.lower(QuizVersion.title),
            *recent,
        )
    elif sort == "score":
        # Best score means highest proportion of correct answers.
        accuracy = cast(Result.correct_count, Float) / func.nullif(
            played_counts.c.played_count, 0
        )
        statement = statement.order_by(
            func.coalesce(accuracy, -1).desc(),
            *recent,
        )
    else:
        statement = statement.order_by(*recent)

    rows = db.execute(statement.offset(offset).limit(limit + 1)).mappings().all()

    return {
        "items": [
            {
                "session_id": row["session_id"],
                "quiz_id": row["quiz_id"],
                "quiz_title": row["quiz_title"],
                "version_number": row["version_number"],
                "host_name": row["host_name"],
                "ended_at": _date(row["ended_at"]),
                "rank": row["final_rank"],
                "correct": row["correct_count"],
                "points": row["total_score"],
                "total_participants": row["total_participants"],
                "played_count": row["played_count"],
            }
            for row in rows[:limit]
        ],
        "has_more": len(rows) > limit,
    }


def list_quiz_hosting_history(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
    *,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    quiz = db.get(Quiz, quiz_id)

    if quiz is None or (quiz.author_id != account.account_id and not account.is_admin):
        raise APIError(
            404,
            "quiz_not_found",
            "Quiz not found.",
        )

    statement = _history_query().where(
        QuizVersion.quiz_id == quiz_id,
        LiveSession.status.in_(
            [
                LiveSessionStatus.COMPLETED,
                LiveSessionStatus.CANCELLED,
            ]
        ),
    )

    # Match the existing report permission model: hosts see their sessions;
    # global administrators can inspect all sessions.
    if not account.is_admin:
        statement = statement.where(LiveSession.host_id == account.account_id)

    return _page(db, statement, limit, offset)
