"""Faculty granting and removing faculty status in the app (issue #116).

Faculty status is account.account_type = 'ADMINISTRATOR'. It lets someone
create classes and be made an organizer; it never gives access to classes
they aren't an organizer of. The rules:

- Only active faculty can see, grant, or remove faculty status.
- Faculty status goes to an existing account, found by its exact email
  (case-insensitive). The person has to sign in once so the account exists.
- Faculty can remove anyone else's faculty status, never their own, so at
  least one faculty account always remains.
- Faculty status can't be removed from the last usable organizer of a class:
  organizer powers need faculty status, and nobody else could manage it.
- Every change is recorded in faculty_access_event.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.account import (
    FACULTY_ACCOUNT_TYPE,
    Account,
    FacultyAccessAction,
    FacultyAccessEvent,
)
from app.models.classes import Class, ClassMembership, ClassRole, MembershipStatus
from app.schemas.faculty import (
    FacultyAccessHistoryItem,
    FacultyAccessPage,
    FacultyMember,
)
from app.services.class_memberships import _lock_active_organizers

HISTORY_LIMIT = 50


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _require_faculty(account: CurrentAccount) -> None:
    if not account.is_admin:
        raise APIError(
            403,
            "faculty_required",
            "Only faculty can manage faculty access.",
        )


def _latest_grants(db: Session, account_ids: list[int]) -> dict[int, tuple]:
    """account_id -> (granted_at, granted_by_name) of the newest grant."""
    if not account_ids:
        return {}
    actor = aliased(Account)
    rows = db.execute(
        select(
            FacultyAccessEvent.account_id,
            FacultyAccessEvent.occurred_at,
            actor.display_name,
        )
        .join(actor, actor.account_id == FacultyAccessEvent.actor_id)
        .where(
            FacultyAccessEvent.account_id.in_(account_ids),
            FacultyAccessEvent.action == FacultyAccessAction.GRANTED,
        )
        .order_by(FacultyAccessEvent.occurred_at, FacultyAccessEvent.event_id)
    ).all()
    latest: dict[int, tuple] = {}
    for account_id, occurred_at, actor_name in rows:
        latest[account_id] = (occurred_at, actor_name)  # later rows win
    return latest


def _member(account: Account, me: int, grant: tuple | None) -> FacultyMember:
    granted_at, granted_by = grant or (None, None)
    return FacultyMember(
        account_id=account.account_id,
        display_name=account.display_name,
        email=account.email,
        is_me=account.account_id == me,
        granted_at=_utc(granted_at),
        granted_by_name=granted_by,
    )


def list_faculty_access(db: Session, account: CurrentAccount) -> FacultyAccessPage:
    _require_faculty(account)

    faculty = db.scalars(
        select(Account)
        .where(
            Account.account_type == FACULTY_ACCOUNT_TYPE,
            Account.is_active.is_(True),
        )
        .order_by(func.lower(Account.display_name), Account.account_id)
    ).all()
    grants = _latest_grants(db, [person.account_id for person in faculty])

    subject = aliased(Account)
    actor = aliased(Account)
    history_rows = db.execute(
        select(FacultyAccessEvent, subject, actor.display_name)
        .join(subject, subject.account_id == FacultyAccessEvent.account_id)
        .join(actor, actor.account_id == FacultyAccessEvent.actor_id)
        .order_by(
            FacultyAccessEvent.occurred_at.desc(),
            FacultyAccessEvent.event_id.desc(),
        )
        .limit(HISTORY_LIMIT)
    ).all()

    return FacultyAccessPage(
        faculty=[
            _member(person, account.account_id, grants.get(person.account_id))
            for person in faculty
        ],
        history=[
            FacultyAccessHistoryItem(
                event_id=event.event_id,
                action=event.action,
                account_id=person.account_id,
                account_name=person.display_name,
                account_email=person.email,
                actor_name=actor_name,
                occurred_at=_utc(event.occurred_at),
            )
            for event, person, actor_name in history_rows
        ],
    )


def _lock_accounts(db: Session, *account_ids: int) -> dict[int, Account]:
    """Lock the rows in id order so two changes can't deadlock or interleave."""
    rows = db.scalars(
        select(Account)
        .where(Account.account_id.in_(sorted(set(account_ids))))
        .order_by(Account.account_id)
        .with_for_update()
    ).all()
    return {row.account_id: row for row in rows}


