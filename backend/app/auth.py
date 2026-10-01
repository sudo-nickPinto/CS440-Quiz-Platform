import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.errors import APIError

bearer = HTTPBearer(auto_error=False)
_jwks: jwt.PyJWKClient | None = None


def _jwks_client(domain: str) -> jwt.PyJWKClient:
    # Created lazily so the app starts (and /docs works) without Auth0 config.
    global _jwks
    if _jwks is None:
        _jwks = jwt.PyJWKClient(f"https://{domain}/.well-known/jwks.json")
    return _jwks


def current_user(
    request: Request, creds: HTTPAuthorizationCredentials | None = Depends(bearer)
) -> dict:
    """Validate the Auth0 access token and return its claims."""
    settings = request.app.state.settings
    if not settings.auth0_domain or not settings.auth0_audience:
        raise APIError(500, "auth_not_configured", "AUTH0_DOMAIN and AUTH0_AUDIENCE are not configured")
    if creds is None:
        raise APIError(401, "missing_token", "Missing bearer token")
    try:
        key = _jwks_client(settings.auth0_domain).get_signing_key_from_jwt(creds.credentials)
        return jwt.decode(
            creds.credentials,
            key.key,
            algorithms=["RS256"],
            audience=settings.auth0_audience,
            issuer=f"https://{settings.auth0_domain}/",
        )
    except jwt.PyJWTError:
        raise APIError(401, "invalid_token", "Invalid token")
