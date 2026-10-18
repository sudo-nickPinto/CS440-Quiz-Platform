from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy.orm import Session

from fastapi import Response as HTTPResponse

from app.services.session_report import (
    export_session_report,
    get_session_report,
)

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.results import (
    FinalResults,
    ParticipantFinalResults,
    participant_final_view,
)
from app.schemas.session import (
    SessionJoinRequest,
    SessionJoinResponse,
    SessionParticipantResponse,
    SessionResponse,
)
from app.services.session_end import get_final_results
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
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> SessionJoinResponse:
    joined = join_session(db, account, payload.join_code)
    # Joining happens over REST, so tell the live host after the commit.
    background_tasks.add_task(
        request.app.state.live_hub.participant_joined,
        joined.session.session_id,
        joined.participant.session_participant_id,
        joined.participant.display_name,
    )
    return joined


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


@router.get(
    "/sessions/{session_id}/results",
    response_model=FinalResults | ParticipantFinalResults,
)
def get_final_results_route(
    session_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> FinalResults | ParticipantFinalResults:
    """Final standings after a session ends, e.g. when the results page reloads.

    The host and Admins get every row; a participant gets their own row plus
    the top 5, the same cut as the live session_ended event.
    """
    results, viewer_participant_id = get_final_results(db, account, session_id)
    if viewer_participant_id is None:
        return results
    return participant_final_view(results, viewer_participant_id)


@router.get("/sessions/{session_id}/report")
def session_report_route(
    session_id: int,
    response: HTTPResponse,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return get_session_report(db, account, session_id)


@router.get("/sessions/{session_id}/results/export.csv")
def session_results_export_route(
    session_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> HTTPResponse:
    content = export_session_report(db, account, session_id)

    return HTTPResponse(
        content="\ufeff" + content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="session-{session_id}-results.csv"'
            ),
            "Cache-Control": "no-store",
        },
    )