def _require_still_faculty(actor: Account | None) -> None:
    # Re-checked under the row lock: another faculty member may have removed
    # the caller's access after this request was authorized.
    if (
        actor is None
        or not actor.is_active
        or actor.account_type != FACULTY_ACCOUNT_TYPE
    ):
        raise APIError(
            403,
            "faculty_required",
            "Only faculty can manage faculty access.",
        )


def grant_faculty_access(
    db: Session, account: CurrentAccount, email: str
) -> FacultyMember:
    _require_faculty(account)
    wanted = email.strip().lower()
    if not wanted:
        raise APIError(422, "email_required", "Enter an email address.")

    target_id = db.scalar(
        select(Account.account_id).where(func.lower(Account.email) == wanted)
    )
    if target_id is None:
        raise APIError(
            404,
            "account_not_found",
            "No account uses that email. They need to sign in to the app "
            "once, then you can give them faculty access.",
        )

    try:
        locked = _lock_accounts(db, account.account_id, target_id)
        _require_still_faculty(locked.get(account.account_id))
        target = locked[target_id]
        if not target.is_active:
            raise APIError(
                409,
                "account_inactive",
                "That account is deactivated, so it can't be given faculty access.",
            )
        if target.account_type == FACULTY_ACCOUNT_TYPE:
            raise APIError(
                409,
                "already_faculty",
                f"{target.display_name} already has faculty access.",
            )

        occurred_at = _now()
        target.account_type = FACULTY_ACCOUNT_TYPE
        actor = locked[account.account_id]
        db.add(
            FacultyAccessEvent(
                account_id=target.account_id,
                action=FacultyAccessAction.GRANTED,
                actor_id=account.account_id,
                occurred_at=occurred_at,
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _member(
        target, account.account_id, (occurred_at, actor.display_name)
    )


def _classes_only_they_organize(db: Session, target: Account) -> list[Class]:
    """Classes where the target is the only usable organizer.

    Uses the same locked organizer count as removing, demoting or leaving
    (_lock_active_organizers), archived classes included, so two changes at
    once can't both pass and leave a class with no one to manage it.
    """
    classes = db.scalars(
        select(Class)
        .join(ClassMembership, ClassMembership.class_id == Class.class_id)
        .where(
            ClassMembership.account_id == target.account_id,
            ClassMembership.status == MembershipStatus.ACTIVE,
            ClassMembership.role == ClassRole.ORGANIZER,
        )
        .order_by(Class.class_id)
    ).all()
    stranded = []
    for class_ in classes:
        organizers = _lock_active_organizers(db, class_.class_id)
        if [o.account_id for o in organizers] == [target.account_id]:
            stranded.append(class_)
    return stranded


def _class_list(names: list[str]) -> str:
    quoted = [f"“{name}”" for name in names]
    if len(quoted) <= 2:
        return " and ".join(quoted)
    return ", ".join(quoted[:-1]) + f", and {quoted[-1]}"


def revoke_faculty_access(
    db: Session, account: CurrentAccount, account_id: int
) -> None:
    _require_faculty(account)
    if account_id == account.account_id:
        # Also guarantees at least one faculty account remains: the caller.
        raise APIError(
            409,
            "cannot_revoke_self",
            "You can't remove your own faculty access. Ask another faculty member.",
        )

    try:
        locked = _lock_accounts(db, account.account_id, account_id)
        _require_still_faculty(locked.get(account.account_id))
        target = locked.get(account_id)
        if target is None or target.account_type != FACULTY_ACCOUNT_TYPE:
            raise APIError(
                404,
                "faculty_not_found",
                "That person doesn't have faculty access.",
            )

        stranded = _classes_only_they_organize(db, target)
        if stranded:
            names = [class_.name for class_ in stranded]
            raise APIError(
                409,
                "last_organizer",
                f"{target.display_name} is the only organizer of "
                f"{_class_list(names)}. Make another faculty member an "
                "organizer there first, then remove their faculty access.",
                details={
                    "classes": [
                        {"class_id": class_.class_id, "name": class_.name}
                        for class_ in stranded
                    ]
                },
            )

        target.account_type = None
        db.add(
            FacultyAccessEvent(
                account_id=target.account_id,
                action=FacultyAccessAction.REVOKED,
                actor_id=account.account_id,
                occurred_at=_now(),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
