from collections import defaultdict
import csv
from datetime import UTC, datetime
from io import StringIO
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.models.account import Account
from app.models.classes import (
    ClassMembership,
    ClassRole,
    MembershipStatus,
)
from app.models.quiz import QuizVersion
from app.models.session import (
    LiveSession,
    LiveSessionStatus,
    Result,
    SessionParticipant,
)
from app.schemas.class_dashboard import (
    ClassDashboardResponse,
    ClassQuizPage,
    ClassQuizSummary,
    ClassSessionPage,
    ClassSessionSummary,
    ClassStudentPage,
    ClassStudentSummary,
    PageInfo,
    QuizSort,
    SessionSort,
    SortOrder,
    StudentSort,
)
from app.services.class_authorization import (
    ClassAccess,
    require_class_member,
    require_class_organizer,
)

RECENT_SCORE_COUNT = 5
LIVE_STATUSES = (LiveSessionStatus.LOBBY, LiveSessionStatus.ACTIVE)


def _page_info(page: int, page_size: int, total: int) -> PageInfo:
    return PageInfo(
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=ceil(total / page_size) if total else 0,
    )


def _paginate(items: list, page: int, page_size: int) -> list:
    start = (page - 1) * page_size
    return items[start : start + page_size]


def _utc(value: datetime | None) -> datetime | None:
    # MySQL hands back naive UTC datetimes; label them so clients don't guess.
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _is_organizer(access: ClassAccess) -> bool:
    return access.is_global_admin or (
        access.membership is not None
        and access.membership.role == ClassRole.ORGANIZER
    )


def _active_member_count(db: Session, class_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(ClassMembership.membership_id)).where(
                ClassMembership.class_id == class_id,
                ClassMembership.status == MembershipStatus.ACTIVE,
            )
        )
        or 0
    )


def _session_rows(db: Session, class_id: int, statuses) -> list:
    """One row per class session, with participant and score aggregates."""
    return db.execute(
        select(
            LiveSession.session_id,
            LiveSession.status,
            LiveSession.host_id,
            LiveSession.created_at,
            LiveSession.started_at,
            LiveSession.ended_at,
            QuizVersion.quiz_id,
            QuizVersion.title,
            Account.display_name.label("host_name"),
            func.count(SessionParticipant.session_participant_id).label(
                "participant_count"
            ),
            func.count(Result.result_id).label("result_count"),
            func.sum(Result.total_score).label("score_sum"),
            func.max(Result.total_score).label("top_score"),
        )
        .join(QuizVersion, QuizVersion.quiz_version_id == LiveSession.quiz_version_id)
        .join(Account, Account.account_id == LiveSession.host_id)
        .outerjoin(
            SessionParticipant,
            SessionParticipant.session_id == LiveSession.session_id,
        )
        .outerjoin(
            Result,
            Result.session_participant_id
            == SessionParticipant.session_participant_id,
        )
        .where(LiveSession.class_id == class_id, LiveSession.status.in_(statuses))
        .group_by(
            LiveSession.session_id,
            LiveSession.status,
            LiveSession.host_id,
            LiveSession.created_at,
            LiveSession.started_at,
            LiveSession.ended_at,
            QuizVersion.quiz_id,
            QuizVersion.title,
            Account.display_name,
        )
    ).all()


def _my_results(
    db: Session, account: CurrentAccount, session_ids: list[int]
) -> dict[int, tuple[int | None, int | None]]:
    if not session_ids:
        return {}
    rows = db.execute(
        select(
            SessionParticipant.session_id,
            Result.total_score,
            Result.final_rank,
        )
        .outerjoin(
            Result,
            Result.session_participant_id
            == SessionParticipant.session_participant_id,
        )
        .where(
            SessionParticipant.account_id == account.account_id,
            SessionParticipant.session_id.in_(session_ids),
        )
    ).all()
    return {row.session_id: (row.total_score, row.final_rank) for row in rows}


def _session_summaries(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    access: ClassAccess,
    statuses,
) -> tuple[list[ClassSessionSummary], list]:
    """Summaries newest first, plus the raw rows for quiz-level averages."""
    rows = _session_rows(db, class_id, statuses)
    mine = _my_results(db, account, [row.session_id for row in rows])
    organizer = _is_organizer(access)
    summaries = []
    for row in rows:
        my_score, my_rank = mine.get(row.session_id, (None, None))
        summaries.append(
            ClassSessionSummary(
                session_id=row.session_id,
                quiz_id=row.quiz_id,
                quiz_title=row.title,
                status=row.status.value,
                host_name=row.host_name,
                is_host=row.host_id == account.account_id,
                started_at=_utc(row.started_at or row.created_at),
                ended_at=_utc(row.ended_at),
                participant_count=int(row.participant_count),
                average_score=(
                    round(float(row.score_sum) / row.result_count, 1)
                    if organizer and row.result_count
                    else None
                ),
                top_score=(
                    int(row.top_score)
                    if organizer and row.top_score is not None
                    else None
                ),
                my_score=my_score,
                my_rank=my_rank,
            )
        )
    summaries.sort(key=lambda item: item.started_at, reverse=True)
    return summaries, rows


