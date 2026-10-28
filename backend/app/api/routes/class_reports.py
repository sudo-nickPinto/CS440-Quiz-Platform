from fastapi import APIRouter, Depends
from fastapi import Response as HTTPResponse
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.services.class_reports import (
    get_class_quiz_results,
    get_class_session_results,
    get_class_student_results,
)

router = APIRouter(prefix="/classes/{class_id}", tags=["class reports"])


@router.get("/sessions/{session_id}/results")
def class_session_results_route(
    class_id: int,
    session_id: int,
    response: HTTPResponse,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return get_class_session_results(db, account, class_id, session_id)


@router.get("/quizzes/{quiz_id}/results")
def class_quiz_results_route(
    class_id: int,
    quiz_id: int,
    response: HTTPResponse,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return get_class_quiz_results(db, account, class_id, quiz_id)


@router.get("/students/{account_id}/results")
def class_student_results_route(
    class_id: int,
    account_id: int,
    response: HTTPResponse,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return get_class_student_results(db, account, class_id, account_id)
