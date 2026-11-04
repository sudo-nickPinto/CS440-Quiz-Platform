import json
import unicodedata
import urllib.request

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.avatars import is_valid_avatar_key
from app.errors import APIError

COLUMNS = (
    "account_id, email, display_name, first_name, last_name, avatar_key, "
    "account_type, is_active"
)
NAME_MAX_LENGTH = 50
DISPLAY_NAME_MAX_LENGTH = 100


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
    # A person can have several logins (e.g. older Google logins plus email/password); each sub is
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


def get_or_create_account(db: Session, domain: str, sub: str, token: str) -> dict:
    """Return the account for this Auth0 login, creating or linking it on first use."""
    account = _by_sub(db, sub)
    if account:
        return account

    profile = _fetch_profile(domain, token)
    email = profile.get("email")
    # Linking trusts the email, so it must be verified: otherwise anyone could
    # sign up with someone else's address and be attached to their account.
    if not email or not profile.get("email_verified"):
        raise APIError(403, "email_not_verified", "Please verify your email address, then log in again.")
    name = (profile.get("name") or email)[:100]

    try:
        existing = _by_email(db, email)
        if existing:
            _add_identity(db, sub, existing["account_id"])
        else:
            result = db.execute(
                text("INSERT INTO account (auth0_sub, email, display_name) VALUES (:sub, :email, :name)"),
                {"sub": sub, "email": email, "name": name},
            )
            _add_identity(db, sub, result.lastrowid)
        db.commit()
    except IntegrityError:
        # A parallel first request for this login or email got there first.
        db.rollback()
        account = _by_sub(db, sub)
        if account:
            return account
        existing = _by_email(db, email)
        if existing:
            try:
                _add_identity(db, sub, existing["account_id"])
                db.commit()
            except IntegrityError:
                db.rollback()
        account = _by_sub(db, sub)
        if account:
            return account
        raise
    return _by_sub(db, sub)


def clean_name(value: str, label: str) -> str:
    """Trim a first or last name and check it is printable and 1-50 characters."""
    name = " ".join(value.split())
    if not name:
        raise APIError(422, "invalid_profile", f"Please enter your {label}.")
    if len(name) > NAME_MAX_LENGTH:
        raise APIError(
            422,
            "invalid_profile",
            f"Your {label} can be at most {NAME_MAX_LENGTH} characters.",
        )
    if any(unicodedata.category(char) == "Cc" for char in name):
        raise APIError(422, "invalid_profile", f"Your {label} contains invalid characters.")
    return name


def update_profile(
    db: Session,
    account_id: int,
    first_name: str,
    last_name: str,
    avatar_key: str | None,
) -> dict:
    """Save the profile and make display_name "first last", which every screen shows."""
    first = clean_name(first_name, "first name")
    last = clean_name(last_name, "last name")
    if avatar_key is not None and not is_valid_avatar_key(avatar_key):
        raise APIError(422, "invalid_profile", "Please pick one of the avatars.")
    db.execute(
        text(
            "UPDATE account SET first_name = :first, last_name = :last, "
            "avatar_key = :avatar, display_name = :display WHERE account_id = :id"
        ),
        {
            "first": first,
            "last": last,
            "avatar": avatar_key,
            "display": f"{first} {last}"[:DISPLAY_NAME_MAX_LENGTH],
            "id": account_id,
        },
    )
    db.commit()
    row = db.execute(
        text(f"SELECT {COLUMNS} FROM account WHERE account_id = :id"), {"id": account_id}
    ).mappings().one()
    return dict(row)