def _sort_sessions(
    items: list[ClassSessionSummary], sort: SessionSort, order: SortOrder
) -> list[ClassSessionSummary]:
    keys = {
        SessionSort.STARTED_AT: lambda item: item.started_at,
        SessionSort.PARTICIPANT_COUNT: lambda item: item.participant_count,
        SessionSort.AVERAGE_SCORE: lambda item: (
            item.average_score if item.average_score is not None else -1
        ),
    }
    return sorted(items, key=keys[sort], reverse=order == SortOrder.DESC)


def _quiz_summaries(
    sessions: list[ClassSessionSummary], score_rows: list, organizer: bool
) -> list[ClassQuizSummary]:
    # Weight each quiz's average by players, not by sessions.
    totals: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for row in score_rows:
        if row.result_count:
            totals[row.quiz_id][0] += int(row.score_sum)
            totals[row.quiz_id][1] += int(row.result_count)

    grouped: dict[int, list[ClassSessionSummary]] = defaultdict(list)
    for session in sessions:
        grouped[session.quiz_id].append(session)

    summaries = []
    for quiz_id, quiz_sessions in grouped.items():
        score_sum, result_count = totals[quiz_id]
        summaries.append(
            ClassQuizSummary(
                quiz_id=quiz_id,
                # Sessions are newest first, so this is the latest title.
                title=quiz_sessions[0].quiz_title,
                presented_at=quiz_sessions[0].started_at,
                session_count=len(quiz_sessions),
                participant_count=sum(s.participant_count for s in quiz_sessions),
                average_score=(
                    round(score_sum / result_count, 1)
                    if organizer and result_count
                    else None
                ),
            )
        )
    summaries.sort(key=lambda item: item.presented_at, reverse=True)
    return summaries


def _sort_quizzes(
    items: list[ClassQuizSummary], sort: QuizSort, order: SortOrder
) -> list[ClassQuizSummary]:
    keys = {
        QuizSort.PRESENTED_AT: lambda item: item.presented_at,
        QuizSort.TITLE: lambda item: item.title.lower(),
        QuizSort.PARTICIPANT_COUNT: lambda item: item.participant_count,
    }
    return sorted(items, key=keys[sort], reverse=order == SortOrder.DESC)


def _class_roster(db: Session, class_id: int) -> list:
    return db.execute(
        select(
            ClassMembership.account_id,
            ClassMembership.role,
            Account.display_name,
            Account.email,
        )
        .join(Account, Account.account_id == ClassMembership.account_id)
        .where(
            ClassMembership.class_id == class_id,
            ClassMembership.status == MembershipStatus.ACTIVE,
            ClassMembership.role == ClassRole.MEMBER,
        )
    ).all()


def _class_scores(
    db: Session, class_id: int
) -> tuple[list[int], dict[int, dict[int, int]]]:
    """Completed session ids newest first, and each player's score by session."""
    # One row per (session, player); a session nobody played still appears
    # once with a null account so it counts toward attendance.
    plays = db.execute(
        select(
            LiveSession.session_id,
            func.coalesce(LiveSession.started_at, LiveSession.created_at).label(
                "started_at"
            ),
            SessionParticipant.account_id,
            Result.total_score,
        )
        .outerjoin(
            SessionParticipant,
            SessionParticipant.session_id == LiveSession.session_id,
        )
        .outerjoin(
            Result,
            Result.session_participant_id
            == SessionParticipant.session_participant_id,
        )
        .where(
            LiveSession.class_id == class_id,
            LiveSession.status == LiveSessionStatus.COMPLETED,
        )
    ).all()

    session_times = {row.session_id: row.started_at for row in plays}
    newest_first = sorted(session_times, key=session_times.get, reverse=True)
    scores: dict[int, dict[int, int]] = defaultdict(dict)
    for row in plays:
        if row.account_id is not None:
            scores[row.account_id][row.session_id] = int(row.total_score or 0)
    return newest_first, scores


def _class_students(db: Session, class_id: int) -> list[ClassStudentSummary]:
    """Every active student with their scores across completed class sessions."""
    roster = _class_roster(db, class_id)
    newest_first, scores = _class_scores(db, class_id)

    students = []
    for row in roster:
        played = scores.get(row.account_id, {})
        total = sum(played.values())
        students.append(
            ClassStudentSummary(
                account_id=row.account_id,
                display_name=row.display_name,
                email=row.email,
                role=row.role,
                session_count=len(played),
                average_score=round(total / len(played), 1) if played else None,
                total_points=total,
                attendance_rate=(
                    round(len(played) / len(newest_first), 3)
                    if newest_first
                    else None
                ),
                recent_scores=[
                    played.get(session_id)
                    for session_id in newest_first[:RECENT_SCORE_COUNT]
                ],
            )
        )
    return students


