import json
import urllib.request

import pymysql
from fastapi import HTTPException

from app.auth import AUTH0_DOMAIN

COLUMNS = "account_id, email, display_name, account_type"


def _fetch_profile(token: str) -> dict:
    # The access token only carries `sub`, so ask Auth0 for email and name.
    req = urllib.request.Request(
        f"https://{AUTH0_DOMAIN}/userinfo", headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.load(res)
    except OSError:
        raise HTTPException(502, "Could not load your profile from Auth0")


def _by_sub(db, sub):
    with db.cursor() as cur:
        cur.execute(f"SELECT {COLUMNS} FROM account WHERE auth0_sub = %s", (sub,))
        return cur.fetchone()


def get_or_create_account(db, sub: str, token: str) -> dict:
    """Return the account for this Auth0 user, creating it on first login."""
    account = _by_sub(db, sub)
    if account:
        return account

    profile = _fetch_profile(token)
    email = profile.get("email")
    if not email or not profile.get("email_verified"):
        raise HTTPException(403, "Please verify your email address, then log in again.")
    name = (profile.get("name") or email)[:100]

    try:
        with db.cursor() as cur:
            cur.execute(
                "INSERT INTO account (auth0_sub, email, display_name) VALUES (%s, %s, %s)",
                (sub, email, name),
            )
    except pymysql.err.IntegrityError:
        # Either a parallel request created this row, or the email belongs to
        # an account that signed in with a different method (e.g. Google).
        account = _by_sub(db, sub)
        if account:
            return account
        raise HTTPException(
            409, "This email is already registered with a different login method. "
            "Log in the way you first signed up."
        )
    return _by_sub(db, sub)
