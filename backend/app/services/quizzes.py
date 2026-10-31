from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.account import Account
from app.models.classes import ClassMembership, MembershipStatus
from app.models.quiz import (
    AnswerChoice,
    CollaboratorPermission,
    Question,
    Quiz,
    QuizCollaborator,
    QuizStatus,
    QuizVersion,
    QuizVisibility,
)
from app.schemas.quiz import (
    QuizCollaboratorCreate,
    QuizCollaboratorResponse,
    QuizCreate,
    QuizListItem,
    QuizResponse,
    QuizUpdate,
    QuizVersionResponse,
)


def _quiz_query(quiz_id: int):
    return (
        select(Quiz)
        .where(Quiz.quiz_id == quiz_id)
        .options(
            selectinload(Quiz.versions)
            .selectinload(QuizVersion.questions)
            .selectinload(Question.choices)
        )
    )


def _load_quiz(db: Session, quiz_id: int) -> Quiz:
    quiz = db.scalar(_quiz_query(quiz_id))
    if quiz is None:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    return quiz


def _latest_published_version(quiz: Quiz) -> QuizVersion:
    published = [
        version for version in quiz.versions if version.published_at is not None
    ]

    if not published:
        raise APIError(
            409,
            "quiz_not_published",
            "The quiz has no published version.",
        )

    return max(
        published,
        key=lambda version: version.version_number,
    )


def _to_response(quiz: Quiz) -> QuizResponse:
    return _to_response_with_version(quiz, _latest_published_version(quiz))


def _to_response_with_version(
    quiz: Quiz,
    version: QuizVersion,
) -> QuizResponse:
    return QuizResponse(
        quiz_id=quiz.quiz_id,
        author_id=quiz.author_id,
        class_id=quiz.class_id,
        revision=quiz.revision,
        status=quiz.status,
        visibility=quiz.visibility,
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
        version=QuizVersionResponse.model_validate(version),
    )


def _latest_editor_version(quiz: Quiz) -> QuizVersion:
    drafts = [version for version in quiz.versions if version.published_at is None]
    if drafts:
        return max(drafts, key=lambda version: version.version_number)
    return _latest_published_version(quiz)


def _questions_from_payload(payload: QuizCreate) -> list[Question]:
    return [
        Question(
            question_order=question_order,
            question_text=question.question_text,
            explanation=question.explanation,
            time_limit_seconds=question.time_limit_seconds,
            base_points=question.base_points,
            choices=[
                AnswerChoice(
                    choice_order=choice_order,
                    choice_text=choice.choice_text,
                    is_correct=choice.is_correct,
                )
                for choice_order, choice in enumerate(question.choices, start=1)
            ],
        )
        for question_order, question in enumerate(payload.questions, start=1)
    ]


def _to_list_item(quiz: Quiz) -> QuizListItem:
    version = _latest_published_version(quiz)
    return QuizListItem(
        quiz_id=quiz.quiz_id,
        author_id=quiz.author_id,
        status=quiz.status,
        title=version.title,
        description=version.description,
        question_count=len(version.questions),
        created_at=quiz.created_at,
    )


def create_quiz(
    db: Session,
    account: CurrentAccount,
    payload: QuizCreate,
    *,
    class_id: int | None = None,
) -> QuizResponse:
    """Atomically save a complete, public, immutable MVP quiz."""
    published_at = datetime.now(UTC).replace(tzinfo=None)
    version = QuizVersion(
        version_number=1,
        title=payload.title,
        description=payload.description,
        published_at=published_at,
        questions=_questions_from_payload(payload),
    )
    quiz = Quiz(
        author_id=account.account_id,
        class_id=class_id,
        revision=1,
        status=QuizStatus.PUBLISHED,
        visibility=QuizVisibility.PUBLIC,
        versions=[version],
    )
    db.add(quiz)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, "quiz_save_failed", "Could not save the quiz.") from exc

    quiz_id = quiz.quiz_id
    db.expire_all()
    return _to_response(_load_quiz(db, quiz_id))


