from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    AnswerChoice,
    Question,
    QuestionType,
    Quiz,
    QuizStatus,
    QuizVersion,
)
from app.schemas.quiz import (
    QuestionOrderUpdate,
    QuestionResponse,
    QuestionWrite,
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


def _current_version(quiz: Quiz) -> QuizVersion:
    if not quiz.versions:
        raise APIError(500, "invalid_quiz", "The quiz has no versions.")
    return max(quiz.versions, key=lambda version: version.version_number)


def _to_response(quiz: Quiz) -> QuizResponse:
    current_version = _current_version(quiz)
    return QuizResponse(
        quiz_id=quiz.quiz_id,
        author_id=quiz.author_id,
        status=quiz.status,
        visibility=quiz.visibility,
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
        current_version=QuizVersionResponse.model_validate(current_version),
    )


def _to_list_item(quiz: Quiz) -> QuizListItem:
    current_version = _current_version(quiz)
    return QuizListItem(
        quiz_id=quiz.quiz_id,
        author_id=quiz.author_id,
        status=quiz.status,
        visibility=quiz.visibility,
        title=current_version.title,
        version_number=current_version.version_number,
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
    )


def _load_quiz(db: Session, quiz_id: int) -> Quiz:
    quiz = db.scalar(_quiz_query(quiz_id))
    if quiz is None:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    return quiz


def _editable_version(
    db: Session, account: CurrentAccount, quiz_id: int
) -> tuple[Quiz, QuizVersion]:
    quiz = _load_quiz(db, quiz_id)
    if quiz.author_id != account.account_id:
        raise APIError(403, "quiz_access_denied", "You cannot edit this quiz.")
    if quiz.status == QuizStatus.ARCHIVED:
        raise APIError(409, "quiz_archived", "Archived quizzes cannot be edited.")

    version = _current_version(quiz)
    if version.published_at is not None:
        raise APIError(
            409,
            "published_version_immutable",
            "Published quiz versions cannot be edited.",
        )
    return quiz, version


def publication_errors(version: QuizVersion) -> list[str]:
    """Return every reason a draft cannot be published."""
    errors: list[str] = []
    if not version.title.strip():
        errors.append("The quiz title must not be blank.")
    if not version.questions:
        errors.append("The quiz must contain at least one question.")

    expected_question_order = list(range(1, len(version.questions) + 1))
    actual_question_order = sorted(
        question.question_order for question in version.questions
    )
    if actual_question_order != expected_question_order:
        errors.append("Question positions must be consecutive and start at 1.")

    for question in version.questions:
        label = f"Question {question.question_order}"
        if question.question_type != QuestionType.MULTIPLE_CHOICE:
            errors.append(f"{label} must be multiple choice.")
        if not question.question_text.strip():
            errors.append(f"{label} text must not be blank.")
        if question.time_limit_seconds <= 0:
            errors.append(f"{label} must have a positive time limit.")
        if question.base_points <= 0:
            errors.append(f"{label} must have positive base points.")
        if len(question.choices) < 2:
            errors.append(f"{label} must have at least two choices.")
        if not any(choice.is_correct for choice in question.choices):
            errors.append(f"{label} must have at least one correct choice.")
        if any(not choice.choice_text.strip() for choice in question.choices):
            errors.append(f"{label} choices must not be blank.")

        expected_choice_order = list(range(1, len(question.choices) + 1))
        actual_choice_order = sorted(choice.choice_order for choice in question.choices)
        if actual_choice_order != expected_choice_order:
            errors.append(f"{label} choice positions must be consecutive and start at 1.")
    return errors


def _question_in_version(version: QuizVersion, question_id: int) -> Question:
    question = next(
        (item for item in version.questions if item.question_id == question_id), None
    )
    if question is None:
        raise APIError(404, "question_not_found", "Question not found in this quiz.")
    return question


def _new_choices(payload: QuestionWrite) -> list[AnswerChoice]:
    return [
        AnswerChoice(
            choice_order=position,
            choice_text=choice.choice_text,
            is_correct=choice.is_correct,
        )
        for position, choice in enumerate(payload.choices, start=1)
    ]


def _apply_question_order(db: Session, questions: list[Question]) -> None:
    temporary_start = max(
        (question.question_order for question in questions), default=0
    ) + 1
    if temporary_start + len(questions) - 1 > 65_535:
        raise APIError(409, "question_order_exhausted", "Questions cannot be reordered.")

    for offset, question in enumerate(questions):
        question.question_order = temporary_start + offset
    db.flush()
    for position, question in enumerate(questions, start=1):
        question.question_order = position


def create_quiz(
    db: Session, account: CurrentAccount, payload: QuizCreate
) -> QuizResponse:
    quiz = Quiz(
        author_id=account.account_id,
        visibility=payload.visibility,
        versions=[
            QuizVersion(
                version_number=1,
                title=payload.title,
                description=payload.description,
            )
        ],
    )
    db.add(quiz)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, "quiz_creation_failed", "Could not create the quiz.") from exc

    return _to_response(_load_quiz(db, quiz.quiz_id))


def get_quiz(db: Session, account: CurrentAccount, quiz_id: int) -> QuizResponse:
    quiz = _load_quiz(db, quiz_id)
    if quiz.author_id != account.account_id:
        raise APIError(403, "quiz_access_denied", "You cannot access this quiz.")
    return _to_response(quiz)