def _sort_students(
    items: list[ClassStudentSummary], sort: StudentSort, order: SortOrder
) -> list[ClassStudentSummary]:
    # Ties (and nameless sorts) fall back to name, then id, for a stable page.
    items = sorted(items, key=lambda item: (item.display_name.lower(), item.account_id))
    keys = {
        StudentSort.NAME: lambda item: item.display_name.lower(),
        StudentSort.AVERAGE_SCORE: lambda item: (
            item.average_score if item.average_score is not None else -1
        ),
        StudentSort.SESSION_COUNT: lambda item: item.session_count,
    }
    return sorted(items, key=keys[sort], reverse=order == SortOrder.DESC)


def list_class_students(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    *,
    page: int,
    page_size: int,
    sort: StudentSort,
    order: SortOrder,
) -> ClassStudentPage:
    require_class_organizer(db, account, class_id)
    students = _sort_students(_class_students(db, class_id), sort, order)
    return ClassStudentPage(
        class_id=class_id,
        items=_paginate(students, page, page_size),
        pagination=_page_info(page, page_size, len(students)),
    )


def list_class_quizzes(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    *,
    page: int,
    page_size: int,
    sort: QuizSort,
    order: SortOrder,
) -> ClassQuizPage:
    access = require_class_member(db, account, class_id)
    sessions, rows = _session_summaries(
        db, account, class_id, access, (LiveSessionStatus.COMPLETED,)
    )
    quizzes = _sort_quizzes(
        _quiz_summaries(sessions, rows, _is_organizer(access)), sort, order
    )
    return ClassQuizPage(
        class_id=class_id,
        items=_paginate(quizzes, page, page_size),
        pagination=_page_info(page, page_size, len(quizzes)),
    )


def list_class_sessions(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    *,
    page: int,
    page_size: int,
    sort: SessionSort,
    order: SortOrder,
) -> ClassSessionPage:
    access = require_class_member(db, account, class_id)
    sessions, _ = _session_summaries(
        db, account, class_id, access, (LiveSessionStatus.COMPLETED,)
    )
    sessions = _sort_sessions(sessions, sort, order)
    return ClassSessionPage(
        class_id=class_id,
        items=_paginate(sessions, page, page_size),
        pagination=_page_info(page, page_size, len(sessions)),
    )


def get_class_dashboard(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassDashboardResponse:
    access = require_class_member(db, account, class_id)
    organizer = _is_organizer(access)
    completed, rows = _session_summaries(
        db, account, class_id, access, (LiveSessionStatus.COMPLETED,)
    )
    quizzes = _quiz_summaries(completed, rows, organizer)
    active, _ = _session_summaries(db, account, class_id, access, LIVE_STATUSES)
    students = _class_students(db, class_id)

    class_average = attendance_rate = None
    if organizer:
        averages = [s.average_score for s in students if s.average_score is not None]
        rates = [s.attendance_rate for s in students if s.attendance_rate is not None]
        class_average = round(sum(averages) / len(averages), 1) if averages else None
        attendance_rate = round(sum(rates) / len(rates), 3) if rates else None

    return ClassDashboardResponse(
        class_id=access.class_.class_id,
        class_name=access.class_.name,
        current_user_role=access.membership.role if access.membership else None,
        is_global_admin=access.is_global_admin,
        is_archived=access.class_.archived_at is not None,
        active_member_count=_active_member_count(db, class_id),
        student_count=len(students),
        completed_session_count=len(completed),
        class_average=class_average,
        attendance_rate=attendance_rate,
        active_sessions=active,
        completed_sessions=completed[:RECENT_SCORE_COUNT],
        presented_quizzes=quizzes[:RECENT_SCORE_COUNT],
        students=(
            _sort_students(students, StudentSort.NAME, SortOrder.ASC)[:10]
            if organizer
            else None
        ),
    )


def _csv_safe(value):
    # Same rule as the session export: stop names from running as formulas.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_class_grades(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> tuple[str, str]:
    """The gradebook as CSV text, plus the class name for the filename."""
    access = require_class_organizer(db, account, class_id)
    sessions, _ = _session_summaries(
        db, account, class_id, access, (LiveSessionStatus.COMPLETED,)
    )
    sessions.reverse()  # Oldest first reads left to right like a gradebook.
    students = _sort_students(
        _class_students(db, class_id), StudentSort.NAME, SortOrder.ASC
    )
    _, scores = _class_scores(db, class_id)

    output = StringIO(newline="")
    writer = csv.writer(output)

    def write(row):
        writer.writerow([_csv_safe(value) for value in row])

    write(
        [
            "Student",
            "Email",
            *(
                f"{session.quiz_title} ({session.started_at:%Y-%m-%d})"
                for session in sessions
            ),
            "Sessions played",
            "Attendance %",
            "Average points",
            "Total points",
        ]
    )
    for student in students:
        played = scores.get(student.account_id, {})
        write(
            [
                student.display_name,
                student.email,
                # A blank cell means absent, which is different from scoring 0.
                *(played.get(session.session_id, "") for session in sessions),
                student.session_count,
                (
                    round(student.attendance_rate * 100, 1)
                    if student.attendance_rate is not None
                    else ""
                ),
                student.average_score if student.average_score is not None else "",
                student.total_points,
            ]
        )
    return output.getvalue(), access.class_.name
