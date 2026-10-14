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
    account_type VARCHAR(20) NULL,
    status       VARCHAR(10) NOT NULL DEFAULT 'ACTIVE'
                 CHECK (status IN ('PENDING', 'ACTIVE', 'DISABLED')),
    is_active    BOOLEAN NOT NULL DEFAULT 1,
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_account_status_active CHECK (is_active = (status = 'ACTIVE'))
);
CREATE TABLE account_identity (
    auth0_sub  VARCHAR(255) NOT NULL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES account (account_id) ON DELETE CASCADE
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
            for statement in ACCOUNT_DDL.split(";"):
                conn.execute(text(statement))
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
    assert body["role"] == "USER"
    assert body["status"] == "ACTIVE"
    assert body["is_active"] is True
    assert "account_type" not in body
    assert count_accounts(client) == 1


def test_repeat_login_reuses_account(client):
    first = get_me(client, make_token()).json()
    second = get_me(client, make_token()).json()
    assert first["account_id"] == second["account_id"]
    assert count_accounts(client) == 1


def test_unverified_email_creates_pending_account(client):
    client.profile["email_verified"] = False
    response = get_me(client, make_token())
    assert response.status_code == 200
    assert response.json()["status"] == "PENDING"
    assert response.json()["is_active"] is False
    assert count_accounts(client) == 1


def count_identities(client):
    with client.app_ref.state.database.engine.connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM account_identity")).scalar()


def test_same_email_with_other_login_method_links_to_one_account(client):
    first = get_me(client, make_token("auth0|abc"))
    second = get_me(client, make_token("google-oauth2|123"))
    assert second.status_code == 200
    assert first.json()["account_id"] == second.json()["account_id"]
    assert count_accounts(client) == 1
    assert count_identities(client) == 2


def test_linked_login_is_reused(client):
    get_me(client, make_token("auth0|abc"))
    get_me(client, make_token("google-oauth2|123"))
    again = get_me(client, make_token("google-oauth2|123"))
    assert again.status_code == 200
    assert count_identities(client) == 2


def test_unverified_email_is_not_linked(client):
    get_me(client, make_token("google-oauth2|123"))
    client.profile["email_verified"] = False
    response = get_me(client, make_token("auth0|abc"))
    assert response.status_code == 409
    assert error_code(response) == "email_in_use"
    assert count_identities(client) == 1


# --- Approving email/password signups -------------------------------------


def insert_account(client, email, status="ACTIVE", account_type=None):
    with client.app_ref.state.database.engine.begin() as conn:
        return conn.execute(
            text(
                "INSERT INTO account (auth0_sub, email, display_name, account_type, status, is_active) "
                "VALUES (:sub, :email, :email, :type, :status, :active)"
            ),
            {
                "sub": f"seed|{email}",
                "email": email,
                "type": account_type,
                "status": status,
                "active": status == "ACTIVE",
            },
        ).lastrowid


def account_status(client, account_id):
    with client.app_ref.state.database.engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, is_active FROM account WHERE account_id = :id"),
            {"id": account_id},
        ).first()
    return None if row is None else (row[0], bool(row[1]))


def login_as(client, account_type=None):
    """Log in as a@example.com (ACTIVE) and return auth headers."""
    token = make_token()
    me = get_me(client, token).json()
    if account_type:
        with client.app_ref.state.database.engine.begin() as conn:
            conn.execute(
                text("UPDATE account SET account_type = :type WHERE account_id = :id"),
                {"type": account_type, "id": me["account_id"]},
            )
    return {"Authorization": f"Bearer {token}"}


APPROVAL_CALLS = [
    ("get", "/accounts/pending"),
    ("post", "/accounts/{id}/approve"),
    ("delete", "/accounts/{id}"),
]


@pytest.mark.parametrize("method,path", APPROVAL_CALLS, ids=["list", "approve", "reject"])
def test_regular_user_cannot_use_approval_endpoints(client, method, path):
    headers = login_as(client)
    pending_id = insert_account(client, "new@example.com", status="PENDING")

    response = getattr(client, method)(path.format(id=pending_id), headers=headers)

    assert response.status_code == 403
    assert error_code(response) == "admin_required"
    assert account_status(client, pending_id) == ("PENDING", False)


def test_admin_lists_only_pending_accounts(client):
    headers = login_as(client, "ADMINISTRATOR")
    pending_id = insert_account(client, "new@example.com", status="PENDING")
    insert_account(client, "off@example.com", status="DISABLED")
    insert_account(client, "on@example.com", status="ACTIVE")

    response = client.get("/accounts/pending", headers=headers)

    assert response.status_code == 200
    assert [row["account_id"] for row in response.json()] == [pending_id]


def test_admin_approves_pending_account(client):
    headers = login_as(client, "ADMINISTRATOR")
    pending_id = insert_account(client, "new@example.com", status="PENDING")

    response = client.post(f"/accounts/{pending_id}/approve", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "ACTIVE"
    assert account_status(client, pending_id) == ("ACTIVE", True)


def test_admin_rejects_pending_account(client):
    headers = login_as(client, "ADMINISTRATOR")
    pending_id = insert_account(client, "new@example.com", status="PENDING")

    response = client.delete(f"/accounts/{pending_id}", headers=headers)

    assert response.status_code == 204
    assert account_status(client, pending_id) is None


@pytest.mark.parametrize("status", ["DISABLED", "ACTIVE"])
def test_approve_does_not_touch_non_pending_account(client, status):
    headers = login_as(client, "ADMINISTRATOR")
    other_id = insert_account(client, "other@example.com", status=status)

    response = client.post(f"/accounts/{other_id}/approve", headers=headers)

    assert response.status_code == 404
    assert error_code(response) == "not_pending"
    assert account_status(client, other_id) == (status, status == "ACTIVE")


@pytest.mark.parametrize("status", ["DISABLED", "ACTIVE"])
def test_reject_does_not_delete_non_pending_account(client, status):
    headers = login_as(client, "ADMINISTRATOR")
    other_id = insert_account(client, "other@example.com", status=status)

    response = client.delete(f"/accounts/{other_id}", headers=headers)

    assert response.status_code == 404
    assert error_code(response) == "not_pending"
    assert account_status(client, other_id) == (status, status == "ACTIVE")


def test_disabled_account_cannot_use_the_app(client):
    get_me(client, make_token())
    with client.app_ref.state.database.engine.begin() as conn:
        conn.execute(text("UPDATE account SET status = 'DISABLED', is_active = FALSE"))

    me = get_me(client, make_token())
    pending = client.get("/accounts/pending", headers={"Authorization": f"Bearer {make_token()}"})

    assert me.json()["status"] == "DISABLED"
    assert me.json()["is_active"] is False
    assert pending.status_code == 403
    assert error_code(pending) == "inactive_account"
