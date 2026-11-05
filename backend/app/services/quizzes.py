from datetime import UTC, datetime
from math import ceil

from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.account import Account
from app.models.classes import ClassMembership, ClassRole, MembershipStatus
from app.models.quiz import (
    AnswerChoice,
    CollaboratorEventType,
    CollaboratorPermission,
    Question,
    Quiz,
    QuizCollaborator,
    QuizCollaboratorEvent,
    QuizStatus,
    QuizVersion,
    QuizVisibility,
)
from app.schemas.class_dashboard import PageInfo
from app.schemas.quiz import (
    ClassQuizListItem,
    ClassQuizListPage,
    QuizCollaboratorCreate,
    QuizCollaboratorResponse,
    QuizCreate,
    QuizListItem,
    QuizPublish,
    QuestionCreate,
    QuestionResponse,
    QuestionUpdate,
    QuestionUpdateResponse,
    QuizResponse,
    QuizUpdate,
    QuizVersionResponse,
)
from app.services.class_authorization import get_class, get_class_membership


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


def _active_collaborator(
    db: Session,
    quiz_id: int,
    account_id: int,
    *,
    lock: bool = False,
) -> QuizCollaborator | None:
    statement = select(QuizCollaborator).where(
        QuizCollaborator.quiz_id == quiz_id,
        QuizCollaborator.account_id == account_id,
        QuizCollaborator.revoked_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement)


def _require_current_active_account(
    db: Session,
    account: CurrentAccount,
    *,
    lock: bool = False,
) -> Account:
    statement = select(Account).where(
        Account.account_id == account.account_id,
        Account.is_active.is_(True),
    )
    if lock:
        statement = statement.with_for_update()
    stored_account = db.scalar(statement)
    if stored_account is None:
        raise APIError(403, "inactive_account", "This account is inactive.")
    return stored_account


