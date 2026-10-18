"""Run the real API on a free port for the frontend's live e2e test.

    cd backend && python -m tests.e2e_server

Uses a throwaway SQLite file and the test RSA key instead of Auth0, prints one
JSON line {"base_url": ..., "tokens": {name: jwt}} to stdout, then serves until
killed. frontend/e2e/live.e2e.test.js starts it; it is not a pytest module.
"""

import json
import socket
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import uvicorn
from sqlalchemy import create_engine, text

from app import accounts, auth
from app.config import Settings
from app.database import Base
from app.main import create_app
from tests.test_accounts import AUDIENCE, DOMAIN, PRIVATE_KEY, make_token

PEOPLE = ("host", "alice", "bob")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
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
