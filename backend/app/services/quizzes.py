from datetime import UTC, datetime
from math import ceil

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.account import Account
from app.models.classes import ClassMembership, ClassRole, MembershipStatus
from app.models.quiz import (
    AnswerChoice,
    Question,
    Quiz,
    QuizStatus,
    QuizVersion,
    QuizVisibility,
)
from app.schemas.class_dashboard import PageInfo
from app.schemas.quiz import (
    ClassQuizListItem,
    ClassQuizListPage,
    QuizCreate,
    QuizListItem,
    QuizResponse,
    QuizUpdate,
    QuizVersionResponse,
)
from app.services.class_authorization import ClassAccess, require_class_member


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


def _is_organizer(access: ClassAccess) -> bool:
    return access.is_global_admin or access.membership.role == ClassRole.ORGANIZER


def _can_read(db: Session, account: CurrentAccount, quiz: Quiz) -> bool:
    """Who may see a quiz: its owner or an organizer of its class.

    Either way they need an active membership in the quiz's class. A quiz
    from before V3 with no class is visible only to its owner.
    """
    if quiz.class_id is None:
        return quiz.author_id == account.account_id
    try:
        access = require_class_member(db, account, quiz.class_id)
    except APIError:
        return False
    return quiz.author_id == account.account_id or _is_organizer(access)


def _load_readable_quiz(db: Session, account: CurrentAccount, quiz_id: int) -> Quiz:
    quiz = _load_quiz(db, quiz_id)
    if not _can_read(db, account, quiz):
        # Same answer as a missing quiz, so IDs can't be probed.
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
    return QuizResponse(
        quiz_id=quiz.quiz_id,
        author_id=quiz.author_id,
        class_id=quiz.class_id,
        status=quiz.status,
        visibility=quiz.visibility,
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
        version=QuizVersionResponse.model_validate(_latest_published_version(quiz)),
    )


def _to_list_item(quiz: Quiz) -> QuizListItem:
    version = _latest_published_version(quiz)
    return QuizListItem(
        quiz_id=quiz.quiz_id,
        author_id=quiz.author_id,
        class_id=quiz.class_id,
        status=quiz.status,
        title=version.title,
        description=version.description,
        question_count=len(version.questions),
        created_at=quiz.created_at,
    )


