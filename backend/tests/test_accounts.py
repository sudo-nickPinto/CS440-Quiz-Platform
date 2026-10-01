import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import accounts, auth
from app.config import Settings
from app.main import create_app

DOMAIN = "tenant.example.auth0.com"
AUDIENCE = "https://quiz-platform-api"
PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

# SQLite stand-in for the MySQL `account` table (same columns and unique keys).
ACCOUNT_DDL = """
CREATE TABLE account (
    account_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    auth0_sub    VARCHAR(255) NOT NULL UNIQUE,
    email        VARCHAR(320) NOT NULL UNIQUE,
    display_name VARCHAR(100) NOT NULL,
    account_type VARCHAR(20) NULL
)
"""


def make_token(sub="auth0|abc", audience=AUDIENCE, issuer=f"https://{DOMAIN}/", exp_offset=3600):
    claims = {"sub": sub, "aud": audience, "iss": issuer, "exp": int(time.time()) + exp_offset}
    return jwt.encode(claims, PRIVATE_KEY, algorithm="RS256")


@pytest.fixture
def client(monkeypatch):
    # Verify against our own key instead of downloading Auth0's JWKS.
    fake_jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=PRIVATE_KEY.public_key())
    )
    monkeypatch.setattr(auth, "_jwks_client", lambda domain: fake_jwks)
    profile = {"email": "a@example.com", "email_verified": True, "name": "Ada"}
    monkeypatch.setattr(accounts, "_fetch_profile", lambda domain, token: dict(profile))

    app = create_app(
        Settings(database_url="sqlite://", auth0_domain=DOMAIN, auth0_audience=AUDIENCE)
    )
    with TestClient(app) as test_client:
        with app.state.database.engine.begin() as conn:
            conn.execute(text(ACCOUNT_DDL))
        test_client.profile = profile
        test_client.app_ref = app
        yield test_client


def get_me(client, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get("/me", headers=headers)


def count_accounts(client):
    with client.app_ref.state.database.engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM account")).scalar()


def error_code(response):
    return response.json()["error"]["code"]


def test_me_requires_token(client):
    response = get_me(client)
    assert response.status_code == 401
    assert error_code(response) == "missing_token"


def test_me_rejects_garbage_token(client):
    response = get_me(client, "not-a-jwt")
    assert response.status_code == 401
    assert error_code(response) == "invalid_token"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"audience": "https://some-other-api"},
        {"issuer": "https://evil.example.com/"},
        {"exp_offset": -10},
    ],
    ids=["wrong-audience", "wrong-issuer", "expired"],
)
def test_me_rejects_bad_claims(client, kwargs):
    response = get_me(client, make_token(**kwargs))
    assert response.status_code == 401
    assert error_code(response) == "invalid_token"


def test_me_rejects_token_signed_by_other_key(client):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(
        {"sub": "x", "aud": AUDIENCE, "iss": f"https://{DOMAIN}/", "exp": int(time.time()) + 60},
        other,
        algorithm="RS256",
    )
    assert get_me(client, token).status_code == 401


def test_me_reports_missing_auth0_config():
    # Explicit empty values: Settings would otherwise read a developer's real .env.
    app = create_app(Settings(database_url="sqlite://", auth0_domain="", auth0_audience=""))
    with TestClient(app) as client:
        response = client.get("/me", headers={"Authorization": "Bearer x"})
    assert response.status_code == 500
    assert error_code(response) == "auth_not_configured"


def test_first_login_creates_account(client):
    response = get_me(client, make_token())
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "a@example.com"
    assert body["display_name"] == "Ada"
    assert body["account_type"] is None  # nobody has a role until we decide how to assign them
    assert count_accounts(client) == 1


def test_repeat_login_reuses_account(client):
    first = get_me(client, make_token()).json()
    second = get_me(client, make_token()).json()
    assert first["account_id"] == second["account_id"]
    assert count_accounts(client) == 1


def test_unverified_email_is_rejected(client):
    client.profile["email_verified"] = False
    response = get_me(client, make_token())
    assert response.status_code == 403
    assert error_code(response) == "email_not_verified"
    assert count_accounts(client) == 0


def test_same_email_with_other_login_method_conflicts(client):
    assert get_me(client, make_token("auth0|abc")).status_code == 200
    response = get_me(client, make_token("google-oauth2|123"))
    assert response.status_code == 409
    assert error_code(response) == "email_already_registered"
    assert count_accounts(client) == 1
