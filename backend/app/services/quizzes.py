from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.quiz import (
    AnswerChoice,
    Question,
    Quiz,
    QuizStatus,
    QuizVersion,
    QuizVisibility,
)
from app.schemas.quiz import (
    QuizCreate,
    QuizListItem,
    QuizResponse,
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


def _mvp_version(quiz: Quiz) -> QuizVersion:
    if (
        len(quiz.versions) != 1
        or quiz.versions[0].version_number != 1
        or quiz.versions[0].published_at is None
    ):
        raise APIError(500, "invalid_quiz", "The quiz does not have one MVP version.")
    return quiz.versions[0]


def _to_response(quiz: Quiz) -> QuizResponse:
    return QuizResponse(
        quiz_id=quiz.quiz_id,
        author_id=quiz.author_id,
        status=quiz.status,
        visibility=quiz.visibility,
        created_at=quiz.created_at,
        updated_at=quiz.updated_at,
        version=QuizVersionResponse.model_validate(_mvp_version(quiz)),
    )


def _to_list_item(quiz: Quiz) -> QuizListItem:
    version = _mvp_version(quiz)
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
) -> QuizResponse:
    """Atomically save a complete, public, immutable MVP quiz."""
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
        statement = statement.where(Quiz.status == QuizStatus.PUBLISHED)
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
        raise APIError(500, "quiz_archive_failed", "Could not archive the quiz.") from exc

    db.expire_all()
    return _to_response(_load_quiz(db, quiz_id))
