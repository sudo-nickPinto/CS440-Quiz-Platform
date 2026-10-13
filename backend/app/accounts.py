import json
import urllib.request

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import APIError

COLUMNS = "account_id, email, display_name, account_type, is_active"


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
    # A person can have several logins (Google, email/password); each sub is
    # a row in account_identity pointing at the one account.
    row = db.execute(
        text(
            f"SELECT {COLUMNS} FROM account WHERE account_id = "
            "(SELECT account_id FROM account_identity WHERE auth0_sub = :sub)"
        ),
        {"sub": sub},
    ).mappings().first()
    return dict(row) if row else None


def _by_email(db: Session, email: str) -> dict | None:
    row = db.execute(
        text(f"SELECT {COLUMNS} FROM account WHERE email = :email"), {"email": email}
    ).mappings().first()
    return dict(row) if row else None


def _add_identity(db: Session, sub: str, account_id: int) -> None:
    db.execute(
        text("INSERT INTO account_identity (auth0_sub, account_id) VALUES (:sub, :id)"),
        {"sub": sub, "id": account_id},
    )


def _link_or_create(db: Session, sub: str, email: str, name: str, verified: bool) -> None:
    existing = _by_email(db, email)
    if existing is None:
        # A verified email is active right away. An unverified
        # email/password signup stays inactive until someone approves it.
        result = db.execute(
            text(
                "INSERT INTO account (auth0_sub, email, display_name, is_active) "
                "VALUES (:sub, :email, :name, :active)"
            ),
            {"sub": sub, "email": email, "name": name, "active": verified},
        )
        _add_identity(db, sub, result.lastrowid)
        return
    # Linking trusts the email, so only a verified one may join an account, and
    # never a pending one: it may have been created by someone else using it.
    if not verified:
        raise APIError(
            409,
            "email_in_use",
            "An account with this email already exists. Log in the way you did before.",
        )
    if not existing["is_active"]:
        raise APIError(
            409,
            "account_pending",
            "An account with this email is waiting for approval. Ask to have it approved or rejected.",
        )
    _add_identity(db, sub, existing["account_id"])


def get_or_create_account(db: Session, domain: str, sub: str, token: str) -> dict:
    """Return the account for this Auth0 login, creating or linking it on first use."""
    account = _by_sub(db, sub)
    if account:
        return account

    profile = _fetch_profile(domain, token)
    email = profile.get("email")
    if not email:
        raise APIError(403, "email_missing", "Your login has no email address. Use another login method.")
    verified = bool(profile.get("email_verified"))
    name = (profile.get("name") or email)[:100]

    try:
        _link_or_create(db, sub, email, name, verified)
        db.commit()
    except IntegrityError:
        # A parallel first request for this login or email got there first.
        db.rollback()
        account = _by_sub(db, sub)
        if account:
            return account
        try:
            _link_or_create(db, sub, email, name, verified)
            db.commit()
        except IntegrityError:
            db.rollback()
        account = _by_sub(db, sub)
        if account:
            return account
        raise
    return _by_sub(db, sub)
