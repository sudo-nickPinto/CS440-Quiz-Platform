from datetime import UTC, datetime

from sqlalchemy import exists, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.account import Account
from app.models.classes import ClassMembership, MembershipStatus
from app.models.quiz import Quiz, QuizCollaborator, QuizStatus, QuizVersion
from app.models.quiz_submission import QuizSubmission, SubmissionStatus
from app.schemas.quiz_submission import (
    ApprovedQuizResponse,
    QuizSubmissionCreate,
    QuizSubmissionDecision,
    QuizSubmissionResponse,
)
from app.services.class_authorization import ClassAccess, require_class_member


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _active_collaborator_exists(
    db: Session,
    quiz_id: int,
    account_id: int,
) -> bool:
    return (
        db.scalar(
            select(QuizCollaborator.quiz_id).where(
                QuizCollaborator.quiz_id == quiz_id,
                QuizCollaborator.account_id == account_id,
                QuizCollaborator.revoked_at.is_(None),
            )
        )
        is not None
    )


def _has_quiz_access(db: Session, quiz: Quiz, account_id: int) -> bool:
    return quiz.author_id == account_id or _active_collaborator_exists(
        db, quiz.quiz_id, account_id
    )


def _version_and_quiz(
    db: Session,
    quiz_version_id: int,
) -> tuple[QuizVersion, Quiz] | None:
    row = db.execute(
        select(QuizVersion, Quiz)
        .join(Quiz, Quiz.quiz_id == QuizVersion.quiz_id)
        .where(QuizVersion.quiz_version_id == quiz_version_id)
    ).one_or_none()
    if row is None:
        return None
    return row.QuizVersion, row.Quiz


def _load_visible_version(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_version_id: int,
) -> tuple[QuizVersion, Quiz]:
    row = _version_and_quiz(db, quiz_version_id)
    if row is None:
        raise APIError(404, "quiz_version_not_found", "Quiz version not found.")
    version, quiz = row
    if quiz.class_id != class_id or not _has_quiz_access(
        db, quiz, account.account_id
    ):
        raise APIError(404, "quiz_version_not_found", "Quiz version not found.")
    return version, quiz


def _require_published_current_version(
    db: Session,
    class_id: int,
    version: QuizVersion,
    quiz: Quiz,
) -> None:
    if quiz.class_id != class_id:
        raise APIError(404, "quiz_version_not_found", "Quiz version not found.")
    if version.published_at is None or quiz.status == QuizStatus.ARCHIVED:
        raise APIError(
            409,
            "quiz_version_not_published",
            "Only a published, non-archived quiz version can be submitted.",
        )
    newer_published = db.scalar(
        select(QuizVersion.quiz_version_id).where(
            QuizVersion.quiz_id == version.quiz_id,
            QuizVersion.published_at.is_not(None),
            QuizVersion.version_number > version.version_number,
        )
    )
    if newer_published is not None:
        raise APIError(
            409,
            "quiz_version_stale",
            "A newer published version of this quiz is available.",
        )


def _submission_response(submission: QuizSubmission) -> QuizSubmissionResponse:
    return QuizSubmissionResponse.model_validate(submission)


def create_quiz_submission(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    payload: QuizSubmissionCreate,
) -> QuizSubmissionResponse:
    require_class_member(db, account, class_id)
    version, quiz = _load_visible_version(
        db, account, class_id, payload.quiz_version_id
    )
    _require_published_current_version(db, class_id, version, quiz)

    submission = QuizSubmission(
        class_id=class_id,
        quiz_version_id=version.quiz_version_id,
        submitted_by_id=account.account_id,
        status=SubmissionStatus.PENDING,
    )
    db.add(submission)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise APIError(
            409,
            "quiz_submission_conflict",
            "This quiz version already has a pending or approved submission.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "quiz_submission_failed",
            "Could not submit the quiz version.",
        ) from exc

    db.refresh(submission)
    return _submission_response(submission)


