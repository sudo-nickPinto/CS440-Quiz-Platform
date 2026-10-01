from fastapi import APIRouter, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.accounts import get_or_create_account
from app.auth import bearer, current_user
from app.database import get_db

router = APIRouter(tags=["accounts"])


def current_account(
    request: Request,
    claims: dict = Depends(current_user),
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> dict:
    return get_or_create_account(
        db, request.app.state.settings.auth0_domain, claims["sub"], creds.credentials
    )


@router.get("/me")
def me(account: dict = Depends(current_account)) -> dict:
    return account
