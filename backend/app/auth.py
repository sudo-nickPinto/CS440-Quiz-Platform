from dataclasses import dataclass

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.accounts import get_or_create_account
from app.database import get_db
from app.errors import APIError
from app.models.account import AccountType

bearer = HTTPBearer(auto_error=False)
_jwks: jwt.PyJWKClient | None = None


@dataclass(frozen=True, slots=True)
class CurrentAccount:
    """Authenticated account information needed by protected endpoints."""

    account_id: int
    account_type: AccountType | None
    is_active: bool = True


def _jwks_client(domain: str) -> jwt.PyJWKClient:
    # Created lazily so the app starts (and /docs works) without Auth0 config.
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(f"https://{domain}/.well-known/jwks.json")
    return _jwks


def current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    """Validate the Auth0 access token and return its claims."""
    settings = request.app.state.settings
    if not settings.auth0_domain or not settings.auth0_audience:
        raise APIError(
            500,
            "auth_not_configured",
            "AUTH0_DOMAIN and AUTH0_AUDIENCE are not configured",
        )
    if creds is None:
        raise APIError(401, "missing_token", "Missing bearer token")
    try:
        key = _jwks_client(settings.auth0_domain).get_signing_key_from_jwt(
            creds.credentials
        )
        return jwt.decode(
            creds.credentials,
            key.key,
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=f"https://{settings.auth0_domain}/",
        )
    except jwt.PyJWTError as exc:
        raise APIError(401, "invalid_token", "Invalid token") from exc


def get_current_account(
    request: Request,
    claims: dict = Depends(current_user),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> CurrentAccount:
    """Resolve the verified Auth0 identity to the application's account row."""
    if creds is None:
        raise APIError(401, "missing_token", "Missing bearer token")
    account = get_or_create_account(
        db,
        request.app.state.settings.auth0_domain,
        claims["sub"],
        creds.credentials,
    )
    account_type = account["account_type"]
    return CurrentAccount(
        account_id=account["account_id"],
        account_type=AccountType(account_type) if account_type else None,
        is_active=bool(account["is_active"]),
    )