def update_quiz(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
    payload: QuizUpdate,
) -> QuizResponse:
    """Publish a new revision without changing any previous version."""

    try:
        quiz = db.get(Quiz, quiz_id)

        if quiz is None:
            raise APIError(
                404,
                "quiz_not_found",
                "Quiz not found.",
            )

        _require_quiz_editor(db, account, quiz)

        if quiz.status != QuizStatus.PUBLISHED:
            raise APIError(
                409,
                "quiz_not_editable",
                "Only published quizzes can be edited.",
            )

        versions = list(
            db.scalars(
                select(QuizVersion)
                .where(QuizVersion.quiz_id == quiz_id)
                .order_by(QuizVersion.version_number.desc())
            ).all()
        )

        current = next(
            (version for version in versions if version.published_at is not None),
            None,
        )

        if current is None:
            raise APIError(
                409,
                "quiz_not_published",
                "The quiz has no published version.",
            )

        if payload.expected_revision != quiz.revision:
            raise APIError(
                409,
                "quiz_edit_conflict",
                "This quiz changed after you opened it. "
                "Reload the latest version before saving again.",
                details={
                    "current_revision": quiz.revision,
                },
            )

        now = datetime.now(UTC).replace(tzinfo=None)

        # This conditional UPDATE is the optimistic lock. On MySQL, concurrent
        # requests with the same expected revision serialize on the row and
        # only the first predicate remains true.
        changed = db.execute(
            update(Quiz)
            .where(
                Quiz.quiz_id == quiz_id,
                Quiz.revision == payload.expected_revision,
            )
            .values(
                revision=Quiz.revision + 1,
                updated_at=now,
            )
        )
        if changed.rowcount != 1:
            db.rollback()
            current_revision = db.scalar(
                select(Quiz.revision).where(Quiz.quiz_id == quiz_id)
            )
            raise APIError(
                409,
                "quiz_edit_conflict",
                "This quiz changed after you opened it. "
                "Reload the latest version before saving again.",
                details={"current_revision": current_revision},
            )

        # Include any existing unpublished versions when allocating
        # a number, even though this feature does not create drafts.
        next_number = max(version.version_number for version in versions) + 1

        revision = QuizVersion(
            quiz_id=quiz.quiz_id,
            version_number=next_number,
            title=payload.title,
            description=payload.description,
            published_at=now,
            questions=[
                Question(
                    question_order=question_order,
                    question_text=question.question_text,
                    explanation=question.explanation,
                    time_limit_seconds=question.time_limit_seconds,
                    base_points=question.base_points,
                    choices=[
                        AnswerChoice(
                            choice_order=choice_order,
                            choice_text=choice.choice_text,
                            is_correct=choice.is_correct,
                        )
                        for choice_order, choice in enumerate(
                            question.choices,
                            start=1,
                        )
                    ],
                )
                for question_order, question in enumerate(
                    payload.questions,
                    start=1,
                )
            ],
        )

        # Insert new rows. Never replace quiz.versions or modify the
        # previous version's questions and choices.
        db.add(revision)
        db.flush()

        # Capture the version this request saved, rather than doing a
        # second "latest version" lookup after committing.
        response = QuizResponse(
            quiz_id=quiz.quiz_id,
            author_id=quiz.author_id,
            class_id=quiz.class_id,
            revision=payload.expected_revision + 1,
            status=quiz.status,
            visibility=quiz.visibility,
            created_at=quiz.created_at,
            updated_at=now,
            version=QuizVersionResponse.model_validate(revision),
        )

        db.commit()
        return response

    except APIError:
        db.rollback()
        raise

    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "quiz_update_failed",
            "Could not save the quiz changes.",
        ) from exc


def list_quizzes(
    db: Session,
    account: CurrentAccount,
) -> list[QuizListItem]:
    """List public quizzes, or every quiz when requested by an Admin."""
    statement = (
        select(Quiz)
        .options(selectinload(Quiz.versions).selectinload(QuizVersion.questions))
        .order_by(Quiz.created_at.desc(), Quiz.quiz_id.desc())
    )
    if not account.is_admin:
        statement = statement.where(
            (Quiz.status == QuizStatus.PUBLISHED)
            | (
                (Quiz.author_id == account.account_id)
                & (Quiz.status == QuizStatus.ARCHIVED)
            )
        )
    return [_to_list_item(quiz) for quiz in db.scalars(statement).all()]


def get_quiz(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
) -> QuizResponse:
    quiz = _load_quiz(db, quiz_id)
    if quiz.status != QuizStatus.PUBLISHED and not (
        quiz.author_id == account.account_id or account.is_admin
    ):
        # Do not reveal archived or legacy draft quizzes to other users.
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    return _to_response(quiz)


def archive_quiz(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
) -> QuizResponse:
    quiz = _load_quiz(db, quiz_id)
    if quiz.author_id != account.account_id and not account.is_admin:
        raise APIError(
            403,
            "quiz_access_denied",
            "Only the quiz author or an Admin can archive it.",
        )
    if quiz.status == QuizStatus.ARCHIVED:
        return _to_response(quiz)

    quiz.status = QuizStatus.ARCHIVED
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500, "quiz_archive_failed", "Could not archive the quiz."
        ) from exc

    db.expire_all()
    return _to_response(_load_quiz(db, quiz_id))


