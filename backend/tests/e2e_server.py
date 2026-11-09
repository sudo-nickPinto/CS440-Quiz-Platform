"""Run the real API on a free port for the frontend's live e2e test.

    cd backend && python -m tests.e2e_server

Uses a throwaway SQLite file and the test RSA key instead of Auth0, prints one
JSON line {"base_url": ..., "tokens": {name: jwt}} to stdout, then serves until
killed. Only faculty can create classes and there's no API to make someone
faculty, so this server adds a test-only POST /e2e/faculty/{name} for an
account that has already logged in. Everything else (class, quiz, publish,
approval, session) goes through the real API. The files in frontend/e2e/
start it; it is not a pytest module.

Set E2E_DATABASE_URL to a MySQL database that already has every migration
applied (same setup as CI's TEST_DATABASE_URL; the name must contain "test")
to run against MySQL instead of SQLite. Tests create their own classes, so
the database doesn't need to be empty.
"""

import json
import os
import socket
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import uvicorn
from sqlalchemy import create_engine, make_url, select, text

from app import accounts, auth
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models.account import Account
from tests.test_accounts import AUDIENCE, DOMAIN, PRIVATE_KEY, make_token

# live.e2e.test.js uses the first three; full_flow.e2e.test.js the rest.
PEOPLE = (
    "host", "alice", "bob",
    "prof", "ta", "ana", "ben", "cy", "dee", "zed",
)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _sqlite_database() -> str:
    db_path = Path(tempfile.mkdtemp(prefix="quiz-e2e-")) / "e2e.sqlite3"
    database_url = f"sqlite:///{db_path}"
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE account_identity ("
                " auth0_sub VARCHAR(255) NOT NULL PRIMARY KEY,"
                " account_id INTEGER NOT NULL REFERENCES account (account_id))"
            )
        )
    engine.dispose()
    return database_url


def _database_url() -> str:
    url = os.environ.get("E2E_DATABASE_URL", "").strip()
    if not url:
        return _sqlite_database()
    parsed = make_url(url)
    if not parsed.drivername.startswith("mysql"):
        sys.exit("E2E_DATABASE_URL must use MySQL.")
    if "test" not in (parsed.database or "").lower():
        sys.exit("E2E_DATABASE_URL database name must contain 'test'.")
    return url


def main() -> None:
    database_url = _database_url()

    # Verify tokens with the test key, and make each first login a verified
    # account named after its sub ("e2e|alice" -> "Alice").
    fake_jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(
            key=PRIVATE_KEY.public_key()
        )
    )
    auth._jwks_client = lambda domain: fake_jwks

    def fake_profile(domain, token):
        sub = auth.jwt.decode(token, options={"verify_signature": False})["sub"]
        name = sub.split("|", 1)[1]
        return {
            "email": f"{name}@e2e.invalid",
            "email_verified": True,
            "name": name.title(),
        }

    accounts._fetch_profile = fake_profile

    port = _free_port()
    app = create_app(
        Settings(database_url=database_url, auth0_domain=DOMAIN, auth0_audience=AUDIENCE)
    )

    @app.post("/e2e/faculty/{name}")
    def make_faculty(name: str) -> dict:
        with app.state.database.session_factory() as db:
            account = db.scalar(
                select(Account).where(Account.email == f"{name}@e2e.invalid")
            )
            account.account_type = "ADMINISTRATOR"
            db.commit()
            return {"account_id": account.account_id}

    print(
        json.dumps(
            {
                "base_url": f"http://127.0.0.1:{port}",
                "tokens": {name: make_token(sub=f"e2e|{name}") for name in PEOPLE},
            }
        ),
        flush=True,
    )
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    sys.exit(main())
