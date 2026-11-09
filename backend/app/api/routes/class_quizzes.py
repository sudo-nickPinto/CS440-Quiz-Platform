from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.quiz import (
    ClassQuizListPage,
    QuizCollaboratorCreate,
    QuizCollaboratorResponse,
    QuizCreate,
    QuizPublish,
    QuestionCreate,
    QuestionUpdate,
    QuestionUpdateResponse,
    QuizResponse,
    QuizUpdate,
)
from app.services.quizzes import (
    add_class_quiz_question,
    add_quiz_collaborator,
    create_quiz,
    get_class_quiz,
    list_class_quizzes,
    list_quiz_collaborators,
    publish_class_quiz,
    revoke_quiz_collaborator,
    update_class_quiz,
    update_class_quiz_question,
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


@router.put("/{quiz_id}", response_model=QuizResponse)
async def update_class_quiz_route(
    class_id: int,
    quiz_id: int,
    payload: QuizUpdate,
    request: Request,
    account: CurrentAccount = Depends(get_active_account),
) -> QuizResponse:
    hub = request.app.state.quiz_edit_hub
    result = await hub.run_db(
        update_class_quiz, account, class_id, quiz_id, payload
    )
    await hub.broadcast(
        quiz_id,
        {
            "type": "quiz_structure_updated",
            "quiz_id": quiz_id,
            "quiz_revision": result.revision,
            "editor_account_id": account.account_id,
        },
    )
    return result


@router.patch(
    "/{quiz_id}/questions/{question_id}",
    response_model=QuestionUpdateResponse,
)
async def update_class_quiz_question_route(
    class_id: int,
    quiz_id: int,
    question_id: int,
    payload: QuestionUpdate,
    request: Request,
    account: CurrentAccount = Depends(get_active_account),
) -> QuestionUpdateResponse:
    hub = request.app.state.quiz_edit_hub
    result = await hub.run_db(
        update_class_quiz_question,
        account,
        class_id,
        quiz_id,
        question_id,
        payload,
    )
    await hub.broadcast(
        quiz_id,
        {
            "type": "question_updated",
            "quiz_id": quiz_id,
            "quiz_revision": result.quiz_revision,
            "editor_account_id": account.account_id,
            "question": result.question.model_dump(),
        },
    )
    return result


@router.post(
    "/{quiz_id}/questions",
    response_model=QuestionUpdateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_class_quiz_question_route(
    class_id: int,
    quiz_id: int,
    payload: QuestionCreate,
    request: Request,
    account: CurrentAccount = Depends(get_active_account),
) -> QuestionUpdateResponse:
    hub = request.app.state.quiz_edit_hub
    result = await hub.run_db(
        add_class_quiz_question, account, class_id, quiz_id, payload
    )
    await hub.broadcast(
        quiz_id,
        {
            "type": "question_added",
            "quiz_id": quiz_id,
            "quiz_revision": result.quiz_revision,
            "editor_account_id": account.account_id,
            "question": result.question.model_dump(),
        },
    )
    return result


@router.post("/{quiz_id}/publish", response_model=QuizResponse)
async def publish_class_quiz_route(
    class_id: int,
    quiz_id: int,
    payload: QuizPublish,
    request: Request,
    account: CurrentAccount = Depends(get_active_account),
) -> QuizResponse:
    hub = request.app.state.quiz_edit_hub
    result = await hub.run_db(
        publish_class_quiz, account, class_id, quiz_id, payload
    )
    await hub.broadcast(
        quiz_id,
        {
            "type": "quiz_published",
            "quiz_id": quiz_id,
            "quiz_revision": result.revision,
            "editor_account_id": account.account_id,
        },
    )
    return result


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
async def revoke_quiz_collaborator_route(
    class_id: int,
    quiz_id: int,
    account_id: int,
    request: Request,
    account: CurrentAccount = Depends(get_active_account),
) -> None:
    hub = request.app.state.quiz_edit_hub
    await hub.run_db(
        revoke_quiz_collaborator,
        account,
        class_id,
        quiz_id,
        account_id,
    )
    await hub.close_account(quiz_id, account_id)
