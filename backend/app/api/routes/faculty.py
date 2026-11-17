from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.database import get_db
from app.schemas.faculty import FacultyAccessPage, FacultyGrantRequest, FacultyMember
from app.services.faculty_access import (
    grant_faculty_access,
    list_faculty_access,
    revoke_faculty_access,
)

router = APIRouter(prefix="/faculty", tags=["faculty"])


@router.get("", response_model=FacultyAccessPage)
def list_faculty_route(
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> FacultyAccessPage:
    return list_faculty_access(db, account)


@router.post("", response_model=FacultyMember, status_code=status.HTTP_201_CREATED)
def grant_faculty_route(
    payload: FacultyGrantRequest,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> FacultyMember:
    return grant_faculty_access(db, account, payload.email)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_faculty_route(
    account_id: int,
    db: Session = Depends(get_db),
    account: CurrentAccount = Depends(get_active_account),
) -> Response:
    revoke_faculty_access(db, account, account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