def _active_membership(
    db: Session,
    class_id: int,
    account_id: int,
) -> ClassMembership | None:
    return db.scalar(
        select(ClassMembership).where(
            ClassMembership.class_id == class_id,
            ClassMembership.account_id == account_id,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
    )


def _require_active_class_member(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassMembership:
    membership = _active_membership(db, class_id, account.account_id)
    if membership is None:
        raise APIError(404, "class_not_found", "Class not found.")
    return membership


def _class_quiz(db: Session, class_id: int, quiz_id: int) -> Quiz:
    quiz = _load_quiz(db, quiz_id)
    if quiz.class_id != class_id:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    return quiz


def _active_collaborator(
    db: Session,
    quiz_id: int,
    account_id: int,
) -> QuizCollaborator | None:
    return db.scalar(
        select(QuizCollaborator).where(
            QuizCollaborator.quiz_id == quiz_id,
            QuizCollaborator.account_id == account_id,
            QuizCollaborator.revoked_at.is_(None),
        )
    )


def _require_quiz_editor(
    db: Session,
    account: CurrentAccount,
    quiz: Quiz,
) -> None:
    if quiz.class_id is not None:
        _require_active_class_member(db, account, quiz.class_id)
    if quiz.author_id == account.account_id:
        return
    if _active_collaborator(db, quiz.quiz_id, account.account_id) is not None:
        return
    raise APIError(
        403,
        "quiz_edit_denied",
        "Only the quiz owner or an active editor can edit this quiz.",
    )


def create_class_quiz(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    payload: QuizCreate,
) -> QuizResponse:
    _require_active_class_member(db, account, class_id)
    draft = QuizVersion(
        version_number=1,
        title=payload.title,
        description=payload.description,
        published_at=None,
        questions=_questions_from_payload(payload),
    )
    quiz = Quiz(
        author_id=account.account_id,
        class_id=class_id,
        revision=1,
        status=QuizStatus.DRAFT,
        visibility=QuizVisibility.PRIVATE,
        versions=[draft],
    )
    db.add(quiz)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, "quiz_save_failed", "Could not save the quiz.") from exc
    quiz_id = quiz.quiz_id
    db.expire_all()
    stored = _load_quiz(db, quiz_id)
    return _to_response_with_version(stored, _latest_editor_version(stored))


def get_class_quiz(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_id: int,
) -> QuizResponse:
    _require_active_class_member(db, account, class_id)
    quiz = _class_quiz(db, class_id, quiz_id)
    # Draft/editor detail is private to its owner and named collaborators.
    if quiz.author_id != account.account_id and _active_collaborator(
        db, quiz_id, account.account_id
    ) is None:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    return _to_response_with_version(quiz, _latest_editor_version(quiz))


def update_class_quiz(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_id: int,
    payload: QuizUpdate,
) -> QuizResponse:
    _require_active_class_member(db, account, class_id)
    quiz = _class_quiz(db, class_id, quiz_id)
    _require_quiz_editor(db, account, quiz)

    if payload.expected_revision != quiz.revision:
        raise APIError(
            409,
            "quiz_edit_conflict",
            "This quiz changed after you opened it. "
            "Reload the latest version before saving again.",
            details={"current_revision": quiz.revision},
        )

    now = datetime.now(UTC).replace(tzinfo=None)
    changed = db.execute(
        update(Quiz)
        .where(
            Quiz.quiz_id == quiz_id,
            Quiz.revision == payload.expected_revision,
        )
        .values(revision=Quiz.revision + 1, updated_at=now)
    )
    if changed.rowcount != 1:
        db.rollback()
        current_revision = db.scalar(
            select(Quiz.revision).where(Quiz.quiz_id == quiz_id)
        )
        raise APIError(
            409,
            "quiz_edit_conflict",
            "This quiz changed after you opened it. "
            "Reload the latest version before saving again.",
            details={"current_revision": current_revision},
        )

    draft = next(
        (version for version in reversed(quiz.versions) if version.published_at is None),
        None,
    )
    if draft is None:
        draft = QuizVersion(
            quiz_id=quiz_id,
            version_number=max(version.version_number for version in quiz.versions) + 1,
            published_at=None,
        )
        db.add(draft)
    else:
        # Delete and flush the old nested rows before inserting positions 1..N;
        # otherwise MySQL's unique ordering constraints see both generations.
        for question in list(draft.questions):
            db.delete(question)
        db.flush()

    draft.title = payload.title
    draft.description = payload.description
    draft.questions = _questions_from_payload(payload)
    quiz.status = QuizStatus.DRAFT
    try:
        db.flush()
        response = QuizResponse(
            quiz_id=quiz.quiz_id,
            author_id=quiz.author_id,
            class_id=quiz.class_id,
            revision=payload.expected_revision + 1,
            status=QuizStatus.DRAFT,
            visibility=quiz.visibility,
            created_at=quiz.created_at,
            updated_at=now,
            version=QuizVersionResponse.model_validate(draft),
        )
        db.commit()
        return response
    except APIError:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "quiz_update_failed",
            "Could not save the quiz changes.",
        ) from exc


