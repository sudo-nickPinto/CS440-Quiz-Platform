import os

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE", "")

bearer = HTTPBearer(auto_error=False)
_jwks = None


def _jwks_client() -> jwt.PyJWKClient:
    # Created lazily so the app can start (and /docs work) without Auth0 config.
    global _jwks
    if not AUTH0_DOMAIN or not AUTH0_AUDIENCE:
        raise HTTPException(500, "AUTH0_DOMAIN and AUTH0_AUDIENCE are not configured")
    if _jwks is None:
        _jwks = jwt.PyJWKClient(f"https://{AUTH0_DOMAIN}/.well-known/jwks.json")
    return _jwks


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    """Validate the Auth0 access token and return its claims."""
    if creds is None:
        raise HTTPException(401, "Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    try:
        key = _jwks_client().get_signing_key_from_jwt(creds.credentials)
        return jwt.decode(
            creds.credentials,
            key.key,
            algorithms=["RS256"],
            audience=AUTH0_AUDIENCE,
            issuer=f"https://{AUTH0_DOMAIN}/",
        )
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token", headers={"WWW-Authenticate": "Bearer"})
