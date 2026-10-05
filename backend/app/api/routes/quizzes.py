from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_current_account
from app.database import get_db
from app.errors import APIError
from app.models import QuizStatus
from app.schemas.quiz import QuizCreate, QuizListItem, QuizResponse
from app.services.quizzes import archive_quiz, create_quiz, get_quiz, list_quizzes

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


@router.patch("/{quiz_id}/archive", response_model=QuizResponse)
def archive_quiz_route(
    quiz_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(active_account),
) -> QuizResponse:
    return archive_quiz(db, account, quiz_id)
