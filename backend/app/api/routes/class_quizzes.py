from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.quiz import ClassQuizListPage, QuizCreate, QuizResponse
from app.services.quizzes import create_quiz, get_class_quiz, list_class_quizzes

router = APIRouter(prefix="/classes/{class_id}/quizzes", tags=["class quizzes"])
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


@router.post("", response_model=QuizResponse, status_code=status.HTTP_201_CREATED)
def create_class_quiz_route(
    class_id: int,
    payload: QuizCreate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> QuizResponse:
    return create_quiz(db, account, class_id, payload)


@router.get("", response_model=ClassQuizListPage)
def list_class_quizzes_route(
    class_id: int,
    page: Page = 1,
    page_size: PageSize = 25,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassQuizListPage:
    return list_class_quizzes(db, account, class_id, page=page, page_size=page_size)


@router.get("/{quiz_id}", response_model=QuizResponse)
def get_class_quiz_route(
    class_id: int,
    quiz_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> QuizResponse:
    return get_class_quiz(db, account, class_id, quiz_id)
