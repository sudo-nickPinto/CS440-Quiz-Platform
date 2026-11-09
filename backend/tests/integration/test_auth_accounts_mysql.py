"""Signing in and account linking (PRs #21, #22, #40, #42, #52), on migrated MySQL.

tests/test_accounts.py runs the same lookup against a hand-written SQLite
table. These run it against the real migrated schema, where emails compare
without regard to case, names have a length limit, and two first requests
for the same person can race on unique keys. Tokens are signed with the
test key and Auth0's /userinfo is stubbed, so nothing talks to Auth0.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import jwt
import pytest
from sqlalchemy import text

from app import accounts
from app.accounts import get_or_create_account
from app.errors import APIError
from tests.integration.live_support import bearer, mysql_live  # noqa: F401
from tests.test_accounts import DOMAIN, make_token


def stub_userinfo(monkeypatch, profiles: dict, barrier: Barrier | None = None) -> list:
    """Answer Auth0's /userinfo from profiles, keyed by the token's sub.

    Returns the list of subs looked up, so tests can see when it was asked.
    """
    asked: list[str] = []

    def fetch_profile(domain: str, token: str) -> dict:
        sub = jwt.decode(token, options={"verify_signature": False})["sub"]
        asked.append(sub)
        if barrier is not None:
            # Hold every first request here until all of them got this far.
            barrier.wait(timeout=10)
        profile = profiles[sub]
        if isinstance(profile, APIError):
            raise profile
        return dict(profile)

    monkeypatch.setattr(accounts, "_fetch_profile", fetch_profile)
    return asked


def me(client, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get("/me", headers=headers)


def error_code(response) -> str:
    return response.json()["error"]["code"]


def stored(client, email: str) -> list[tuple]:
    """(account_id, account auth0_sub, display_name, identity sub) rows."""
    with client.app.state.database.engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT a.account_id, a.auth0_sub, a.display_name, i.auth0_sub "
                "FROM account a "
                "LEFT JOIN account_identity i ON i.account_id = a.account_id "
                "WHERE a.email = :email ORDER BY i.created_at, i.auth0_sub"
            ),
            {"email": email},
        ).all()
    return [tuple(row) for row in rows]


def test_first_login_creates_an_account_that_later_logins_reuse(
    mysql_live, monkeypatch
) -> None:
    client, _ = mysql_live
    asked = stub_userinfo(
        monkeypatch,
        {
            "auth0|ada": {
                "email": "ada@test.invalid",
                "email_verified": True,
                "name": "Ada Lovelace \U0001f680",
            },
            # The same person signing in another way, with the address in
            # different case.
            "email|ada": {
                "email": "Ada@Test.Invalid",
                "email_verified": True,
                "name": "Someone Else",
            },
        },
    )

    first = me(client, make_token(sub="auth0|ada"))
    assert first.status_code == 200, first.text
    account_id = first.json()["account_id"]
    assert first.json() == {
        "account_id": account_id,
        "email": "ada@test.invalid",
        "display_name": "Ada Lovelace \U0001f680",
        "role": "USER",
        "is_active": True,
    }
    assert stored(client, "ada@test.invalid") == [
        (account_id, "auth0|ada", "Ada Lovelace \U0001f680", "auth0|ada")
    ]

    # Signing in again is a database lookup; Auth0 isn't asked twice.
    again = me(client, make_token(sub="auth0|ada"))
    assert again.json()["account_id"] == account_id
    assert asked == ["auth0|ada"]

    # A new login with the same verified email joins the same account and
    # keeps the original name and first login.
    linked = me(client, make_token(sub="email|ada"))
    assert linked.status_code == 200, linked.text
    assert linked.json()["account_id"] == account_id
    assert linked.json()["display_name"] == "Ada Lovelace \U0001f680"
    assert stored(client, "ada@test.invalid") == [
        (account_id, "auth0|ada", "Ada Lovelace \U0001f680", "auth0|ada"),
        (account_id, "auth0|ada", "Ada Lovelace \U0001f680", "email|ada"),
    ]
    assert me(client, make_token(sub="email|ada")).json()["account_id"] == account_id
    assert asked == ["auth0|ada", "email|ada"]


def test_profiles_are_fitted_to_the_schema(mysql_live, monkeypatch) -> None:
    client, _ = mysql_live
    stub_userinfo(
        monkeypatch,
        {
            "auth0|long": {
                "email": "long@test.invalid",
                "email_verified": True,
                "name": "N" * 150,
            },
            "auth0|nameless": {"email": "nameless@test.invalid", "email_verified": True},
        },
    )

    # display_name is VARCHAR(100); a longer Auth0 name is cut, not refused.
    long = me(client, make_token(sub="auth0|long"))
    assert long.status_code == 200, long.text
    assert long.json()["display_name"] == "N" * 100
    # No name at all falls back to the email address.
    nameless = me(client, make_token(sub="auth0|nameless"))
    assert nameless.status_code == 200, nameless.text
    assert nameless.json()["display_name"] == "nameless@test.invalid"


def test_refused_sign_ins_store_nothing(mysql_live, monkeypatch) -> None:
    client, _ = mysql_live
    stub_userinfo(
        monkeypatch,
        {
            "auth0|unverified": {
                "email": "unverified@test.invalid",
                "email_verified": False,
                "name": "Unverified",
            },
            "auth0|no-email": {"email_verified": True, "name": "No Email"},
            "auth0|down": APIError(
                502, "profile_unavailable", "Could not load your profile from Auth0"
            ),
            # Someone else's address, unverified, must not be linked to them.
            "auth0|squatter": {
                "email": "alice@test.invalid",
                "email_verified": False,
                "name": "Not Alice",
            },
        },
    )
    with client.app.state.database.engine.connect() as conn:
        before = conn.execute(
            text(
                "SELECT (SELECT COUNT(*) FROM account), "
                "(SELECT COUNT(*) FROM account_identity)"
            )
        ).one()

    for sub, status, code in (
        ("auth0|unverified", 403, "email_not_verified"),
        ("auth0|no-email", 403, "email_not_verified"),
        ("auth0|squatter", 403, "email_not_verified"),
        ("auth0|down", 502, "profile_unavailable"),
    ):
        refused = me(client, make_token(sub=sub))
        assert (refused.status_code, error_code(refused)) == (status, code), sub

    for token, code in (
        (None, "missing_token"),
        ("not-a-jwt", "invalid_token"),
        (make_token(sub="test|alice", exp_offset=-3600), "invalid_token"),
        (make_token(sub="test|alice", audience="someone-else"), "invalid_token"),
        (make_token(sub="test|alice", issuer="https://evil.example/"), "invalid_token"),
    ):
        refused = me(client, token)
        assert (refused.status_code, error_code(refused)) == (401, code)

    with client.app.state.database.engine.connect() as conn:
        after = conn.execute(
            text(
                "SELECT (SELECT COUNT(*) FROM account), "
                "(SELECT COUNT(*) FROM account_identity)"
            )
        ).one()
    assert tuple(after) == tuple(before)


def test_roles_and_deactivation_come_from_the_account_row(mysql_live) -> None:
    client, people = mysql_live
    with client.app.state.database.engine.begin() as conn:
        conn.execute(
            text("UPDATE account SET account_type = 'PROFESSOR' WHERE account_id = :id"),
            {"id": people["bob"].account_id},
        )
        conn.execute(
            text("UPDATE account SET is_active = FALSE WHERE account_id = :id"),
            {"id": people["alice"].account_id},
        )

    # Only ADMINISTRATOR is an admin in the MVP's two roles.
    assert client.get("/me", headers=bearer("faculty")).json()["role"] == "ADMIN"
    assert client.get("/me", headers=bearer("bob")).json()["role"] == "USER"

    # A deactivated account can still load /me, which is how the app knows
    # to show the deactivated screen, but nothing else.
    alice = client.get("/me", headers=bearer("alice"))
    assert alice.status_code == 200
    assert alice.json()["is_active"] is False
    for method, url, body in (
        ("GET", "/classes", None),
        ("POST", "/classes/join", {"code": "ABCD2345"}),
        ("POST", "/sessions/join", {"join_code": "123456"}),
    ):
        refused = client.request(method, url, json=body, headers=bearer("alice"))
        assert refused.status_code == 403, url
        assert error_code(refused) == "inactive_account"
    assert client.get("/classes", headers=bearer("bob")).status_code == 200


@pytest.mark.parametrize(
    "subs, identities",
    [
        # Two tabs finishing the same first sign-in at once.
        (["auth0|twin", "auth0|twin"], ["auth0|twin"]),
        # Two login methods for one email, both used for the first time.
        (["auth0|twin", "email|twin"], ["auth0|twin", "email|twin"]),
    ],
)
def test_simultaneous_first_logins_make_one_account(
    mysql_live, monkeypatch, subs, identities
) -> None:
    client, _ = mysql_live
    profile = {"email": "twin@test.invalid", "email_verified": True, "name": "Twin"}
    stub_userinfo(
        monkeypatch,
        {sub: profile for sub in subs},
        barrier=Barrier(len(subs)),
    )

    def sign_in(sub: str) -> int:
        with client.app.state.database.session_factory() as db:
            account = get_or_create_account(db, DOMAIN, sub, make_token(sub=sub))
            return account["account_id"]

    with ThreadPoolExecutor(max_workers=len(subs)) as executor:
        futures = [executor.submit(sign_in, sub) for sub in subs]
        account_ids = {future.result(timeout=15) for future in futures}

    assert len(account_ids) == 1
    rows = stored(client, "twin@test.invalid")
    assert {row[0] for row in rows} == account_ids
    assert sorted(row[3] for row in rows) == identities
