"""Can this person host this quiz right now, and if not, why?

Starting a session (create_session) and the quiz responses that drive the
Host button both use these checks, so the button and the server always agree.
The approval check itself is still Task 4's require_approved_quiz_version.

The order matches create_session: class archived, host permission, quiz
archived, published, approved. Membership is checked by the caller, because
people outside the class can't see the quiz at all.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import APIError
from app.models import Quiz, QuizStatus, QuizVersion
from app.models.classes import ClassRole, MembershipStatus
from app.models.quiz_submission import QuizSubmission, SubmissionStatus
from app.schemas.quiz import QuizHosting
from app.services.class_authorization import get_class, get_class_membership
from app.services.quiz_submissions import require_approved_quiz_version


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


def latest_published_version(db: Session, quiz_id: int) -> QuizVersion | None:
    return db.scalar(
        select(QuizVersion)
        .where(
            QuizVersion.quiz_id == quiz_id,
            QuizVersion.published_at.is_not(None),
        )
        .order_by(QuizVersion.version_number.desc())
        .limit(1)
    )


def _approval_problem(
    db: Session, class_id: int, quiz: Quiz, version: QuizVersion
) -> HostingProblem:
    """Explain why the newest published version isn't approved."""
    latest = db.scalar(
        select(QuizSubmission.status)
        .where(
            QuizSubmission.class_id == class_id,
            QuizSubmission.quiz_version_id == version.quiz_version_id,
        )
        .order_by(
            QuizSubmission.submitted_at.desc(),
            QuizSubmission.submission_id.desc(),
        )
        .limit(1)
    )
    if latest == SubmissionStatus.PENDING:
        return PROBLEMS["pending_approval"]
    if latest == SubmissionStatus.REJECTED:
        return PROBLEMS["rejected"]
    if latest == SubmissionStatus.WITHDRAWN:
        return PROBLEMS["withdrawn"]

    older_approved = db.scalar(
        select(QuizSubmission.submission_id)
        .join(
            QuizVersion,
            QuizVersion.quiz_version_id == QuizSubmission.quiz_version_id,
        )
        .where(
            QuizSubmission.class_id == class_id,
            QuizSubmission.status == SubmissionStatus.APPROVED,
            QuizVersion.quiz_id == quiz.quiz_id,
            QuizVersion.version_number < version.version_number,
        )
        .limit(1)
    )
    if older_approved is not None:
        return PROBLEMS["approval_outdated"]
    return PROBLEMS["not_submitted"]


def check_hosting(
    db: Session,
    quiz: Quiz,
    account_id: int,
    *,
    is_organizer: bool,
    class_archived: bool,
) -> HostingCheck:
    """Run every hosting rule for a quiz the caller can already see."""
    if quiz.class_id is None:
        return HostingCheck(PROBLEMS["not_in_class"], None)
    if class_archived:
        return HostingCheck(PROBLEMS["class_archived"], None)
    if quiz.author_id != account_id and not is_organizer:
        return HostingCheck(PROBLEMS["not_host"], None)
    if quiz.status == QuizStatus.ARCHIVED:
        return HostingCheck(PROBLEMS["quiz_archived"], None)

    version = latest_published_version(db, quiz.quiz_id)
    if version is None:
        return HostingCheck(PROBLEMS["not_published"], None)

    try:
        require_approved_quiz_version(db, quiz.class_id, version.quiz_version_id)
    except APIError as exc:
        if exc.code == "class_archived":
            return HostingCheck(PROBLEMS["class_archived"], None)
        if exc.code != "quiz_version_not_approved":
            raise
        return HostingCheck(_approval_problem(db, quiz.class_id, quiz, version), None)
    return HostingCheck(None, version)


def to_quiz_hosting(problem: HostingProblem | None) -> QuizHosting:
    if problem is None:
        return QuizHosting(can_host=True)
    return QuizHosting(
        can_host=False, reason=problem.reason, message=problem.message
    )


class HostingLookup:
    """Works out a caller's hosting status for many quizzes.

    It remembers each class's archived flag and the caller's role, so a list
    of quizzes doesn't look them up again for every row.
    """

    def __init__(self, db: Session, account_id: int) -> None:
        self.db = db
        self.account_id = account_id
        self._classes: dict[int, tuple[bool, bool]] = {}

    def _class_state(self, class_id: int) -> tuple[bool, bool]:
        if class_id not in self._classes:
            archived = get_class(self.db, class_id).archived_at is not None
            membership = get_class_membership(self.db, class_id, self.account_id)
            is_organizer = (
                membership is not None
                and membership.status == MembershipStatus.ACTIVE
                and membership.role == ClassRole.ORGANIZER
            )
            self._classes[class_id] = (archived, is_organizer)
        return self._classes[class_id]

    def __call__(self, quiz: Quiz) -> QuizHosting:
        if quiz.class_id is None:
            return to_quiz_hosting(PROBLEMS["not_in_class"])
        archived, is_organizer = self._class_state(quiz.class_id)
        check = check_hosting(
            self.db,
            quiz,
            self.account_id,
            is_organizer=is_organizer,
            class_archived=archived,
        )
        return to_quiz_hosting(check.problem)
