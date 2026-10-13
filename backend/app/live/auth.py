import jwt
from sqlalchemy.orm import Session

from app.accounts import get_or_create_account
from app.auth import CurrentAccount, _jwks_client
from app.config import Settings
from app.live.protocol import CloseCode, LiveCloseError
from app.models.account import effective_role


def authenticate_token(db: Session, settings: Settings, token: str) -> CurrentAccount:
    """Verify an Auth0 access token the same way the HTTP auth chain does."""
    if not settings.auth0_domain or not settings.auth0_audience:
        raise LiveCloseError(CloseCode.SERVER_ERROR, "auth_not_configured")
    try:
        key = _jwks_client(settings.auth0_domain).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key.key,
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=f"https://{settings.auth0_domain}/",
        )
    except jwt.PyJWTError as exc:
        raise LiveCloseError(CloseCode.UNAUTHORIZED, "invalid_token") from exc

    record = get_or_create_account(db, settings.auth0_domain, claims["sub"], token)
    account = CurrentAccount(
        account_id=record["account_id"],
        role=effective_role(record["account_type"]),
        is_active=bool(record["is_active"]),
    )
    if not account.is_active:
        raise LiveCloseError(CloseCode.FORBIDDEN, "inactive_account")
    return account
