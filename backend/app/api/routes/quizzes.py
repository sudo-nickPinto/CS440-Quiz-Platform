from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_current_account
from app.database import get_db
from app.errors import APIError
from app.schemas.quiz import QuizCreate, QuizResponse
from app.services.quizzes import create_quiz, get_quiz

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


@router.get("/{quiz_id}", response_model=QuizResponse)
def get_quiz_route(
    quiz_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(active_account),
) -> QuizResponse:
    return get_quiz(db, account, quiz_id)
