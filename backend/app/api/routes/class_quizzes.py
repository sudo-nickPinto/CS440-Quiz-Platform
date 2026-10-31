from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.quiz import (
    QuizCollaboratorCreate,
    QuizCollaboratorResponse,
    QuizCreate,
    QuizResponse,
    QuizUpdate,
)
from app.services.quizzes import (
    add_quiz_collaborator,
    create_class_quiz,
    get_class_quiz,
    list_quiz_collaborators,
    revoke_quiz_collaborator,
    update_class_quiz,
)

router = APIRouter(prefix="/classes/{class_id}/quizzes", tags=["class quizzes"])


@router.post("", response_model=QuizResponse, status_code=status.HTTP_201_CREATED)
def create_class_quiz_route(
    class_id: int,
    payload: QuizCreate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> QuizResponse:
    return create_class_quiz(db, account, class_id, payload)


@router.get("/{quiz_id}", response_model=QuizResponse)
def get_class_quiz_route(
    class_id: int,
    quiz_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> QuizResponse:
    return get_class_quiz(db, account, class_id, quiz_id)


@router.put("/{quiz_id}", response_model=QuizResponse)
def update_class_quiz_route(
    class_id: int,
    quiz_id: int,
    payload: QuizUpdate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> QuizResponse:
    return update_class_quiz(db, account, class_id, quiz_id, payload)


@router.get(
    "/{quiz_id}/collaborators",
    response_model=list[QuizCollaboratorResponse],
)
def list_quiz_collaborators_route(
    class_id: int,
    quiz_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[QuizCollaboratorResponse]:
    return list_quiz_collaborators(db, account, class_id, quiz_id)


@router.post(
    "/{quiz_id}/collaborators",
    response_model=QuizCollaboratorResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_quiz_collaborator_route(
    class_id: int,
    quiz_id: int,
    payload: QuizCollaboratorCreate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> QuizCollaboratorResponse:
    return add_quiz_collaborator(db, account, class_id, quiz_id, payload)


@router.delete(
    "/{quiz_id}/collaborators/{account_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_quiz_collaborator_route(
    class_id: int,
    quiz_id: int,
    account_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> None:
    revoke_quiz_collaborator(db, account, class_id, quiz_id, account_id)
