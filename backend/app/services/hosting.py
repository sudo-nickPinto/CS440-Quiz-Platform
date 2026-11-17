"""Can this person host this quiz right now, and if not, why?

Starting a session (create_session) and the `hosting` field on quiz responses
(which drives the Host button) both use these checks, so the button and the
server always agree.

The order matches create_session: class archived, host permission, quiz
archived, published (with no unpublished draft on top), approved. Membership is checked by the caller, because
people outside the class can't see the quiz at all.

The checks are batched: a list of quizzes costs a fixed number of queries no
matter how long it is.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import Class, Quiz, QuizStatus, QuizVersion
from app.models.classes import ClassMembership
from app.models.quiz_submission import QuizSubmission, SubmissionStatus
from app.schemas.quiz import QuizHosting
from app.services.class_authorization import ClassAccess


@dataclass(frozen=True)
class HostingProblem:
    reason: str
    status_code: int
    code: str
    message: str

    def error(self) -> APIError:
        return APIError(
            self.status_code,
            self.code,
            self.message,
            details={"reason": self.reason},
        )


def _problem(reason: str, status_code: int, code: str, message: str):
    return reason, HostingProblem(reason, status_code, code, message)


# The error code stays the same as before for each case, so existing clients
# keep working; the reason and message say exactly what to do next.
PROBLEMS: dict[str, HostingProblem] = dict(
    [
        _problem(
            "not_in_class",
            409,
            "quiz_not_hostable",
            "This quiz isn't in a class, so it can't be hosted.",
        ),
        _problem(
            "class_archived",
            409,
            "class_archived",
            "This class is archived, so it can't start new sessions.",
        ),
        _problem(
            "not_host",
            403,
            "session_host_denied",
            "Only the quiz owner or a class organizer can host this quiz.",
        ),
        _problem(
            "quiz_archived",
            409,
            "quiz_not_hostable",
            "This quiz is archived, so it can't be hosted.",
        ),
        _problem(
            "not_published",
            409,
            "quiz_not_hostable",
            "Publish this quiz before hosting it.",
        ),
        _problem(
            "unpublished_changes",
            409,
            "quiz_not_hostable",
            "This quiz has unpublished changes. Publish them and get the new "
            "version approved before hosting.",
        ),
        _problem(
            "not_submitted",
            409,
            "quiz_version_not_approved",
            "Submit this quiz to the class organizers for approval "
            "before hosting it.",
        ),
        _problem(
            "pending_approval",
            409,
            "quiz_version_not_approved",
            "This quiz is waiting for a class organizer to approve it.",
        ),
        _problem(
            "rejected",
            409,
            "quiz_version_not_approved",
            "A class organizer rejected this version. Update it or submit "
            "it again for approval.",
        ),
        _problem(
            "withdrawn",
            409,
            "quiz_version_not_approved",
            "The approval request for this version was withdrawn. Submit it "
            "again to host it.",
        ),
        _problem(
            "approval_outdated",
            409,
            "quiz_version_not_approved",
            "An older version was approved, but the newest published version "
            "wasn't. Submit the new version for approval.",
        ),
    ]
)


@dataclass(frozen=True)
class HostingCheck:
    problem: HostingProblem | None
    # The version a new session would use, once the quiz is hostable.
    version: QuizVersion | None


def _class_states(
    db: Session,
    account: CurrentAccount,
    class_ids: set[int],
) -> dict[int, tuple[bool, bool]]:
    """(archived, is_organizer) per class, in two queries.

    is_organizer uses ClassAccess, the same rule create_session uses: an
    ACTIVE ORGANIZER membership *and* faculty status.
    """
    if not class_ids:
        return {}
    classes = {
        class_.class_id: class_
        for class_ in db.scalars(select(Class).where(Class.class_id.in_(class_ids)))
    }
    memberships = {
        membership.class_id: membership
        for membership in db.scalars(
            select(ClassMembership).where(
                ClassMembership.class_id.in_(class_ids),
                ClassMembership.account_id == account.account_id,
            )
        )
    }
    states = {}
    for class_id, class_ in classes.items():
        membership = memberships.get(class_id)
        is_organizer = (
            membership is not None
            and ClassAccess(class_, membership, is_faculty=account.is_admin).is_organizer
        )
        states[class_id] = (class_.archived_at is not None, is_organizer)
    return states


def _latest_published_versions(
    db: Session, quiz_ids: set[int]
) -> dict[int, tuple[QuizVersion, bool]]:
    """The newest published version of each quiz, and whether a newer
    unpublished draft sits on top of it. One query."""
    if not quiz_ids:
        return {}
    newest = (
        select(
            QuizVersion.quiz_id.label("quiz_id"),
            func.max(
                case(
                    (QuizVersion.published_at.is_not(None), QuizVersion.version_number)
                )
            ).label("published_number"),
            func.max(QuizVersion.version_number).label("newest_number"),
        )
        .where(QuizVersion.quiz_id.in_(quiz_ids))
        .group_by(QuizVersion.quiz_id)
        .subquery()
    )
    rows = db.execute(
        select(QuizVersion, newest.c.newest_number).join(
            newest,
            (QuizVersion.quiz_id == newest.c.quiz_id)
            & (QuizVersion.version_number == newest.c.published_number),
        )
    )
    return {
        version.quiz_id: (version, newest_number > version.version_number)
        for version, newest_number in rows
    }


def _approval_problems(
    db: Session,
    candidates: Sequence[tuple[Quiz, QuizVersion]],
) -> dict[int, HostingProblem | None]:
    """Approval state of each quiz's newest published version, in two queries.

    A version is approved when the quiz's class has an APPROVED submission
    for it. That is the same rule as Task 4's approved-quiz listing: the quiz
    belongs to the class, isn't archived, and no newer version was published
    (all already true here, because this is the newest published version of
    a non-archived quiz).
    """
    if not candidates:
        return {}
    version_ids = {version.quiz_version_id for _, version in candidates}
    submissions: dict[tuple[int, int], list[QuizSubmission]] = {}
    for submission in db.scalars(
        select(QuizSubmission)
        .where(QuizSubmission.quiz_version_id.in_(version_ids))
        .order_by(
            QuizSubmission.submitted_at.desc(),
            QuizSubmission.submission_id.desc(),
        )
    ):
        key = (submission.class_id, submission.quiz_version_id)
        submissions.setdefault(key, []).append(submission)

    approved_versions: dict[tuple[int, int], int] = {}
    for quiz_id, class_id, version_number in db.execute(
        select(QuizVersion.quiz_id, QuizSubmission.class_id, QuizVersion.version_number)
        .join(
            QuizSubmission,
            QuizSubmission.quiz_version_id == QuizVersion.quiz_version_id,
        )
        .where(
            QuizVersion.quiz_id.in_({quiz.quiz_id for quiz, _ in candidates}),
            QuizSubmission.status == SubmissionStatus.APPROVED,
        )
    ):
        key = (quiz_id, class_id)
        approved_versions[key] = min(
            approved_versions.get(key, version_number), version_number
        )

    problems: dict[int, HostingProblem | None] = {}
    for quiz, version in candidates:
        history = submissions.get((quiz.class_id, version.quiz_version_id), [])
        if any(item.status == SubmissionStatus.APPROVED for item in history):
            problems[quiz.quiz_id] = None
        elif history and history[0].status == SubmissionStatus.PENDING:
            problems[quiz.quiz_id] = PROBLEMS["pending_approval"]
        elif history and history[0].status == SubmissionStatus.REJECTED:
            problems[quiz.quiz_id] = PROBLEMS["rejected"]
        elif history and history[0].status == SubmissionStatus.WITHDRAWN:
            problems[quiz.quiz_id] = PROBLEMS["withdrawn"]
        elif (
            approved_versions.get((quiz.quiz_id, quiz.class_id), version.version_number)
            < version.version_number
        ):
            problems[quiz.quiz_id] = PROBLEMS["approval_outdated"]
        else:
            problems[quiz.quiz_id] = PROBLEMS["not_submitted"]
    return problems


def check_hosting_many(
    db: Session,
    account: CurrentAccount,
    quizzes: Iterable[Quiz],
) -> dict[int, HostingCheck]:
    """Run every hosting rule for quizzes the caller can already see.

    Uses at most five queries however many quizzes are passed in.
    """
    quizzes = list(quizzes)
    states = _class_states(
        db, account, {quiz.class_id for quiz in quizzes if quiz.class_id is not None}
    )

    checks: dict[int, HostingCheck] = {}
    remaining: list[Quiz] = []
    for quiz in quizzes:
        if quiz.class_id is None or quiz.class_id not in states:
            checks[quiz.quiz_id] = HostingCheck(PROBLEMS["not_in_class"], None)
            continue
        archived, is_organizer = states[quiz.class_id]
        if archived:
            problem = PROBLEMS["class_archived"]
        elif quiz.author_id != account.account_id and not is_organizer:
            problem = PROBLEMS["not_host"]
        elif quiz.status == QuizStatus.ARCHIVED:
            problem = PROBLEMS["quiz_archived"]
        else:
            remaining.append(quiz)
            continue
        checks[quiz.quiz_id] = HostingCheck(problem, None)

    versions = _latest_published_versions(db, {quiz.quiz_id for quiz in remaining})
    candidates = []
    for quiz in remaining:
        version, draft_on_top = versions.get(quiz.quiz_id, (None, False))
        if version is None:
            checks[quiz.quiz_id] = HostingCheck(PROBLEMS["not_published"], None)
        elif draft_on_top or quiz.status == QuizStatus.DRAFT:
            # Edited after publishing: an older version is published, but the
            # owner and the page are on the new draft. Hosting the old version
            # would silently show different content, so block it.
            checks[quiz.quiz_id] = HostingCheck(
                PROBLEMS["unpublished_changes"], None
            )
        else:
            candidates.append((quiz, version))

    approvals = _approval_problems(db, candidates)
    for quiz, version in candidates:
        problem = approvals[quiz.quiz_id]
        checks[quiz.quiz_id] = HostingCheck(problem, None if problem else version)
    return checks


def check_hosting(db: Session, account: CurrentAccount, quiz: Quiz) -> HostingCheck:
    return check_hosting_many(db, account, [quiz])[quiz.quiz_id]


def to_quiz_hosting(check: HostingCheck) -> QuizHosting:
    if check.problem is None:
        return QuizHosting(can_host=True)
    return QuizHosting(
        can_host=False, reason=check.problem.reason, message=check.problem.message
    )


def quiz_hosting_many(
    db: Session, account: CurrentAccount, quizzes: Iterable[Quiz]
) -> dict[int, QuizHosting]:
    return {
        quiz_id: to_quiz_hosting(check)
        for quiz_id, check in check_hosting_many(db, account, quizzes).items()
    }


def quiz_hosting(db: Session, account: CurrentAccount, quiz: Quiz) -> QuizHosting:
    return to_quiz_hosting(check_hosting(db, account, quiz))
