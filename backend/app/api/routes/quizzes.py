from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.quiz import QuizListItem, QuizResponse, QuizUpdate
from app.services.quizzes import archive_quiz, get_quiz, list_quizzes, update_quiz

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


# Quizzes are created inside a class: POST /classes/{class_id}/quizzes.


@router.get("", response_model=list[QuizListItem])
def list_quizzes_route(
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[QuizListItem]:
    return list_quizzes(db, account)


@router.get("/{quiz_id}", response_model=QuizResponse)
def get_quiz_route(
    quiz_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> QuizResponse:
    return get_quiz(db, account, quiz_id)


@router.put("/{quiz_id}", response_model=QuizResponse)
def update_quiz_route(
    quiz_id: int,
    payload: QuizUpdate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> QuizResponse:
    return update_quiz(db, account, quiz_id, payload)


@router.patch("/{quiz_id}/archive", response_model=QuizResponse)
async def archive_quiz_route(
    quiz_id: int,
    request: Request,
    account: CurrentAccount = Depends(get_active_account),
) -> QuizResponse:
    hub = request.app.state.quiz_edit_hub
    result = await hub.run_db(archive_quiz, account, quiz_id)
    # Reauthorization closes every editor socket now that the quiz is no
    # longer editable, even if no later question event occurs.
    await hub.broadcast(
        quiz_id,
        {
            "type": "quiz_archived",
            "quiz_id": quiz_id,
            "quiz_revision": result.revision,
            "editor_account_id": account.account_id,
        },
    )
    return result
