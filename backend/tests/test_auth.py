"""End-to-end auth tests: a real signed token through get_active_account.

test_accounts.py covers token validation on /me. These tests cover the layer
protected routes use (token -> account row -> CurrentAccount), without the
dependency overrides that test_quiz_api.py relies on.
"""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import accounts, auth
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models.account import AccountRole, effective_role
from tests.test_accounts import AUDIENCE, DOMAIN, PRIVATE_KEY, make_token


@pytest.fixture
def client(monkeypatch):
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
        Base.metadata.create_all(app.state.database.engine)
        with app.state.database.engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE account_identity ("
                    " auth0_sub VARCHAR(255) NOT NULL PRIMARY KEY,"
                    " account_id INTEGER NOT NULL REFERENCES account (account_id))"
                )
            )
        test_client.app_ref = app
        yield test_client


def get_quizzes(client, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get("/quizzes", headers=headers)


def set_account(client, **values):
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    with client.app_ref.state.database.engine.begin() as conn:
        conn.execute(text(f"UPDATE account SET {assignments}"), values)


def test_protected_route_requires_token(client):
    response = get_quizzes(client)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_token"


def test_protected_route_rejects_invalid_token(client):
    response = get_quizzes(client, "not-a-jwt")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_protected_route_rejects_expired_token(client):
    response = get_quizzes(client, make_token(exp_offset=-60))
    assert response.status_code == 401


def test_valid_token_reaches_protected_route(client):
    response = get_quizzes(client, make_token())
    assert response.status_code == 200
    assert response.json() == []


def test_inactive_account_is_forbidden(client):
    token = make_token()
    get_quizzes(client, token)  # first login creates the account
    set_account(client, is_active=False)

    response = get_quizzes(client, token)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "inactive_account"


def test_new_account_is_a_user(client):
    response = client.get("/me", headers={"Authorization": f"Bearer {make_token()}"})
    assert response.json()["role"] == AccountRole.USER


def test_administrator_account_type_becomes_admin(client):
    token = make_token()
    get_quizzes(client, token)
    set_account(client, account_type="ADMINISTRATOR")

    account = auth.get_current_account(
        {"account_id": 1, "account_type": "ADMINISTRATOR", "is_active": 1}
    )
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.json()["role"] == AccountRole.ADMIN
    assert account.is_admin


@pytest.mark.parametrize("account_type", [None, "STUDENT", "PROFESSOR", "unexpected"])
def test_every_other_account_type_is_a_user(account_type):
    # MVP has only User and Admin; professor/student are not roles yet.
    assert effective_role(account_type) == AccountRole.USER
