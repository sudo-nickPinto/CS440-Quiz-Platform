from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.class_membership import (
    ClassMemberCreate,
    ClassMemberResponse,
    ClassMemberUpdate,
)
from app.services.class_memberships import (
    add_class_member,
    get_class_member,
    list_class_members,
    remove_class_member,
    update_class_member,
)

router = APIRouter(prefix="/classes/{class_id}/members", tags=["class members"])


@router.get("", response_model=list[ClassMemberResponse])
def list_class_members_route(
    class_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> list[ClassMemberResponse]:
    return list_class_members(db, account, class_id)


@router.post("", response_model=ClassMemberResponse, status_code=status.HTTP_201_CREATED)
def add_class_member_route(
    class_id: int,
    payload: ClassMemberCreate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassMemberResponse:
    return add_class_member(db, account, class_id, payload)


@router.get("/{account_id}", response_model=ClassMemberResponse)
def get_class_member_route(
    class_id: int,
    account_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassMemberResponse:
    return get_class_member(db, account, class_id, account_id)


@router.patch("/{account_id}", response_model=ClassMemberResponse)
def update_class_member_route(
    class_id: int,
    account_id: int,
    payload: ClassMemberUpdate,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> ClassMemberResponse:
    return update_class_member(db, account, class_id, account_id, payload)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_class_member_route(
    class_id: int,
    account_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    remove_class_member(db, account, class_id, account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
