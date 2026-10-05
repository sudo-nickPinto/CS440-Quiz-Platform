from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_current_account
from app.database import get_db
from app.errors import APIError
from app.models import QuizStatus
from app.schemas.quiz import (
    QuestionOrderUpdate,
    QuestionResponse,
    QuestionWrite,
    QuizCreate,
    QuizListItem,
    QuizResponse,
    QuizUpdate,
)
from app.services.quizzes import (
    archive_quiz,
    create_question,
    create_quiz,
    delete_question,
    get_quiz,
    list_quizzes,
    reorder_questions,
    update_quiz,
    update_question,
)

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


def active_account(
    account: CurrentAccount = Depends(get_current_account),
) -> CurrentAccount:
    if not account.is_active:
        raise APIError(403, "inactive_account", "This account is inactive.")
    return account


@router.post("", response_model=QuizResponse, status_code=status.HTTP_201_CREATED)
def create_quiz_route(
    payload: QuizCreate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(active_account),
) -> QuizResponse:
    return create_quiz(db, account, payload)


@router.get("", response_model=list[QuizListItem])
def list_quizzes_route(
    status_filter: QuizStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(active_account),
) -> list[QuizListItem]:
    return list_quizzes(db, account, status_filter)


@router.get("/{quiz_id}", response_model=QuizResponse)
def get_quiz_route(
    quiz_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(active_account),
) -> QuizResponse:
    return get_quiz(db, account, quiz_id)


@router.patch("/{quiz_id}", response_model=QuizResponse)
def update_quiz_route(
    quiz_id: int,
    payload: QuizUpdate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(active_account),
) -> QuizResponse:
    return update_quiz(db, account, quiz_id, payload)


@router.patch("/{quiz_id}/archive", response_model=QuizResponse)
def archive_quiz_route(
    quiz_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(active_account),
) -> QuizResponse:
    return archive_quiz(db, account, quiz_id)


@router.post(
    "/{quiz_id}/questions",
    response_model=QuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_question_route(
    quiz_id: int,
    payload: QuestionWrite,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(active_account),
) -> QuestionResponse:
    return create_question(db, account, quiz_id, payload)


@router.put(
    "/{quiz_id}/questions/{question_id}", response_model=QuestionResponse
)
def update_question_route(
    quiz_id: int,
    question_id: int,
    payload: QuestionWrite,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(active_account),
) -> QuestionResponse:
    return update_question(db, account, quiz_id, question_id, payload)


@router.delete(
    "/{quiz_id}/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_question_route(
    quiz_id: int,
    question_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(active_account),
) -> None:
    delete_question(db, account, quiz_id, question_id)


@router.patch(
    "/{quiz_id}/questions/order", response_model=list[QuestionResponse]
)
def reorder_questions_route(
    quiz_id: int,
    payload: QuestionOrderUpdate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(active_account),
) -> list[QuestionResponse]:
    return reorder_questions(db, account, quiz_id, payload)
