from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.pagination import SortOrder
from app.schemas.quiz import (
    ClassQuizListPage,
    ClassQuizSort,
    QuizCollaboratorCreate,
    QuizCollaboratorResponse,
    QuizCreate,
    QuizPublish,
    QuizResponse,
    QuizUpdate,
)
from app.services.quizzes import (
    add_quiz_collaborator,
    create_quiz,
    get_class_quiz,
    list_class_quizzes,
    list_quiz_collaborators,
    publish_class_quiz,
    revoke_quiz_collaborator,
    update_class_quiz,
)

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
    sort: ClassQuizSort = ClassQuizSort.CREATED_AT,
    order: SortOrder = SortOrder.DESC,
    mine: bool = False,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassQuizListPage:
    return list_class_quizzes(
        db,
        account,
        class_id,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        mine=mine,
    )


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


@router.post("/{quiz_id}/publish", response_model=QuizResponse)
def publish_class_quiz_route(
    class_id: int,
    quiz_id: int,
    payload: QuizPublish,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> QuizResponse:
    return publish_class_quiz(db, account, class_id, quiz_id, payload)


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
