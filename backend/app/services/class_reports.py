"""Detailed class reports (task 8): one session, one quiz, or one student.

Only COMPLETED class sessions count; cancelled and unfinished ones never
appear. Scores come from the stored result rows, not from recalculating
responses.

Organizers and global Admins see everyone. Members see only their own rows,
and the class-wide numbers (averages, top scores) come back null for them,
the same as on the dashboard.

Averages use the dashboard's formula (docs/CLASSES.md):
- a student's average is the mean of their total points over the completed
  sessions they played; sessions they missed are left out, not counted as 0;
- the class average is the mean of the student averages, over active
  members with the MEMBER role who played at least once.
"""

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.account import Account
from app.models.classes import ClassMembership
from app.models.quiz import Quiz, QuizVersion
from app.models.session import (
    LiveSession,
    LiveSessionStatus,
    Result,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.services.class_authorization import require_class_member
from app.services.class_dashboard import (
    _class_students,
    _is_organizer,
    _session_summaries,
    _utc,
)
from app.services.session_end import load_final_results
from app.services.session_report import build_session_report


def _class_average(db: Session, class_id: int) -> float | None:
    averages = [
        student.average_score
        for student in _class_students(db, class_id)
        if student.average_score is not None
    ]
    return round(sum(averages) / len(averages), 1) if averages else None


def get_class_session_results(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    session_id: int,
) -> dict:
    access = require_class_member(db, account, class_id)
    session = db.get(LiveSession, session_id)
    # Other classes' sessions, open sessions and unfinished sessions all look
    # missing here, so the URL can't be used to probe them.
    if (
        session is None
        or session.class_id != class_id
        or session.status != LiveSessionStatus.COMPLETED
    ):
        raise APIError(404, "session_not_found", "Session not found.")

    viewer_id = None
    if not _is_organizer(access):
        viewer_id = db.scalar(
            select(SessionParticipant.session_participant_id).where(
                SessionParticipant.session_id == session_id,
                SessionParticipant.account_id == account.account_id,
            )
        )
        if viewer_id is None:
            raise APIError(
                403,
                "participant_report_denied",
                "You did not participate in this session.",
            )

    report = build_session_report(
        db, session, load_final_results(db, session), viewer_id
    )
    report["class_id"] = class_id
    report["started_at"] = _utc(session.started_at or session.created_at).isoformat()
    return report


def get_class_quiz_results(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_id: int,
) -> dict:
    access = require_class_member(db, account, class_id)
    organizer = _is_organizer(access)
    if db.get(Quiz, quiz_id) is None:
        raise APIError(404, "quiz_not_found", "Quiz not found.")

    sessions, _ = _session_summaries(
        db, account, class_id, access, (LiveSessionStatus.COMPLETED,)
    )
    sessions = [s for s in sessions if s.quiz_id == quiz_id]
    session_ids = [s.session_id for s in sessions]

    # Every player's final row for these sessions in one query.
    query = (
        select(
            SessionParticipant.session_id,
            SessionParticipant.account_id,
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
        .where(SessionParticipant.session_id.in_(session_ids))
    )
    if not organizer:
        query = query.where(SessionParticipant.account_id == account.account_id)
    results = defaultdict(list)
    for row in db.execute(query).all():
        results[row.session_id].append(
            {
                "account_id": row.account_id,
                "name": row.display_name,
                "rank": row.final_rank,
                "points": row.total_score,
                "correct": row.correct_count,
            }
        )

    title = (
        sessions[0].quiz_title
        if sessions
        else db.scalar(
            select(QuizVersion.title)
            .where(QuizVersion.quiz_id == quiz_id)
            .order_by(QuizVersion.version_number.desc())
            .limit(1)
        )
    )
    score_sum = sum(p["points"] for rows in results.values() for p in rows)
    result_count = sum(len(rows) for rows in results.values())

    return {
        "class_id": class_id,
        "quiz_id": quiz_id,
        "title": title,
        "session_count": len(sessions),
        "participant_count": sum(s.participant_count for s in sessions),
        # Weighted by players, like the quizzes tab.
        "average_score": (
            round(score_sum / result_count, 1) if organizer and result_count else None
        ),
        "sessions": [
            {
                **session.model_dump(mode="json"),
                "results": sorted(
                    results[session.session_id],
                    key=lambda p: (p["rank"], p["name"].casefold()),
                ),
            }
            for session in sessions
        ],
    }


def get_class_student_results(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    account_id: int,
) -> dict:
    access = require_class_member(db, account, class_id)
    organizer = _is_organizer(access)
    if not organizer and account_id != account.account_id:
        raise APIError(
            403,
            "not_class_organizer",
            "Only a class organizer or global Admin can view other students.",
        )

    # Removed and departed students keep their history, so any membership
    # row counts; invited-only accounts never played, which is harmless.
    student = db.execute(
        select(
            Account.account_id,
            Account.display_name,
            Account.email,
            ClassMembership.role,
            ClassMembership.status,
        )
        .join(ClassMembership, ClassMembership.account_id == Account.account_id)
        .where(
            ClassMembership.class_id == class_id,
            ClassMembership.account_id == account_id,
        )
    ).one_or_none()
    if student is None:
        raise APIError(404, "student_not_found", "Student not found.")

    played_questions = (
        select(
            SessionQuestion.session_id,
            func.count(SessionQuestion.session_question_id).label("question_count"),
        )
        .where(SessionQuestion.status == SessionQuestionStatus.CLOSED)
        .group_by(SessionQuestion.session_id)
        .subquery()
    )
    my_results = (
        select(
            SessionParticipant.session_id,
            Result.total_score,
            Result.correct_count,
            Result.final_rank,
        )
        .join(
            Result,
            Result.session_participant_id == SessionParticipant.session_participant_id,
        )
        .where(SessionParticipant.account_id == account_id)
        .subquery()
    )
    rows = db.execute(
        select(
            LiveSession.session_id,
            LiveSession.started_at,
            LiveSession.created_at,
            QuizVersion.quiz_id,
            QuizVersion.title,
            func.coalesce(played_questions.c.question_count, 0).label("question_count"),
            my_results.c.total_score,
            my_results.c.correct_count,
            my_results.c.final_rank,
        )
        .join(QuizVersion, QuizVersion.quiz_version_id == LiveSession.quiz_version_id)
        .outerjoin(
            played_questions, played_questions.c.session_id == LiveSession.session_id
        )
        .outerjoin(my_results, my_results.c.session_id == LiveSession.session_id)
        .where(
            LiveSession.class_id == class_id,
            LiveSession.status == LiveSessionStatus.COMPLETED,
        )
    ).all()

    sessions = []
    for row in rows:
        played = row.total_score is not None
        sessions.append(
            {
                "session_id": row.session_id,
                "quiz_id": row.quiz_id,
                "quiz_title": row.title,
                "started_at": _utc(row.started_at or row.created_at),
                "played": played,
                "points": row.total_score,
                "rank": row.final_rank,
                "question_count": row.question_count,
                "correct": row.correct_count if played else None,
                # Unanswered questions count as incorrect.
                "incorrect": (
                    row.question_count - row.correct_count if played else None
                ),
            }
        )
    sessions.sort(key=lambda s: s["started_at"], reverse=True)
    for session in sessions:
        session["started_at"] = session["started_at"].isoformat()

    played = [s for s in sessions if s["played"]]
    total = sum(s["points"] for s in played)
    return {
        "class_id": class_id,
        "account_id": student.account_id,
        "display_name": student.display_name,
        "email": student.email if organizer else None,
        "role": student.role.value,
        "status": student.status.value,
        "class_session_count": len(sessions),
        "session_count": len(played),
        "attendance_rate": (
            round(len(played) / len(sessions), 3) if sessions else None
        ),
        "total_points": total,
        "average_score": round(total / len(played), 1) if played else None,
        "correct_count": sum(s["correct"] for s in played),
        "incorrect_count": sum(s["incorrect"] for s in played),
        "class_average": _class_average(db, class_id) if organizer else None,
        "sessions": sessions,
    }
