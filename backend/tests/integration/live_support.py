"""Shared MySQL setup for the live-session integration tests.

These tests drive the real app end to end: signed JWTs through the same
fake-JWKS patch as tests/test_accounts.py, REST and WebSocket calls through
TestClient, and the migrated MySQL test database underneath. Nothing talks to
Auth0.

Import the fixture into a test module with
``from tests.integration.live_support import mysql_live  # noqa: F401``.
"""

import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from app import auth
from app.auth import CurrentAccount
from app.config import Settings
from app.main import create_app
from app.models import Account, AccountRole, LiveSession
from tests.integration.conftest import cleanup_database
from tests.test_accounts import AUDIENCE, DOMAIN, PRIVATE_KEY, make_token

# host, alice, bob and outsider match tests/test_live_host_controls.py, so its
# helpers (make_session, join, connect, ...) work on these accounts too.
PEOPLE = {
    "host": None,
    "alice": None,
    "bob": None,
    "outsider": None,
    "faculty": "ADMINISTRATOR",
}


def mysql_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run migrated MySQL integration tests.")
    parsed = make_url(url)
    if not parsed.drivername.startswith("mysql"):
        pytest.fail("TEST_DATABASE_URL must use MySQL.")
    if not parsed.database or "test" not in parsed.database.lower():
        pytest.fail("TEST_DATABASE_URL database name must contain 'test'.")
    return url


def patch_jwks(monkeypatch) -> None:
    """Verify tokens against the test key instead of Auth0's JWKS."""
    fake_jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(
            key=PRIVATE_KEY.public_key()
        )
    )
    monkeypatch.setattr(auth, "_jwks_client", lambda domain: fake_jwks)


def add_people(app) -> dict[str, CurrentAccount]:
    """One account per PEOPLE entry, each with its own Auth0 login (sub)."""
    people: dict[str, CurrentAccount] = {}
    with app.state.database.session_factory() as db:
        for name, account_type in PEOPLE.items():
            model = Account(
                auth0_sub=f"test|{name}",
                email=f"{name}@test.invalid",
                display_name=name.title(),
                account_type=account_type,
            )
            db.add(model)
            db.flush()
            db.execute(
                text(
                    "INSERT INTO account_identity (auth0_sub, account_id) "
                    "VALUES (:sub, :id)"
                ),
                {"sub": f"test|{name}", "id": model.account_id},
            )
            role = AccountRole.ADMIN if account_type else AccountRole.USER
            people[name] = CurrentAccount(model.account_id, role, True)
        db.commit()
    return people


@contextmanager
def live_app(monkeypatch, **settings) -> Iterator[tuple[TestClient, dict]]:
    """A started app on the MySQL test database, with the PEOPLE accounts."""
    database_url = mysql_url()
    patch_jwks(monkeypatch)
    app = create_app(
        Settings(
            database_url=database_url,
            auth0_domain=DOMAIN,
            auth0_audience=AUDIENCE,
            **settings,
        )
    )
    with TestClient(app) as client:
        cleanup_database(app)
        people = add_people(app)
        try:
            yield client, people
        finally:
            app.dependency_overrides.clear()
            cleanup_database(app)


@pytest.fixture
def mysql_live(monkeypatch) -> Iterator[tuple[TestClient, dict]]:
    # The background reaper is off so tests can run passes themselves.
    with live_app(monkeypatch, live_abandon_after_seconds=0) as live:
        yield live


def bearer(name: str, **claims) -> dict[str, str]:
    """Authorization header with a real signed token for test|<name>."""
    return {"Authorization": f"Bearer {make_token(sub=f'test|{name}', **claims)}"}


def wait_until(check: Callable[[], bool], timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not check():
        if time.monotonic() > deadline:
            raise AssertionError("Timed out waiting for the condition.")
        time.sleep(0.02)


def host_connected(client: TestClient, session_id: int) -> bool:
    hub = client.app.state.live_hub
    return client.portal.call(hub.host_connected, session_id)


def wait_for_host_to_leave(client: TestClient, session_id: int) -> None:
    """The hub handles a client-side close asynchronously; wait for it."""
    wait_until(lambda: not host_connected(client, session_id))


def stored_session(client: TestClient, session_id: int) -> LiveSession:
    with client.app.state.database.session_factory() as db:
        session = db.scalar(
            select(LiveSession).where(LiveSession.session_id == session_id)
        )
        db.expunge(session)
        return session
