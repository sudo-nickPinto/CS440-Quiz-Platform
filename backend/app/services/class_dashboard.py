from math import ceil

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.models.account import Account
from app.models.classes import (
    ClassMembership,
    ClassRole,
    MembershipStatus,
)
from app.schemas.class_dashboard import (
    ClassDashboardResponse,
    ClassQuizPage,
    ClassSessionPage,
    ClassStudentPage,
    ClassStudentSummary,
    DependencyState,
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


PENDING_CLASS_LINKS = DependencyState(
    is_complete=False,
    blocked_by=["task_5_quiz_class_association", "task_6_class_sessions"],
)
PENDING_SCORE_LINKS = DependencyState(
    is_complete=False,
    blocked_by=["task_5_quiz_class_association", "task_6_class_sessions"],
)


def _page_info(page: int, page_size: int, total: int) -> PageInfo:
    return PageInfo(
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=ceil(total / page_size) if total else 0,
    )


def _empty_page(page: int, page_size: int) -> PageInfo:
    return _page_info(page, page_size, 0)


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


def _student_sort_column(sort: StudentSort):
    # Score-based sorts temporarily fall back to name until Tasks 5 and 6
    # provide class-scoped session/result relationships.
    if sort in (StudentSort.AVERAGE_SCORE, StudentSort.SESSION_COUNT):
        return Account.display_name
    return Account.display_name


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
    filters = (
        ClassMembership.class_id == class_id,
        ClassMembership.status == MembershipStatus.ACTIVE,
        ClassMembership.role == ClassRole.MEMBER,
    )
    total = int(
        db.scalar(
            select(func.count(ClassMembership.membership_id)).where(*filters)
        )
        or 0
    )
    sort_column = _student_sort_column(sort)
    direction = desc if order == SortOrder.DESC else asc
    rows = db.execute(
        select(
            ClassMembership.account_id,
            ClassMembership.role,
            Account.display_name,
            Account.email,
        )
        .join(Account, Account.account_id == ClassMembership.account_id)
        .where(*filters)
        .order_by(direction(sort_column), direction(ClassMembership.account_id))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        ClassStudentSummary(
            account_id=row.account_id,
            display_name=row.display_name,
            email=row.email,
            role=row.role,
            session_count=None,
            average_score=None,
            total_points=None,
        )
        for row in rows
    ]
    return ClassStudentPage(
        class_id=class_id,
        items=items,
        pagination=_page_info(page, page_size, total),
        dependency=PENDING_SCORE_LINKS,
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
    del sort, order
    require_class_member(db, account, class_id)
    return ClassQuizPage(
        class_id=class_id,
        items=[],
        pagination=_empty_page(page, page_size),
        dependency=PENDING_CLASS_LINKS,
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
    del sort, order
    require_class_member(db, account, class_id)
    return ClassSessionPage(
        class_id=class_id,
        items=[],
        pagination=_empty_page(page, page_size),
        dependency=PENDING_CLASS_LINKS,
    )


def _dashboard_students(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    access: ClassAccess,
) -> list[ClassStudentSummary] | None:
    if not access.is_organizer:
        return None
    return list_class_students(
        db,
        account,
        class_id,
        page=1,
        page_size=10,
        sort=StudentSort.NAME,
        order=SortOrder.ASC,
    ).items


def get_class_dashboard(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassDashboardResponse:
    access = require_class_member(db, account, class_id)
    return ClassDashboardResponse(
        class_id=access.class_.class_id,
        class_name=access.class_.name,
        current_user_role=access.role,
        is_global_admin=access.is_global_admin,
        is_archived=access.class_.archived_at is not None,
        active_member_count=_active_member_count(db, class_id),
        active_sessions=[],
        completed_sessions=[],
        presented_quizzes=[],
        students=_dashboard_students(db, account, class_id, access),
        dependency=PENDING_CLASS_LINKS,
    )
