import jwt
from sqlalchemy.orm import Session

# Module lookups, not name imports, so tests that patch the HTTP auth chain
# (auth._jwks_client, accounts._fetch_profile) patch this path too.
from app import accounts, auth
from app.auth import CurrentAccount
from app.config import Settings
from app.errors import APIError
from app.live.protocol import CloseCode, LiveCloseError, close_code_for_status
from app.models.account import effective_role


def authenticate_token(db: Session, settings: Settings, token: str) -> CurrentAccount:
    """Verify an Auth0 access token the same way the HTTP auth chain does.

    Every expected failure becomes a LiveCloseError with a §7 close code, so
    only genuinely unexpected errors reach the handler's 1011 fallback.
    """
    if not settings.auth0_domain or not settings.auth0_audience:
        raise LiveCloseError(CloseCode.SERVER_ERROR, "auth_not_configured")
    if not token:
        raise LiveCloseError(CloseCode.UNAUTHORIZED, "missing_token")
    try:
        key = auth._jwks_client(settings.auth0_domain).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=f"https://{settings.auth0_domain}/",
        )
    except jwt.ExpiredSignatureError as exc:
        raise LiveCloseError(CloseCode.UNAUTHORIZED, "token_expired") from exc
    except jwt.PyJWTError as exc:
        raise LiveCloseError(CloseCode.UNAUTHORIZED, "invalid_token") from exc

    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise LiveCloseError(CloseCode.UNAUTHORIZED, "invalid_token")

    try:
        record = accounts.get_or_create_account(db, settings.auth0_domain, sub, token)
    except APIError as exc:
        # e.g. email_not_verified (403) -> 4403. profile_unavailable (502) is
        # an upstream outage, so it stays 1011 and the client retries.
        raise LiveCloseError(close_code_for_status(exc.status_code), exc.code) from exc
    if record is None:
        raise LiveCloseError(CloseCode.FORBIDDEN, "account_not_found")

    account = CurrentAccount(
        account_id=record["account_id"],
        role=effective_role(record["account_type"]),
        is_active=bool(record["is_active"]),
    )
    if not account.is_active:
        raise LiveCloseError(CloseCode.FORBIDDEN, "inactive_account")
    return account
