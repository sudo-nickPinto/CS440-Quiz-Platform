import json
import urllib.request

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import APIError

COLUMNS = "account_id, email, display_name, account_type"


def _fetch_profile(domain: str, token: str) -> dict:
    # The access token only carries `sub`, so ask Auth0 for email and name.
    req = urllib.request.Request(
        f"https://{domain}/userinfo", headers={"Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            return json.load(res)
    except OSError:
        raise APIError(502, "profile_unavailable", "Could not load your profile from Auth0")


def _by_sub(db: Session, sub: str) -> dict | None:
    row = db.execute(
        text(f"SELECT {COLUMNS} FROM account WHERE auth0_sub = :sub"), {"sub": sub}
    ).mappings().first()
    return dict(row) if row else None


def get_or_create_account(db: Session, domain: str, sub: str, token: str) -> dict:
    """Return the account for this Auth0 user, creating it on first login."""
    account = _by_sub(db, sub)
    if account:
        return account

    profile = _fetch_profile(domain, token)
    email = profile.get("email")
    if not email or not profile.get("email_verified"):
        raise APIError(403, "email_not_verified", "Please verify your email address, then log in again.")
    name = (profile.get("name") or email)[:100]

    try:
        db.execute(
            text("INSERT INTO account (auth0_sub, email, display_name) VALUES (:sub, :email, :name)"),
            {"sub": sub, "email": email, "name": name},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        # Either a parallel request created this row, or the email belongs to
        # an account that signed in with a different method (e.g. Google).
        account = _by_sub(db, sub)
        if account:
            return account
        raise APIError(
            409,
            "email_already_registered",
            "This email is already registered with a different login method. "
            "Log in the way you first signed up.",
        )
    return _by_sub(db, sub)
