"""V3 task 6: the class dashboard's views of the Task 4 approval queue.

Organizers see every submission in the class with who sent it and which
version; members see only their own. Approved quizzes are visible to every
active member, and each one says whether the caller may host it.
"""

from math import ceil

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.auth import CurrentAccount
from app.models.account import Account
from app.models.quiz import Question, Quiz, QuizStatus, QuizVersion
from app.models.quiz_submission import QuizSubmission, SubmissionStatus
from app.schemas.class_dashboard import (
    ApprovedQuizSort,
    ClassApprovedQuiz,
    ClassApprovedQuizPage,
    ClassSubmissionPage,
    ClassSubmissionSummary,
    SubmissionSort,
)
from app.schemas.pagination import PageInfo, SortOrder
from app.services.class_authorization import ClassAccess, require_class_member
from app.services.hosting import quiz_hosting_many
from app.services.quiz_submissions import (
    _approved_versions_statement as approved_versions_statement,
)


def _page_info(page: int, page_size: int, total: int) -> PageInfo:
    return PageInfo(
        page=page,
        page_size=page_size,
        total_items=total,
        total_pages=ceil(total / page_size) if total else 0,
    )


def _page(items: list, page: int, page_size: int) -> list:
    start = (page - 1) * page_size
    return items[start : start + page_size]


def _question_counts(db: Session, version_ids: set[int]) -> dict[int, int]:
    if not version_ids:
        return {}
    rows = db.execute(
        select(Question.quiz_version_id, func.count(Question.question_id))
        .where(Question.quiz_version_id.in_(version_ids))
        .group_by(Question.quiz_version_id)
    ).all()
    return {version_id: int(count) for version_id, count in rows}


def _newest_published(db: Session, quiz_ids: set[int]) -> dict[int, int]:
    if not quiz_ids:
        return {}
    rows = db.execute(
        select(QuizVersion.quiz_id, func.max(QuizVersion.version_number))
        .where(
            QuizVersion.quiz_id.in_(quiz_ids),
            QuizVersion.published_at.is_not(None),
        )
        .group_by(QuizVersion.quiz_id)
    ).all()
    return {quiz_id: int(number) for quiz_id, number in rows}


def _visible_submissions(
    access: ClassAccess, account: CurrentAccount, class_id: int
):
    submitter = aliased(Account)
    decider = aliased(Account)
    statement = (
        select(
            QuizSubmission,
            QuizVersion,
            submitter.display_name.label("submitter_name"),
            decider.display_name.label("decided_by_name"),
        )
        .join(
            QuizVersion,
            QuizVersion.quiz_version_id == QuizSubmission.quiz_version_id,
        )
        .join(Quiz, Quiz.quiz_id == QuizVersion.quiz_id)
        .join(submitter, submitter.account_id == QuizSubmission.submitted_by_id)
        .outerjoin(decider, decider.account_id == QuizSubmission.decided_by_id)
        .where(QuizSubmission.class_id == class_id, Quiz.class_id == class_id)
    )
    if not access.is_organizer:
        statement = statement.where(
            QuizSubmission.submitted_by_id == account.account_id
        )
    return statement


def _hostable_approved(class_id: int):
    return approved_versions_statement(class_id).where(
        Quiz.status == QuizStatus.PUBLISHED
    )


