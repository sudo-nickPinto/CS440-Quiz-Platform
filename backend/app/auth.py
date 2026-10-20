from dataclasses import dataclass
import re

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
import logging

from app.accounts import get_or_create_account, get_or_create_dev_account
from app.database import get_db
from app.errors import APIError
from app.models.account import AccountRole, effective_role

bearer = HTTPBearer(auto_error=False)
_jwks: jwt.PyJWKClient | None = None
TOKEN_LEEWAY_SECONDS = 30
DEV_AUTH_TOKEN_PREFIX = "local-development-token:"
DEV_AUTH_IDENTITY_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}\Z")


def dev_auth_identity(token: str) -> str | None:
    """Extract a constrained local identity from a development token."""
    if not token.startswith(DEV_AUTH_TOKEN_PREFIX):
        return None
    identity = token.removeprefix(DEV_AUTH_TOKEN_PREFIX)
    return identity if DEV_AUTH_IDENTITY_PATTERN.fullmatch(identity) else None


@dataclass(frozen=True, slots=True)
class CurrentAccount:
    account_id: int
    role: AccountRole
    is_active: bool

    @property
    def is_admin(self) -> bool:
        return self.role == AccountRole.ADMIN


def _jwks_client(domain: str) -> jwt.PyJWKClient:
    # Created lazily so the app starts (and /docs works) without Auth0 config.
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(f"https://{domain}/.well-known/jwks.json")
    return _jwks


def decode_access_token(settings, token: str) -> dict:
    """Verify an Auth0 access token's signature and claims; raises PyJWTError.

    Shared by HTTP and the live WebSocket so both accept the same tokens.
    """
    key = _jwks_client(settings.auth0_domain).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        key.key,
        algorithms=["RS256"],
        audience=settings.auth0_audience,
        issuer=f"https://{settings.auth0_domain}/",
        # Tolerate small clock skew; without it a fresh token whose iat is
        # a fraction of a second ahead of this machine fails as invalid.
        leeway=TOKEN_LEEWAY_SECONDS,
    )


def current_user(
    request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> dict:
    """Validate the Auth0 access token and return its claims."""
    settings = request.app.state.settings
    if settings.dev_auth_enabled:
        identity = dev_auth_identity(creds.credentials) if creds else None
        if identity is None:
            raise APIError(401, "invalid_token", "Invalid local development token")
        return {"sub": f"dev|{identity}", "dev_auth_identity": identity}
    if not settings.auth0_domain or not settings.auth0_audience:
        raise APIError(500, "auth_not_configured", "AUTH0_DOMAIN and AUTH0_AUDIENCE are not configured")
    if creds is None:
        raise APIError(401, "missing_token", "Missing bearer token")
    try:
        return decode_access_token(settings, creds.credentials)
    except jwt.PyJWTError as exc:
        logging.getLogger(__name__).warning(
            "Auth0 token validation failed: %s",
            type(exc).__name__,
        )
        raise APIError(
            401,
            "invalid_token",
            "Invalid token",
        ) from exc




def get_account_record(
    request: Request,
    claims: dict = Depends(current_user),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> dict:
    if creds is None:
        raise APIError(401, "missing_token", "Missing bearer token")
    settings = request.app.state.settings
    identity = claims.get("dev_auth_identity")
    if settings.dev_auth_enabled and isinstance(identity, str):
        return get_or_create_dev_account(db, identity)
    return get_or_create_account(
        db,
        settings.auth0_domain,
        claims["sub"],
        creds.credentials,
    )


def get_current_account(
    account: dict = Depends(get_account_record),
) -> CurrentAccount:
    return CurrentAccount(
        account_id=account["account_id"],
        role=effective_role(account["account_type"]),
        is_active=bool(account["is_active"]),
    )


def get_active_account(
    account: CurrentAccount = Depends(get_current_account),
) -> CurrentAccount:
    if not account.is_active:
        raise APIError(403, "inactive_account", "This account is inactive.")
    return account