def _collaborator_response(
    collaborator: QuizCollaborator,
    account: Account,
) -> QuizCollaboratorResponse:
    return QuizCollaboratorResponse(
        quiz_id=collaborator.quiz_id,
        account_id=collaborator.account_id,
        email=account.email,
        display_name=account.display_name,
        permission=collaborator.permission,
        shared_by_id=collaborator.shared_by_id,
        created_at=collaborator.created_at,
    )


def _require_collaborator_owner(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_id: int,
) -> Quiz:
    _require_active_class_member(db, account, class_id)
    quiz = _class_quiz(db, class_id, quiz_id)
    if quiz.author_id != account.account_id:
        raise APIError(
            403,
            "collaborator_management_denied",
            "Only the quiz owner can manage collaborators.",
        )
    return quiz


def list_quiz_collaborators(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_id: int,
) -> list[QuizCollaboratorResponse]:
    _require_collaborator_owner(db, account, class_id, quiz_id)
    rows = db.execute(
        select(QuizCollaborator, Account)
        .join(Account, Account.account_id == QuizCollaborator.account_id)
        .where(
            QuizCollaborator.quiz_id == quiz_id,
            QuizCollaborator.revoked_at.is_(None),
        )
        .order_by(Account.display_name, Account.account_id)
    ).all()
    return [
        _collaborator_response(collaborator, target)
        for collaborator, target in rows
    ]


def add_quiz_collaborator(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_id: int,
    payload: QuizCollaboratorCreate,
) -> QuizCollaboratorResponse:
    quiz = _require_collaborator_owner(db, account, class_id, quiz_id)
    target = db.scalar(
        select(Account).where(func.lower(Account.email) == payload.email)
    )
    if target is None:
        raise APIError(404, "account_not_found", "No account has that email address.")
    if target.account_id == quiz.author_id:
        raise APIError(
            409,
            "quiz_owner_cannot_collaborate",
            "The quiz owner cannot also be a collaborator.",
        )
    if (
        not target.is_active
        or _active_membership(db, class_id, target.account_id) is None
    ):
        raise APIError(
            409,
            "not_class_member",
            "The account is not an active member of this class.",
        )

    collaborator = db.get(QuizCollaborator, (quiz_id, target.account_id))
    now = datetime.now(UTC).replace(tzinfo=None)
    if collaborator is not None and collaborator.revoked_at is None:
        raise APIError(
            409,
            "already_quiz_collaborator",
            "That account is already a quiz collaborator.",
        )
    if collaborator is None:
        collaborator = QuizCollaborator(
            quiz_id=quiz_id,
            account_id=target.account_id,
            permission=payload.permission,
            shared_by_id=account.account_id,
        )
        db.add(collaborator)
    else:
        collaborator.permission = payload.permission
        collaborator.shared_by_id = account.account_id
        collaborator.created_at = now
        collaborator.revoked_at = None
        collaborator.revoked_by_id = None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise APIError(
            409,
            "already_quiz_collaborator",
            "That account is already a quiz collaborator.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "quiz_collaborator_add_failed",
            "Could not add the quiz collaborator.",
        ) from exc
    db.refresh(collaborator)
    return _collaborator_response(collaborator, target)


def revoke_quiz_collaborator(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_id: int,
    target_account_id: int,
) -> None:
    _require_collaborator_owner(db, account, class_id, quiz_id)
    collaborator = db.get(QuizCollaborator, (quiz_id, target_account_id))
    if collaborator is None or collaborator.revoked_at is not None:
        raise APIError(404, "quiz_collaborator_not_found", "Collaborator not found.")
    collaborator.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    collaborator.revoked_by_id = account.account_id
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "quiz_collaborator_revoke_failed",
            "Could not revoke the quiz collaborator.",
        ) from exc
