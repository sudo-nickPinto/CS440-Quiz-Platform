from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.session import (
    SessionJoinRequest,
    SessionJoinResponse,
    SessionParticipantResponse,
    SessionResponse,
)
from app.services.sessions import (
    create_session,
    get_session,
    join_session,
    list_session_participants,
)

router = APIRouter(tags=["sessions"])


@router.post(
    "/quizzes/{quiz_id}/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session_route(
    quiz_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> SessionResponse:
    return create_session(db, account, quiz_id)


@router.post(
    "/sessions/join",
    response_model=SessionJoinResponse,
    status_code=status.HTTP_201_CREATED,
)
def join_session_route(
    payload: SessionJoinRequest,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> SessionJoinResponse:
    return join_session(db, account, payload.join_code)


@router.get("/sessions/{session_id}", response_model=SessionResponse)
def get_session_route(
    session_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> SessionResponse:
    return get_session(db, account, session_id)


@router.get(
    "/sessions/{session_id}/participants",
    response_model=list[SessionParticipantResponse],
)
def list_session_participants_route(
    session_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[SessionParticipantResponse]:
    return list_session_participants(db, account, session_id)
