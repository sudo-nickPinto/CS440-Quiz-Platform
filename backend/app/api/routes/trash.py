from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.trash import TrashResponse, TrashSelection
from app.services.trash import (
    list_trash,
    purge_selected,
    restore_class,
    restore_quiz,
    restore_selected,
    restore_session,
    trash_class,
    trash_quiz,
    trash_session,
)

router = APIRouter(tags=["trash"])

NO_CONTENT = status.HTTP_204_NO_CONTENT


@router.get("/trash", response_model=TrashResponse)
def list_trash_route(
    response: Response,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> TrashResponse:
    response.headers["Cache-Control"] = "no-store"
    return list_trash(db, account)


@router.post("/trash/restore", status_code=NO_CONTENT)
def restore_selected_route(
    payload: TrashSelection,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    restore_selected(db, account, payload)
    return Response(status_code=NO_CONTENT)


@router.post("/trash/purge", status_code=NO_CONTENT)
def purge_selected_route(
    payload: TrashSelection,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    purge_selected(db, account, payload)
    return Response(status_code=NO_CONTENT)


@router.post("/classes/{class_id}/trash", status_code=NO_CONTENT)
def trash_class_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    trash_class(db, account, class_id)
    return Response(status_code=NO_CONTENT)


@router.post("/classes/{class_id}/restore", status_code=NO_CONTENT)
def restore_class_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    restore_class(db, account, class_id)
    return Response(status_code=NO_CONTENT)


@router.post("/quizzes/{quiz_id}/trash", status_code=NO_CONTENT)
async def trash_quiz_route(
    quiz_id: int,
    request: Request,
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    hub = request.app.state.quiz_edit_hub
    await hub.run_db(trash_quiz, account, quiz_id)
    # Like archiving: every open editor is re-authorized, and the quiz now
    # looks missing, so their sockets close.
    await hub.broadcast(quiz_id, {"type": "quiz_trashed", "quiz_id": quiz_id})
    return Response(status_code=NO_CONTENT)


@router.post("/quizzes/{quiz_id}/restore", status_code=NO_CONTENT)
def restore_quiz_route(
    quiz_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    restore_quiz(db, account, quiz_id)
    return Response(status_code=NO_CONTENT)


@router.post("/sessions/{session_id}/trash", status_code=NO_CONTENT)
def trash_session_route(
    session_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    trash_session(db, account, session_id)
    return Response(status_code=NO_CONTENT)


@router.post("/sessions/{session_id}/restore", status_code=NO_CONTENT)
def restore_session_route(
    session_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    restore_session(db, account, session_id)
    return Response(status_code=NO_CONTENT)