def create_quiz(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    payload: QuizCreate,
) -> QuizResponse:
    """Atomically save a complete, immutable quiz owned by a class.

    Any active member or organizer may create one, and becomes its owner.
    Publishing here doesn't approve the quiz for hosting.
    """
    access = require_class_member(db, account, class_id)
    # An Admin passes require_class_member without joining, but the owner
    # must be a member of the class the quiz belongs to.
    if access.membership is None or access.membership.status != MembershipStatus.ACTIVE:
        raise APIError(404, "class_not_found", "Class not found.")
    if access.class_.archived_at is not None:
        raise APIError(
            409, "class_archived", "An archived class cannot get new quizzes."
        )

    published_at = datetime.now(UTC).replace(tzinfo=None)
    version = QuizVersion(
        version_number=1,
        title=payload.title,
        description=payload.description,
        published_at=published_at,
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
                    for choice_order, choice in enumerate(question.choices, start=1)
                ],
            )
            for question_order, question in enumerate(payload.questions, start=1)
        ],
    )
    quiz = Quiz(
        author_id=account.account_id,
        class_id=class_id,
        status=QuizStatus.PUBLISHED,
        # Visibility no longer reaches outside the class; keep it private.
        visibility=QuizVisibility.PRIVATE,
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
        # Serialize edits to the same quiz on MySQL.
        # populate_existing avoids using an already-loaded stale ORM object.
        quiz = db.scalar(
            select(Quiz)
            .where(Quiz.quiz_id == quiz_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

        if quiz is None:
            raise APIError(
                404,
                "quiz_not_found",
                "Quiz not found.",
            )

        if not _can_read(db, account, quiz):
            raise APIError(404, "quiz_not_found", "Quiz not found.")

        # Being a global administrator does not grant edit access
        # to somebody else's quiz.
        if quiz.author_id != account.account_id:
            raise APIError(
                403,
                "quiz_edit_denied",
                "Only the quiz creator can edit this quiz.",
            )

        if quiz.status != QuizStatus.PUBLISHED:
            raise APIError(
                409,
                "quiz_not_editable",
                "Only published quizzes can be edited.",
            )

        # This is a locking/current read on MySQL, so a request that
        # waited for another editor sees the newly committed version.
        versions = list(
            db.scalars(
                select(QuizVersion)
                .where(QuizVersion.quiz_id == quiz_id)
                .order_by(QuizVersion.version_number.desc())
                .with_for_update()
                .execution_options(populate_existing=True)
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

        if payload.base_version != current.version_number:
            raise APIError(
                409,
                "quiz_version_conflict",
                "This quiz changed after you opened it. "
                "Reload the latest version before saving again.",
                details={
                    "current_version": current.version_number,
                },
            )

        now = datetime.now(UTC).replace(tzinfo=None)

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
        quiz.updated_at = now
        db.flush()

        # Capture the version this request saved, rather than doing a
        # second "latest version" lookup after committing.
        response = QuizResponse(
            quiz_id=quiz.quiz_id,
            author_id=quiz.author_id,
            class_id=quiz.class_id,
            status=quiz.status,
            visibility=quiz.visibility,
            created_at=quiz.created_at,
            updated_at=quiz.updated_at,
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
    """The caller's own quizzes, across the classes they're active in.

    There is no app-wide catalog any more; class quizzes are listed per class.
    """
    statement = (
        select(Quiz)
        .join(
            ClassMembership,
            (ClassMembership.class_id == Quiz.class_id)
            & (ClassMembership.account_id == account.account_id),
        )
        .where(
            Quiz.author_id == account.account_id,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
        .options(selectinload(Quiz.versions).selectinload(QuizVersion.questions))
        .order_by(Quiz.created_at.desc(), Quiz.quiz_id.desc())
    )
    return [_to_list_item(quiz) for quiz in db.scalars(statement).all()]


def get_quiz(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
) -> QuizResponse:
    return _to_response(_load_readable_quiz(db, account, quiz_id))


def list_class_quizzes(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    *,
    page: int,
    page_size: int,
) -> ClassQuizListPage:
    """A class's quizzes, newest first.

    Organizers see every quiz in the class; members see the ones they own.
    """
    access = require_class_member(db, account, class_id)
    condition = Quiz.class_id == class_id
    if not _is_organizer(access):
        condition = condition & (Quiz.author_id == account.account_id)

    total = db.scalar(select(func.count(Quiz.quiz_id)).where(condition)) or 0
    rows = db.execute(
        select(Quiz, Account.display_name)
        .join(Account, Account.account_id == Quiz.author_id)
        .where(condition)
        .options(selectinload(Quiz.versions).selectinload(QuizVersion.questions))
        .order_by(Quiz.created_at.desc(), Quiz.quiz_id.desc())
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()

    items = []
    for quiz, author_name in rows:
        version = _latest_published_version(quiz)
        items.append(
            ClassQuizListItem(
                **_to_list_item(quiz).model_dump(),
                author_name=author_name,
                version_number=version.version_number,
                updated_at=quiz.updated_at,
            )
        )
    return ClassQuizListPage(
        class_id=class_id,
        items=items,
        pagination=PageInfo(
            page=page,
            page_size=page_size,
            total_items=total,
            total_pages=ceil(total / page_size),
        ),
    )


def get_class_quiz(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_id: int,
) -> QuizResponse:
    require_class_member(db, account, class_id)
    quiz = _load_readable_quiz(db, account, quiz_id)
    if quiz.class_id != class_id:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    return _to_response(quiz)


def archive_quiz(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
) -> QuizResponse:
    quiz = _load_readable_quiz(db, account, quiz_id)
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
