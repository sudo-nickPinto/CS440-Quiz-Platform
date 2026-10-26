from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.class_membership import (
    ClassInviteCreate,
    ClassMemberResponse,
    ClassMemberUpdate,
)
from app.services.class_memberships import (
    accept_class_invite,
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
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassMemberResponse:
    return create_class_invite(db, account, class_id, payload)


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
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    remove_class_member(db, account, class_id, account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