def _require_active_membership(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassMembership:
    """The caller's ACTIVE membership in the class, or 404 class_not_found.

    V3 has no app-wide authority over classes: being an Admin (faculty)
    doesn't let anyone into a class they aren't an active member of.
    """
    get_class(db, class_id)
    membership = get_class_membership(db, class_id, account.account_id)
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        raise APIError(404, "class_not_found", "Class not found.")
    return membership


def _can_read(db: Session, account: CurrentAccount, quiz: Quiz) -> bool:
    """Who may see a quiz: its owner or an organizer of its class.

    Either way they need an active membership in the quiz's class. A quiz
    from before V3 with no class is visible only to its owner.
    """
    if quiz.class_id is None:
        return quiz.author_id == account.account_id
    try:
        membership = _require_active_membership(db, account, quiz.class_id)
    except APIError:
        return False
    return (
        quiz.author_id == account.account_id
        or membership.role == ClassRole.ORGANIZER
        or _active_collaborator(db, quiz.quiz_id, account.account_id) is not None
    )


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


def _latest_editor_version(quiz: Quiz) -> QuizVersion:
    """The version people work on: the newest draft, else the newest
    published version."""
    drafts = [version for version in quiz.versions if version.published_at is None]
    if drafts:
        return max(drafts, key=lambda version: version.version_number)
    return _latest_published_version(quiz)


def _to_response(
    db: Session,
    account: CurrentAccount,
    quiz: Quiz,
) -> QuizResponse:
    return _to_response_with_version(
        quiz,
        _latest_editor_version(quiz),
        can_edit=_can_edit(db, account, quiz),
    )


def _to_response_with_version(
    quiz: Quiz,
    version: QuizVersion,
    *,
    can_edit: bool,
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
        can_edit=can_edit,
        version=QuizVersionResponse.model_validate(version),
    )


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


def _question_from_payload(
    payload: QuestionCreate,
    *,
    question_order: int,
) -> Question:
    return Question(
        question_order=question_order,
        question_text=payload.question_text,
        explanation=payload.explanation,
        time_limit_seconds=payload.time_limit_seconds,
        base_points=payload.base_points,
        choices=[
            AnswerChoice(
                choice_order=choice_order,
                choice_text=choice.choice_text,
                is_correct=choice.is_correct,
            )
            for choice_order, choice in enumerate(payload.choices, start=1)
        ],
    )


def _clone_questions(questions: list[Question]) -> list[Question]:
    """Copy immutable published questions into a new editable draft."""
    return [
        Question(
            question_order=question.question_order,
            question_type=question.question_type,
            question_text=question.question_text,
            explanation=question.explanation,
            time_limit_seconds=question.time_limit_seconds,
            base_points=question.base_points,
            revision=question.revision,
            choices=[
                AnswerChoice(
                    choice_order=choice.choice_order,
                    choice_text=choice.choice_text,
                    is_correct=choice.is_correct,
                )
                for choice in question.choices
            ],
        )
        for question in questions
    ]


def _same_question_content(left: Question, right: Question) -> bool:
    """Whether an ID remap still points at an unchanged logical question.

    Question order alone is not sufficient: a whole-quiz edit can replace the
    question at that position while resetting its row revision to one.
    """
    return (
        left.question_type == right.question_type
        and left.question_text == right.question_text
        and left.explanation == right.explanation
        and left.time_limit_seconds == right.time_limit_seconds
        and left.base_points == right.base_points
        and [
            (choice.choice_order, choice.choice_text, choice.is_correct)
            for choice in left.choices
        ]
        == [
            (choice.choice_order, choice.choice_text, choice.is_correct)
            for choice in right.choices
        ]
    )


def _to_list_item(quiz: Quiz) -> QuizListItem:
    version = _latest_editor_version(quiz)
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
    """Atomically save a new quiz draft owned by a class.

    Any active member or organizer may create one, and becomes its owner.
    The draft can't be hosted until it's published, and publishing doesn't
    approve it for hosting either.
    """
    _require_active_membership(db, account, class_id)
    if get_class(db, class_id).archived_at is not None:
        raise APIError(
            409, "class_archived", "An archived class cannot get new quizzes."
        )

    version = QuizVersion(
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
    return _to_response(db, account, _load_quiz(db, quiz_id))


def update_quiz(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
    payload: QuizUpdate,
) -> QuizResponse:
    """Compatibility route for the editor; V3 writes the class-owned draft."""
    quiz = _load_quiz(db, quiz_id)
    if quiz.class_id is None:
        raise APIError(
            409,
            "quiz_class_required",
            "Assign this legacy quiz to a class before editing it.",
        )
    return update_class_quiz(db, account, quiz.class_id, quiz_id, payload)


def list_quizzes(
    db: Session,
    account: CurrentAccount,
) -> list[QuizListItem]:
    """The caller's own quizzes, across the classes they're active in.

    There is no app-wide catalog any more; class quizzes are listed per class.
    """
    collaborator_access = exists(
        select(1).where(
            QuizCollaborator.quiz_id == Quiz.quiz_id,
            QuizCollaborator.account_id == account.account_id,
            QuizCollaborator.revoked_at.is_(None),
        )
    )
    statement = (
        select(Quiz)
        .join(
            ClassMembership,
            (ClassMembership.class_id == Quiz.class_id)
            & (ClassMembership.account_id == account.account_id),
        )
        .where(
            ClassMembership.status == MembershipStatus.ACTIVE,
            or_(
                Quiz.author_id == account.account_id,
                collaborator_access,
            ),
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
    return _to_response(db, account, _load_readable_quiz(db, account, quiz_id))


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
    membership = _require_active_membership(db, account, class_id)
    condition = Quiz.class_id == class_id
    if membership.role != ClassRole.ORGANIZER:
        collaborator_access = exists(
            select(1).where(
                QuizCollaborator.quiz_id == Quiz.quiz_id,
                QuizCollaborator.account_id == account.account_id,
                QuizCollaborator.revoked_at.is_(None),
            )
        )
        condition = and_(
            condition,
            or_(Quiz.author_id == account.account_id, collaborator_access),
        )

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
        version = _latest_editor_version(quiz)
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
    _require_active_membership(db, account, class_id)
    quiz = _load_readable_quiz(db, account, quiz_id)
    if quiz.class_id != class_id:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    return _to_response(db, account, quiz)


def archive_quiz(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
) -> QuizResponse:
    # Archive shares the quiz row as its serialization boundary with draft
    # edits and publication. Without this lock (and a revision increment), a
    # publisher that read the old revision could change ARCHIVED back to
    # PUBLISHED after the archive committed.
    db.execute(
        select(Quiz.quiz_id)
        .where(Quiz.quiz_id == quiz_id)
        .with_for_update()
    )
    db.expire_all()
    _require_current_active_account(db, account, lock=True)
    quiz = _load_readable_quiz(db, account, quiz_id)
    # Only the owner; being an Admin or a class organizer isn't enough.
    if quiz.author_id != account.account_id:
        raise APIError(
            403,
            "quiz_access_denied",
            "Only the quiz owner can archive it.",
        )
    if quiz.status == QuizStatus.ARCHIVED:
        return _to_response(db, account, quiz)

    quiz.status = QuizStatus.ARCHIVED
    quiz.revision += 1
    quiz.updated_at = datetime.now(UTC).replace(tzinfo=None)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500, "quiz_archive_failed", "Could not archive the quiz."
        ) from exc

    db.expire_all()
    return _to_response(db, account, _load_quiz(db, quiz_id))


def _active_membership(
    db: Session,
    class_id: int,
    account_id: int,
    *,
    lock: bool = False,
) -> ClassMembership | None:
    statement = select(ClassMembership).where(
        ClassMembership.class_id == class_id,
        ClassMembership.account_id == account_id,
        ClassMembership.status == MembershipStatus.ACTIVE,
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement)


def _require_active_class_member(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    *,
    lock: bool = False,
) -> ClassMembership:
    membership = _active_membership(
        db,
        class_id,
        account.account_id,
        lock=lock,
    )
    if membership is None:
        raise APIError(404, "class_not_found", "Class not found.")
    return membership


def _class_quiz(db: Session, class_id: int, quiz_id: int) -> Quiz:
    quiz = _load_quiz(db, quiz_id)
    if quiz.class_id != class_id:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    return quiz


def _lock_class_quiz_for_update(
    db: Session,
    class_id: int,
    quiz_id: int,
) -> Quiz:
    """Lock and reload a class quiz before choosing its editable version."""
    locked_id = db.scalar(
        select(Quiz.quiz_id)
        .where(
            Quiz.quiz_id == quiz_id,
            Quiz.class_id == class_id,
        )
        .with_for_update()
    )
    if locked_id is None:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    db.expire_all()
    return _class_quiz(db, class_id, quiz_id)


def _require_quiz_editor(
    db: Session,
    account: CurrentAccount,
    quiz: Quiz,
    *,
    lock_access: bool = False,
) -> None:
    _require_current_active_account(db, account, lock=lock_access)
    if quiz.class_id is not None:
        _require_active_class_member(
            db,
            account,
            quiz.class_id,
            lock=lock_access,
        )
    if quiz.author_id == account.account_id:
        return
    if _active_collaborator(
        db,
        quiz.quiz_id,
        account.account_id,
        lock=lock_access,
    ) is not None:
        return
    raise APIError(
        403,
        "quiz_edit_denied",
        "Only the quiz owner or an active editor can edit this quiz.",
    )


def _can_edit(db: Session, account: CurrentAccount, quiz: Quiz) -> bool:
    if quiz.status == QuizStatus.ARCHIVED:
        return False
    if quiz.class_id is not None and _active_membership(
        db, quiz.class_id, account.account_id
    ) is None:
        return False
    return (
        quiz.author_id == account.account_id
        or _active_collaborator(db, quiz.quiz_id, account.account_id) is not None
    )


def require_quiz_editor_access(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
) -> Quiz:
    """Authorize an editor connection without exposing unreadable quiz IDs."""
    quiz = _load_quiz(db, quiz_id)
    try:
        _require_quiz_editor(db, account, quiz)
    except APIError as exc:
        if exc.status_code in (403, 404):
            raise APIError(404, "quiz_not_found", "Quiz not found.") from exc
        raise
    if quiz.status == QuizStatus.ARCHIVED:
        raise APIError(409, "quiz_not_editable", "An archived quiz cannot be edited.")
    return quiz


def update_class_quiz_question(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_id: int,
    question_id: int,
    payload: QuestionUpdate,
) -> QuestionUpdateResponse:
    """Save one question without revision-locking sibling questions.

    The quiz lock makes version selection atomic with archive/publication and
    draft creation. The compare-and-swap on ``question.revision`` then rejects
    two editors that changed the same question from the same revision.
    """
    quiz = _lock_class_quiz_for_update(db, class_id, quiz_id)
    _require_quiz_editor(db, account, quiz, lock_access=True)
    if quiz.status == QuizStatus.ARCHIVED:
        raise APIError(
            409,
            "quiz_not_editable",
            "An archived quiz cannot be edited.",
        )

    editor_version = _latest_editor_version(quiz)
    source = next(
        (question for question in editor_version.questions if question.question_id == question_id),
        None,
    )
    question = source
    mapped_source = None
    if source is None and editor_version.published_at is None:
        # A client may still hold IDs from the published version while another
        # editor has already created the next draft. Map only from the direct
        # published predecessor; older historical IDs must not target a newer
        # draft merely because their question order happens to match.
        predecessor = max(
            (
                version
                for version in quiz.versions
                if version.published_at is not None
                and version.version_number < editor_version.version_number
            ),
            key=lambda version: version.version_number,
            default=None,
        )
        stale_source = (
            next(
                (
                    item
                    for item in predecessor.questions
                    if item.question_id == question_id
                ),
                None,
            )
            if predecessor is not None
            else None
        )
        if stale_source is not None:
            mapped_source = stale_source
            question = next(
                (
                    item
                    for item in editor_version.questions
                    if item.question_order == stale_source.question_order
                ),
                None,
            )
    if source is None:
        if question is None:
            raise APIError(404, "question_not_found", "Question not found.")

    if editor_version.published_at is not None:
        # The quiz row is already locked, so this immutable-version copy and
        # the selection of its target question cannot race archive, publish,
        # or another editor creating the next draft.
        source_order = source.question_order
        draft = QuizVersion(
            quiz_id=quiz_id,
            version_number=max(
                version.version_number for version in quiz.versions
            ) + 1,
            title=editor_version.title,
            description=editor_version.description,
            published_at=None,
            questions=_clone_questions(editor_version.questions),
        )
        db.add(draft)
        db.flush()
        editor_version = draft
        quiz.status = QuizStatus.DRAFT
        db.flush()
        question = next(
            item for item in editor_version.questions
            if item.question_order == source_order
        )
        if question.question_id != source.question_id:
            mapped_source = source

    if (
        mapped_source is not None
        and not _same_question_content(mapped_source, question)
    ):
        db.rollback()
        raise APIError(
            409,
            "question_edit_conflict",
            "This question changed after you opened it. Reload that question before saving.",
            details={"current_revision": question.revision},
        )

    if payload.expected_revision != question.revision:
        db.rollback()
        raise APIError(
            409,
            "question_edit_conflict",
            "This question changed after you opened it. Reload that question before saving.",
            details={"current_revision": question.revision},
        )

    now = datetime.now(UTC).replace(tzinfo=None)
    # Advance the aggregate revision while the quiz row is still locked.
    # Different-question saves queue briefly on this row, then each applies
    # its independent question compare-and-swap against the current draft.
    claimed_draft = db.execute(
        update(Quiz)
        .where(
            Quiz.quiz_id == quiz_id,
            Quiz.status == QuizStatus.DRAFT,
        )
        .values(
            revision=Quiz.revision + 1,
            updated_at=now,
        )
    )
    if claimed_draft.rowcount != 1:
        db.rollback()
        current_revision = db.scalar(
            select(Quiz.revision).where(Quiz.quiz_id == quiz_id)
        )
        raise APIError(
            409,
            "quiz_edit_conflict",
            "This quiz was published while the question was being saved. "
            "Reload the latest version before editing again.",
            details={"current_revision": current_revision},
        )

    changed = db.execute(
        update(Question)
        .where(
            Question.question_id == question.question_id,
            Question.revision == payload.expected_revision,
        )
        .values(
            question_text=payload.question_text,
            explanation=payload.explanation,
            time_limit_seconds=payload.time_limit_seconds,
            base_points=payload.base_points,
            revision=Question.revision + 1,
            updated_at=now,
        )
    )
    if changed.rowcount != 1:
        db.rollback()
        current_revision = db.scalar(
            select(Question.revision).where(Question.question_id == question.question_id)
        )
        raise APIError(
            409,
            "question_edit_conflict",
            "This question changed after you opened it. Reload that question before saving.",
            details={"current_revision": current_revision},
        )

    try:
        # Choices are part of the question aggregate and share its revision.
        for choice in list(question.choices):
            db.delete(choice)
        db.flush()
        question.choices = [
            AnswerChoice(
                choice_order=choice_order,
                choice_text=choice.choice_text,
                is_correct=choice.is_correct,
            )
            for choice_order, choice in enumerate(payload.choices, start=1)
        ]
        db.flush()
        db.expire(question)
        quiz_revision = db.scalar(
            select(Quiz.revision).where(Quiz.quiz_id == quiz_id)
        )
        response = QuestionUpdateResponse(
            quiz_id=quiz_id,
            quiz_revision=quiz_revision,
            question=QuestionResponse.model_validate(question),
        )
        db.commit()
        return response
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "question_update_failed",
            "Could not save the question changes.",
        ) from exc


def add_class_quiz_question(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_id: int,
    payload: QuestionCreate,
) -> QuestionUpdateResponse:
    """Append one question without replacing or revision-locking its siblings.

    The quiz row lock only serializes concurrent appends and the one-time copy
    from an immutable published version. Editors saving existing questions use
    their independent question revisions and can proceed without a stale
    whole-quiz conflict.
    """
    _require_active_class_member(db, account, class_id)

    # Serialize order allocation for two simultaneous appends. This does not
    # lock any Question row, so an editor may save another question at once.
    db.execute(
        select(Quiz.quiz_id)
        .where(Quiz.quiz_id == quiz_id)
        .with_for_update()
    )
    db.expire_all()
    quiz = _class_quiz(db, class_id, quiz_id)
    _require_quiz_editor(db, account, quiz, lock_access=True)
    if quiz.status == QuizStatus.ARCHIVED:
        raise APIError(409, "quiz_not_editable", "An archived quiz cannot be edited.")

    editor_version = _latest_editor_version(quiz)
    if editor_version.published_at is not None:
        editor_version = QuizVersion(
            quiz_id=quiz_id,
            version_number=max(
                version.version_number for version in quiz.versions
            ) + 1,
            title=editor_version.title,
            description=editor_version.description,
            published_at=None,
            questions=_clone_questions(editor_version.questions),
        )
        db.add(editor_version)
        db.flush()

    next_order = max(
        (question.question_order for question in editor_version.questions),
        default=0,
    ) + 1
    question = _question_from_payload(payload, question_order=next_order)
    editor_version.questions.append(question)
    now = datetime.now(UTC).replace(tzinfo=None)

    try:
        quiz.revision += 1
        quiz.status = QuizStatus.DRAFT
        quiz.updated_at = now
        db.flush()
        response = QuestionUpdateResponse(
            quiz_id=quiz_id,
            quiz_revision=quiz.revision,
            question=QuestionResponse.model_validate(question),
        )
        db.commit()
        return response
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "question_create_failed",
            "Could not add the question.",
        ) from exc


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
    if quiz.status == QuizStatus.ARCHIVED:
        raise APIError(409, "quiz_not_editable", "An archived quiz cannot be edited.")

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
            Quiz.status != QuizStatus.ARCHIVED,
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

    _require_quiz_editor(db, account, quiz, lock_access=True)

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
            can_edit=True,
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


def publish_class_quiz(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_id: int,
    payload: QuizPublish,
) -> QuizResponse:
    """Publish the current draft using the same revision lock as editing.

    Collaborators may edit a draft, but only its owner controls publication.
    Publishing timestamps the current version, making that version immutable;
    a later edit creates a new draft version.
    """
    _require_active_class_member(db, account, class_id)
    quiz = _class_quiz(db, class_id, quiz_id)
    if quiz.author_id != account.account_id:
        raise APIError(
            403,
            "quiz_publish_denied",
            "Only the quiz owner can publish it.",
        )
    if quiz.status == QuizStatus.ARCHIVED:
        raise APIError(
            409,
            "quiz_not_publishable",
            "An archived quiz cannot be published.",
        )
    if payload.expected_revision != quiz.revision:
        raise APIError(
            409,
            "quiz_edit_conflict",
            "This quiz changed after you opened it. Reload before publishing.",
            details={"current_revision": quiz.revision},
        )

    draft = max(
        (version for version in quiz.versions if version.published_at is None),
        key=lambda version: version.version_number,
        default=None,
    )
    if draft is None:
        raise APIError(
            409,
            "quiz_not_publishable",
            "The quiz has no draft version to publish.",
        )

    now = datetime.now(UTC).replace(tzinfo=None)
    try:
        changed = db.execute(
            update(Quiz)
            .where(
                Quiz.quiz_id == quiz_id,
                Quiz.revision == payload.expected_revision,
                Quiz.status == QuizStatus.DRAFT,
            )
            .values(
                revision=Quiz.revision + 1,
                status=QuizStatus.PUBLISHED,
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
                "This quiz changed after you opened it. Reload before publishing.",
                details={"current_revision": current_revision},
            )

        _require_current_active_account(db, account, lock=True)
        draft.published_at = now
        db.flush()
        response = QuizResponse(
            quiz_id=quiz.quiz_id,
            author_id=quiz.author_id,
            class_id=quiz.class_id,
            revision=payload.expected_revision + 1,
            status=QuizStatus.PUBLISHED,
            visibility=quiz.visibility,
            created_at=quiz.created_at,
            updated_at=now,
            can_edit=True,
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
            "quiz_publish_failed",
            "Could not publish the quiz.",
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
    if (
        target is None
        or not target.is_active
        or _active_membership(db, class_id, target.account_id) is None
    ):
        # Do not reveal whether an email belongs to an account elsewhere.
        raise APIError(
            409,
            "not_class_member",
            "No active member of this class has that email address.",
        )
    if target.account_id == quiz.author_id:
        raise APIError(
            409,
            "quiz_owner_cannot_collaborate",
            "The quiz owner cannot also be a collaborator.",
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
    db.add(
        QuizCollaboratorEvent(
            quiz_id=quiz_id,
            account_id=target.account_id,
            action=CollaboratorEventType.SHARED,
            actor_id=account.account_id,
        )
    )
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
    # Use the same lock order as editor mutations: quiz, then access row.
    db.execute(
        select(Quiz.quiz_id)
        .where(Quiz.quiz_id == quiz_id)
        .with_for_update()
    )
    db.expire_all()
    _require_current_active_account(db, account, lock=True)
    _require_collaborator_owner(db, account, class_id, quiz_id)
    collaborator = db.scalar(
        select(QuizCollaborator)
        .where(
            QuizCollaborator.quiz_id == quiz_id,
            QuizCollaborator.account_id == target_account_id,
        )
        .with_for_update()
    )
    if collaborator is None or collaborator.revoked_at is not None:
        raise APIError(404, "quiz_collaborator_not_found", "Collaborator not found.")
    collaborator.revoked_at = datetime.now(UTC).replace(tzinfo=None)
    collaborator.revoked_by_id = account.account_id
    db.add(
        QuizCollaboratorEvent(
            quiz_id=quiz_id,
            account_id=target_account_id,
            action=CollaboratorEventType.REVOKED,
            actor_id=account.account_id,
        )
    )
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "quiz_collaborator_revoke_failed",
            "Could not revoke the quiz collaborator.",
        ) from exc