def list_quiz_submissions(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> list[QuizSubmissionResponse]:
    access = require_class_member(db, account, class_id)
    statement = select(QuizSubmission).where(QuizSubmission.class_id == class_id)
    if not access.is_organizer:
        statement = statement.where(
            QuizSubmission.submitted_by_id == account.account_id
        )
    statement = statement.order_by(
        QuizSubmission.submitted_at.desc(), QuizSubmission.submission_id.desc()
    )
    return [
        _submission_response(submission)
        for submission in db.scalars(statement).all()
    ]


def _load_visible_submission(
    db: Session,
    account: CurrentAccount,
    access: ClassAccess,
    class_id: int,
    submission_id: int,
) -> QuizSubmission:
    submission = db.scalar(
        select(QuizSubmission).where(
            QuizSubmission.submission_id == submission_id,
            QuizSubmission.class_id == class_id,
        )
    )
    if submission is None or (
        not access.is_organizer
        and submission.submitted_by_id != account.account_id
    ):
        raise APIError(404, "submission_not_found", "Submission not found.")
    return submission


def _submitter_remains_eligible(
    db: Session,
    submission: QuizSubmission,
    quiz: Quiz,
) -> bool:
    account_active = db.scalar(
        select(Account.is_active).where(
            Account.account_id == submission.submitted_by_id
        )
    )
    membership_active = db.scalar(
        select(ClassMembership.membership_id).where(
            ClassMembership.class_id == submission.class_id,
            ClassMembership.account_id == submission.submitted_by_id,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
    )
    return bool(account_active) and membership_active is not None and _has_quiz_access(
        db, quiz, submission.submitted_by_id
    )


def decide_quiz_submission(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    submission_id: int,
    payload: QuizSubmissionDecision,
) -> QuizSubmissionResponse:
    access = require_class_member(db, account, class_id)
    submission = _load_visible_submission(
        db, account, access, class_id, submission_id
    )
    if not access.is_organizer:
        raise APIError(
            403,
            "not_class_organizer",
            "Only an active faculty organizer can decide submissions.",
        )
    if submission.status != SubmissionStatus.PENDING:
        raise APIError(
            409,
            "invalid_submission_transition",
            "Only a pending submission can be decided.",
        )

    if payload.status == SubmissionStatus.APPROVED:
        row = _version_and_quiz(db, submission.quiz_version_id)
        if row is None:
            raise APIError(404, "quiz_version_not_found", "Quiz version not found.")
        version, quiz = row
        _require_published_current_version(db, class_id, version, quiz)
        if not _submitter_remains_eligible(db, submission, quiz):
            raise APIError(
                409,
                "submission_no_longer_eligible",
                "The submitter is no longer eligible to submit this quiz.",
            )

    decided_at = _now()
    try:
        changed = db.execute(
            update(QuizSubmission)
            .where(
                QuizSubmission.submission_id == submission_id,
                QuizSubmission.class_id == class_id,
                QuizSubmission.status == SubmissionStatus.PENDING,
            )
            .values(
                status=payload.status,
                decided_by_id=account.account_id,
                decided_at=decided_at,
            )
        )
        if changed.rowcount != 1:
            db.rollback()
            raise APIError(
                409,
                "invalid_submission_transition",
                "Only a pending submission can be decided.",
            )
        db.commit()
    except APIError:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "quiz_submission_decision_failed",
            "Could not decide the quiz submission.",
        ) from exc

    db.expire_all()
    decided = db.get(QuizSubmission, submission_id)
    return _submission_response(decided)


def withdraw_quiz_submission(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    submission_id: int,
) -> None:
    access = require_class_member(db, account, class_id)
    submission = _load_visible_submission(
        db, account, access, class_id, submission_id
    )
    if submission.submitted_by_id != account.account_id:
        raise APIError(
            403,
            "not_submission_owner",
            "Only the original submitter can withdraw this submission.",
        )
    if submission.status != SubmissionStatus.PENDING:
        raise APIError(
            409,
            "invalid_submission_transition",
            "Only a pending submission can be withdrawn.",
        )

    try:
        changed = db.execute(
            update(QuizSubmission)
            .where(
                QuizSubmission.submission_id == submission_id,
                QuizSubmission.class_id == class_id,
                QuizSubmission.submitted_by_id == account.account_id,
                QuizSubmission.status == SubmissionStatus.PENDING,
            )
            .values(
                status=SubmissionStatus.WITHDRAWN,
                decided_by_id=account.account_id,
                decided_at=_now(),
            )
        )
        if changed.rowcount != 1:
            db.rollback()
            raise APIError(
                409,
                "invalid_submission_transition",
                "Only a pending submission can be withdrawn.",
            )
        db.commit()
    except APIError:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "quiz_submission_withdrawal_failed",
            "Could not withdraw the quiz submission.",
        ) from exc


def _approved_versions_statement(class_id: int):
    newer = aliased(QuizVersion)
    newer_published = exists(
        select(newer.quiz_version_id).where(
            newer.quiz_id == QuizVersion.quiz_id,
            newer.published_at.is_not(None),
            newer.version_number > QuizVersion.version_number,
        )
    )
    return (
        select(QuizSubmission, QuizVersion, Quiz)
        .join(
            QuizVersion,
            QuizVersion.quiz_version_id == QuizSubmission.quiz_version_id,
        )
        .join(Quiz, Quiz.quiz_id == QuizVersion.quiz_id)
        .where(
            QuizSubmission.class_id == class_id,
            QuizSubmission.status == SubmissionStatus.APPROVED,
            QuizVersion.published_at.is_not(None),
            Quiz.class_id == class_id,
            Quiz.status != QuizStatus.ARCHIVED,
            ~newer_published,
        )
    )


def list_approved_quizzes(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> list[ApprovedQuizResponse]:
    require_class_member(db, account, class_id)
    rows = db.execute(
        _approved_versions_statement(class_id).order_by(
            QuizSubmission.decided_at.desc(), QuizSubmission.submission_id.desc()
        )
    ).all()
    return [
        ApprovedQuizResponse(
            submission_id=submission.submission_id,
            quiz_id=quiz.quiz_id,
            quiz_version_id=version.quiz_version_id,
            version_number=version.version_number,
            title=version.title,
            author_id=quiz.author_id,
            approved_at=submission.decided_at,
            approved_by_id=submission.decided_by_id,
        )
        for submission, version, quiz in rows
    ]


def require_approved_quiz_version(
    db: Session,
    class_id: int,
    quiz_version_id: int,
) -> QuizVersion:
    row = db.execute(
        _approved_versions_statement(class_id).where(
            QuizVersion.quiz_version_id == quiz_version_id
        )
    ).one_or_none()
    if row is None:
        raise APIError(
            409,
            "quiz_version_not_approved",
            "This quiz version is not currently approved for the class.",
        )
    _, version, _ = row
    return version
