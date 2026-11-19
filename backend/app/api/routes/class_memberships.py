from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.services.class_roster import added_email, roster_invitation_email
from app.schemas.class_membership import (
    ClassInviteCreate,
    ClassMemberResponse,
    ClassMemberUpdate,
)
from app.services.class_memberships import (
    accept_class_invite,
    add_class_student,
    cancel_class_invite,
    create_class_invite,
    decline_class_invite,
    list_class_members,
    remove_class_member,
    list_class_invites,
    update_class_member,
)

router = APIRouter(prefix="/classes/{class_id}", tags=["class members"])


@router.get("/members", response_model=list[ClassMemberResponse])
def list_class_members_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[ClassMemberResponse]:
    return list_class_members(db, account, class_id)


@router.post(
    "/students", response_model=ClassMemberResponse, status_code=status.HTTP_201_CREATED
)
def add_class_student_route(
    class_id: int,
    payload: ClassInviteCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassMemberResponse:
    """+ Add student: the account is a student right away and gets an email."""
    added = add_class_student(db, account, class_id, payload)
    email = request.app.state.email
    background_tasks.add_task(
        email.send_all, [added_email(db, email, class_id, added.email)]
    )
    return added


@router.get("/invites", response_model=list[ClassMemberResponse])
def list_class_invites_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[ClassMemberResponse]:
    return list_class_invites(db, account, class_id)


@router.post(
    "/invites", response_model=ClassMemberResponse, status_code=status.HTTP_201_CREATED
)
def create_class_invite_route(
    class_id: int,
    payload: ClassInviteCreate,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassMemberResponse:
    invited = create_class_invite(db, account, class_id, payload)
    email = request.app.state.email
    background_tasks.add_task(
        email.send_all, [roster_invitation_email(db, email, class_id, invited.email)]
    )
    return invited


@router.delete("/invites/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_class_invite_route(
    class_id: int,
    account_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    cancel_class_invite(db, account, class_id, account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/invite/accept", response_model=ClassMemberResponse)
def accept_class_invite_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassMemberResponse:
    return accept_class_invite(db, account, class_id)


@router.post("/invite/decline", status_code=status.HTTP_204_NO_CONTENT)
def decline_class_invite_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    decline_class_invite(db, account, class_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/members/{account_id}", response_model=ClassMemberResponse)
def update_class_member_route(
    class_id: int,
    account_id: int,
    payload: ClassMemberUpdate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassMemberResponse:
    return update_class_member(db, account, class_id, account_id, payload)


@router.delete("/members/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_class_member_route(
    class_id: int,
    account_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    left_sessions = remove_class_member(db, account, class_id, account_id)
    # After the commit: close the removed member's live sockets in this class
    # and update the hosts of the sessions they were playing in.
    background_tasks.add_task(
        request.app.state.live_hub.evict_class_member,
        class_id,
        account_id,
        left_sessions,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