def list_class_submissions(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    *,
    page: int,
    page_size: int,
    sort: SubmissionSort,
    order: SortOrder,
    status: SubmissionStatus | None,
) -> ClassSubmissionPage:
    access = require_class_member(db, account, class_id)
    statement = _visible_submissions(access, account, class_id)
    if status is not None:
        statement = statement.where(QuizSubmission.status == status)
    rows = db.execute(statement).all()

    counts = _question_counts(db, {row.QuizVersion.quiz_version_id for row in rows})
    newest = _newest_published(db, {row.QuizVersion.quiz_id for row in rows})
    items = [
        ClassSubmissionSummary(
            submission_id=row.QuizSubmission.submission_id,
            quiz_id=row.QuizVersion.quiz_id,
            quiz_version_id=row.QuizVersion.quiz_version_id,
            version_number=row.QuizVersion.version_number,
            quiz_title=row.QuizVersion.title,
            question_count=counts.get(row.QuizVersion.quiz_version_id, 0),
            submitted_by_id=row.QuizSubmission.submitted_by_id,
            submitter_name=row.submitter_name,
            status=row.QuizSubmission.status,
            submitted_at=row.QuizSubmission.submitted_at,
            decided_at=row.QuizSubmission.decided_at,
            decided_by_name=row.decided_by_name,
            is_current_version=(
                newest.get(row.QuizVersion.quiz_id) == row.QuizVersion.version_number
            ),
        )
        for row in rows
    ]

    keys = {
        SubmissionSort.SUBMITTED_AT: lambda item: item.submitted_at,
        SubmissionSort.TITLE: lambda item: item.quiz_title.lower(),
        SubmissionSort.SUBMITTER: lambda item: item.submitter_name.lower(),
    }
    reverse = order == SortOrder.DESC
    # Id breaks ties so equal timestamps or titles still page stably.
    items.sort(key=lambda item: item.submission_id, reverse=reverse)
    items.sort(key=keys[sort], reverse=reverse)
    return ClassSubmissionPage(
        class_id=class_id,
        items=_page(items, page, page_size),
        pagination=_page_info(page, page_size, len(items)),
    )


def list_class_approved_quizzes(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    *,
    page: int,
    page_size: int,
    sort: ApprovedQuizSort,
    order: SortOrder,
) -> ClassApprovedQuizPage:
    require_class_member(db, account, class_id)
    author = aliased(Account)
    approver = aliased(Account)
    rows = db.execute(
        _hostable_approved(class_id)
        .add_columns(
            author.display_name.label("author_name"),
            approver.display_name.label("approved_by_name"),
        )
        .join(author, author.account_id == Quiz.author_id)
        .join(approver, approver.account_id == QuizSubmission.decided_by_id)
    ).all()

    counts = _question_counts(db, {row.QuizVersion.quiz_version_id for row in rows})
    hosting = quiz_hosting_many(db, account, [row.Quiz for row in rows])
    items = [
        ClassApprovedQuiz(
            quiz_id=row.Quiz.quiz_id,
            quiz_version_id=row.QuizVersion.quiz_version_id,
            version_number=row.QuizVersion.version_number,
            title=row.QuizVersion.title,
            question_count=counts.get(row.QuizVersion.quiz_version_id, 0),
            author_id=row.Quiz.author_id,
            author_name=row.author_name,
            approved_at=row.QuizSubmission.decided_at,
            approved_by_name=row.approved_by_name,
            can_host=hosting[row.Quiz.quiz_id].can_host,
            hosting=hosting[row.Quiz.quiz_id],
        )
        for row in rows
    ]

    keys = {
        ApprovedQuizSort.APPROVED_AT: lambda item: item.approved_at,
        ApprovedQuizSort.TITLE: lambda item: item.title.lower(),
    }
    reverse = order == SortOrder.DESC
    items.sort(key=lambda item: item.quiz_id, reverse=reverse)
    items.sort(key=keys[sort], reverse=reverse)
    return ClassApprovedQuizPage(
        class_id=class_id,
        items=_page(items, page, page_size),
        pagination=_page_info(page, page_size, len(items)),
    )


def approval_counts(
    db: Session, account: CurrentAccount, access: ClassAccess, class_id: int
) -> tuple[int, int]:
    """(pending submissions the caller can see, hostable approved quizzes)."""
    pending = db.execute(
        _visible_submissions(access, account, class_id).where(
            QuizSubmission.status == SubmissionStatus.PENDING
        )
    ).all()
    approved = db.execute(_hostable_approved(class_id)).all()
    return len(pending), len(approved)