def list_quizzes(
    db: Session,
    account: CurrentAccount,
    status_filter: QuizStatus | None,
) -> list[QuizListItem]:
    statement = (
        select(Quiz)
        .where(Quiz.author_id == account.account_id)
        .options(selectinload(Quiz.versions))
        .order_by(Quiz.updated_at.desc(), Quiz.quiz_id.desc())
    )
    if status_filter is None:
        statement = statement.where(Quiz.status != QuizStatus.ARCHIVED)
    else:
        statement = statement.where(Quiz.status == status_filter)
    return [_to_list_item(quiz) for quiz in db.scalars(statement).all()]


def archive_quiz(
    db: Session, account: CurrentAccount, quiz_id: int
) -> QuizResponse:
    quiz = _load_quiz(db, quiz_id)
    if quiz.author_id != account.account_id:
        raise APIError(403, "quiz_access_denied", "You cannot archive this quiz.")
    if quiz.status == QuizStatus.ARCHIVED:
        return _to_response(quiz)

    quiz.status = QuizStatus.ARCHIVED
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, "quiz_archive_failed", "Could not archive the quiz.") from exc

    db.expire_all()
    return _to_response(_load_quiz(db, quiz_id))


def update_quiz(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
    payload: QuizUpdate,
) -> QuizResponse:
    quiz, current_version = _editable_version(db, account, quiz_id)

    supplied_fields = payload.model_fields_set
    if "title" in supplied_fields:
        current_version.title = payload.title
    if "description" in supplied_fields:
        current_version.description = payload.description
    if "visibility" in supplied_fields:
        quiz.visibility = payload.visibility

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, "quiz_update_failed", "Could not update the quiz.") from exc

    db.expire_all()
    return _to_response(_load_quiz(db, quiz_id))


def create_question(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
    payload: QuestionWrite,
) -> QuestionResponse:
    _, version = _editable_version(db, account, quiz_id)
    next_order = max(
        (question.question_order for question in version.questions), default=0
    ) + 1
    question = Question(
        question_order=next_order,
        question_text=payload.question_text,
        explanation=payload.explanation,
        time_limit_seconds=payload.time_limit_seconds,
        base_points=payload.base_points,
        choices=_new_choices(payload),
    )
    version.questions.append(question)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500, "question_creation_failed", "Could not create the question."
        ) from exc

    question_id = question.question_id
    db.expire_all()
    refreshed_version = _current_version(_load_quiz(db, quiz_id))
    return QuestionResponse.model_validate(
        _question_in_version(refreshed_version, question_id)
    )


def update_question(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
    question_id: int,
    payload: QuestionWrite,
) -> QuestionResponse:
    _, version = _editable_version(db, account, quiz_id)
    question = _question_in_version(version, question_id)
    question.question_text = payload.question_text
    question.explanation = payload.explanation
    question.time_limit_seconds = payload.time_limit_seconds
    question.base_points = payload.base_points
    question.choices = _new_choices(payload)

    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500, "question_update_failed", "Could not update the question."
        ) from exc

    db.expire_all()
    refreshed_version = _current_version(_load_quiz(db, quiz_id))
    return QuestionResponse.model_validate(
        _question_in_version(refreshed_version, question_id)
    )


def delete_question(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
    question_id: int,
) -> None:
    _, version = _editable_version(db, account, quiz_id)
    question = _question_in_version(version, question_id)
    version.questions.remove(question)

    try:
        db.flush()
        remaining = sorted(version.questions, key=lambda item: item.question_order)
        _apply_question_order(db, remaining)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500, "question_deletion_failed", "Could not delete the question."
        ) from exc


def reorder_questions(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
    payload: QuestionOrderUpdate,
) -> list[QuestionResponse]:
    _, version = _editable_version(db, account, quiz_id)
    questions_by_id = {
        question.question_id: question for question in version.questions
    }
    if set(payload.question_ids) != set(questions_by_id):
        raise APIError(
            422,
            "invalid_question_order",
            "Question order must include every question exactly once.",
        )

    try:
        ordered_questions = [
            questions_by_id[question_id] for question_id in payload.question_ids
        ]
        _apply_question_order(db, ordered_questions)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500, "question_reorder_failed", "Could not reorder the questions."
        ) from exc

    db.expire_all()
    refreshed_version = _current_version(_load_quiz(db, quiz_id))
    return [
        QuestionResponse.model_validate(question)
        for question in refreshed_version.questions
    ]


def publish_quiz(
    db: Session, account: CurrentAccount, quiz_id: int
) -> QuizResponse:
    quiz = _load_quiz(db, quiz_id)
    if quiz.author_id != account.account_id:
        raise APIError(403, "quiz_access_denied", "You cannot publish this quiz.")
    if quiz.status == QuizStatus.ARCHIVED:
        raise APIError(409, "quiz_archived", "Archived quizzes cannot be published.")

    version = _current_version(quiz)
    if version.published_at is not None:
        raise APIError(409, "quiz_already_published", "This version is already published.")

    errors = publication_errors(version)
    if errors:
        raise APIError(
            422,
            "quiz_not_publishable",
            "The quiz is not ready to publish.",
            errors,
        )

    version.published_at = datetime.now(UTC).replace(tzinfo=None)
    quiz.status = QuizStatus.PUBLISHED
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, "quiz_publish_failed", "Could not publish the quiz.") from exc

    db.expire_all()
    return _to_response(_load_quiz(db, quiz_id))
