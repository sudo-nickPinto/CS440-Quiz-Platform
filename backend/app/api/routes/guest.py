"""Guest join for the capstone live demo (temporary, demo branch only).

Joining needs no sign-in; quick host is for signed-in hosts. See app/guest.py.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.routes.sessions import _announce_join
from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.guest import (
    NICKNAME_MAX_LENGTH,
    check_join_code,
    join_as_guest,
    list_quick_host_quizzes,
    quick_host,
)
from app.schemas.session import (
    SessionJoinRequest,
    SessionJoinResponse,
    SessionResponse,
)

router = APIRouter(prefix="/guest", tags=["guest"])


class GuestCodeResponse(BaseModel):
    session_id: int
    quiz_title: str | None


class GuestJoinRequest(SessionJoinRequest):
    model_config = ConfigDict(extra="forbid")

    # Generous limit only stops huge bodies; clean_nickname enforces the real one.
    nickname: str = Field(max_length=NICKNAME_MAX_LENGTH * 4)


class GuestJoinResponse(SessionJoinResponse):
    guest_token: str


@router.post("/check-code", response_model=GuestCodeResponse)
def check_code_route(
    payload: SessionJoinRequest,
    db: Session = Depends(get_db),
) -> dict:
    return check_join_code(db, payload.join_code)


@router.post(
    "/join",
    response_model=GuestJoinResponse,
    status_code=status.HTTP_201_CREATED,
)
def guest_join_route(
    payload: GuestJoinRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> GuestJoinResponse:
    token, joined = join_as_guest(db, payload.join_code, payload.nickname)
    _announce_join(request, background_tasks, joined)
    return GuestJoinResponse(
        session=joined.session,
        participant=joined.participant,
        guest_token=token,
    )


class QuickHostQuiz(BaseModel):
    quiz_id: int
    title: str
    question_count: int
    class_name: str | None


@router.get("/quick-host/quizzes", response_model=list[QuickHostQuiz])
def quick_host_quizzes_route(
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[dict]:
    """Quizzes you wrote or collaborate on that have a published version."""
    return list_quick_host_quizzes(db, account)


@router.post(
    "/quick-host/quizzes/{quiz_id}",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def quick_host_route(
    quiz_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> SessionResponse:
    """Open a lobby for the quiz in your own Live demo class, no approval needed."""
    return quick_host(db, account, quiz_id)
