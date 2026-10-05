from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import Question, Quiz, QuizStatus, QuizVersion
from app.schemas.quiz import (
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
    quiz = _load_quiz(db, quiz_id)
    if quiz.author_id != account.account_id:
        raise APIError(403, "quiz_access_denied", "You cannot edit this quiz.")
    if quiz.status == QuizStatus.ARCHIVED:
        raise APIError(409, "quiz_archived", "Archived quizzes cannot be edited.")

    current_version = _current_version(quiz)
    if current_version.published_at is not None:
        raise APIError(
            409,
            "published_version_immutable",
            "Published quiz versions cannot be edited.",
        )

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
