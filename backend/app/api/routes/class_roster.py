from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.emails import EmailService
from app.schemas.class_roster import (
    JoinRequestDecisionResponse,
    JoinRequestResponse,
    RosterEntryResponse,
    RosterImportResponse,
    StudentSuggestion,
)
from app.services.class_roster import (
    MAX_ROSTER_BYTES,
    decide_join_requests,
    import_roster,
    list_join_requests,
    list_roster,
    suggest_students,
)
from app.errors import APIError

router = APIRouter(prefix="/classes/{class_id}", tags=["class roster"])


def _email(request: Request) -> EmailService:
    return request.app.state.email


def _import_in_worker(
    request: Request,
    account: CurrentAccount,
    class_id: int,
    content: bytes,
    email: EmailService,
    dry_run: bool,
):
    """Runs in a worker thread with its own database session.

    SQLAlchemy sessions aren't thread-safe, so the session is created, used
    and closed here, in the worker, rather than borrowing the request's.
    """
    with request.app.state.database.session_factory() as db:
        return import_roster(db, account, class_id, content, email, dry_run=dry_run)


@router.post("/roster/import", response_model=RosterImportResponse)
async def import_roster_route(
    class_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    dry_run: bool = Query(default=False),
    account: CurrentAccount = Depends(get_active_account),
) -> RosterImportResponse:
    """The request body is the roster file itself (CSV or .xlsx), not a form.

    The body has to be read asynchronously, so this route is async; the
    blocking database work then runs in a worker thread (see above).
    """
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_ROSTER_BYTES:
            raise APIError(
                413, "roster_file_too_large", "The roster file is larger than 2 MB."
            )
    email = _email(request)
    response, messages = await run_in_threadpool(
        _import_in_worker,
        request,
        account,
        class_id,
        bytes(content),
        email,
        dry_run,
    )
    if messages:
        background_tasks.add_task(email.send_all, messages)
    return response


@router.get("/roster", response_model=list[RosterEntryResponse])
def list_roster_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[RosterEntryResponse]:
    return list_roster(db, account, class_id)


@router.get("/join-requests", response_model=list[JoinRequestResponse])
def list_join_requests_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[JoinRequestResponse]:
    return list_join_requests(db, account, class_id)


@router.post("/join-requests/approve-all", response_model=JoinRequestDecisionResponse)
def approve_all_join_requests_route(
    class_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> JoinRequestDecisionResponse:
    email = _email(request)
    response, messages = decide_join_requests(
        db, account, class_id, email, approve=True
    )
    background_tasks.add_task(email.send_all, messages)
    return response


@router.post(
    "/join-requests/{account_id}/approve", response_model=JoinRequestDecisionResponse
)
def approve_join_request_route(
    class_id: int,
    account_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> JoinRequestDecisionResponse:
    email = _email(request)
    response, messages = decide_join_requests(
        db, account, class_id, email, approve=True, account_id=account_id
    )
    background_tasks.add_task(email.send_all, messages)
    return response


@router.post(
    "/join-requests/{account_id}/reject", response_model=JoinRequestDecisionResponse
)
def reject_join_request_route(
    class_id: int,
    account_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> JoinRequestDecisionResponse:
    email = _email(request)
    response, messages = decide_join_requests(
        db, account, class_id, email, approve=False, account_id=account_id
    )
    background_tasks.add_task(email.send_all, messages)
    return response


@router.get("/student-suggestions", response_model=list[StudentSuggestion])
def student_suggestions_route(
    class_id: int,
    q: str = Query(default="", max_length=100),
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[StudentSuggestion]:
    return suggest_students(db, account, class_id, q)
