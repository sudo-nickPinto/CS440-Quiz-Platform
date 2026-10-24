from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from typing import Literal

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.services.session_history import (
    list_quiz_hosting_history,
    list_taken_sessions,
)

router = APIRouter(tags=["session history"])


@router.get("/me/sessions/taken")
def taken_sessions_route(
    response: Response,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    q: str = Query(default="", max_length=200),
    sort: Literal["recent", "az", "score"] = "recent",
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> dict:
    response.headers["Cache-Control"] = "no-store"

    return list_taken_sessions(
        db,
        account,
        limit=limit,
        offset=offset,
        q=q,
        sort=sort,
    )


@router.get("/quizzes/{quiz_id}/history")
def quiz_hosting_history_route(
    quiz_id: int,
    response: Response,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> dict:
    response.headers["Cache-Control"] = "no-store"

    return list_quiz_hosting_history(
        db,
        account,
        quiz_id,
        limit=limit,
        offset=offset,
    )
