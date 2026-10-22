from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.account import Account
from app.models.classes import (
    Class,
    ClassRole,
    ClassMembership,
    JoinedVia,
    MembershipStatus,
)
from app.schemas.class_membership import (
    ClassInviteCreate,
    ClassMemberResponse,
    ClassMemberUpdate,
)


def _load_class(db: Session, class_id: int, *, lock: bool = False) -> Class:
    statement = select(Class).where(Class.class_id == class_id)
    if lock:
        statement = statement.with_for_update()
    class_ = db.scalar(statement)
    if class_ is None:
        raise APIError(404, "class_not_found", "Class not found.")
    return class_


def _membership_statement(class_id: int, account_id: int):
    return (
        select(ClassMembership)
        .where(
            ClassMembership.class_id == class_id,
            ClassMembership.account_id == account_id,
        )
        .options(joinedload(ClassMembership.account))
    )


def _load_membership(
    db: Session, class_id: int, account_id: int, *, lock: bool = False
) -> ClassMembership:
    statement = _membership_statement(class_id, account_id)
    if lock:
        statement = statement.with_for_update()
    membership = db.scalar(statement)
    if membership is None:
        raise APIError(404, "class_member_not_found", "Class member not found.")
    return membership


def _require_class_organizer(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    *,
    lock_class: bool = False,
) -> None:
    # Every mutation takes this lock before reading actor or target
    # memberships. Serializing roster changes per class prevents two organizers
    # from locking each other's rows in opposite order.
    _load_class(db, class_id, lock=lock_class)
    if account.is_admin:
        return
    membership = db.scalar(_membership_statement(class_id, account.account_id))
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        # Match an unknown class so outsiders and removed members cannot use
        # roster endpoints to discover that a class ID exists.
        raise APIError(404, "class_not_found", "Class not found.")
    if membership.role != ClassRole.ORGANIZER:
        raise APIError(
            403,
            "not_class_organizer",
            "Only a class organizer or global Admin can perform this action.",
        )


def _to_response(membership: ClassMembership) -> ClassMemberResponse:
    return ClassMemberResponse(
        membership_id=membership.membership_id,
        class_id=membership.class_id,
        account_id=membership.account_id,
        email=membership.account.email,
        display_name=membership.account.display_name,
        role=membership.role,
        status=membership.status,
        created_at=membership.created_at,
        updated_at=membership.updated_at,
    )


def _commit(db: Session, code: str, message: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, code, message) from exc


def _lock_active_organizers(db: Session, class_id: int) -> list[ClassMembership]:
    return list(
        db.scalars(
            select(ClassMembership)
            .where(
                ClassMembership.class_id == class_id,
                ClassMembership.status == MembershipStatus.ACTIVE,
                ClassMembership.role == ClassRole.ORGANIZER,
            )
            .with_for_update()
        ).all()
    )


def _protect_last_organizer(db: Session, membership: ClassMembership) -> None:
    if not (
        membership.status == MembershipStatus.ACTIVE
        and membership.role == ClassRole.ORGANIZER
    ):
        return
    if len(_lock_active_organizers(db, membership.class_id)) <= 1:
        raise APIError(
            409,
            "last_organizer",
            "The last active class organizer cannot be removed or demoted.",
        )


def list_class_members(
    db: Session, account: CurrentAccount, class_id: int
) -> list[ClassMemberResponse]:
    _require_class_organizer(db, account, class_id)
    memberships = db.scalars(
        select(ClassMembership)
        .join(Account, Account.account_id == ClassMembership.account_id)
        .where(
            ClassMembership.class_id == class_id,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
        .options(joinedload(ClassMembership.account))
        .order_by(Account.display_name, ClassMembership.account_id)
    ).all()
    return [_to_response(membership) for membership in memberships]


def get_class_member(
    db: Session, account: CurrentAccount, class_id: int, account_id: int
) -> ClassMemberResponse:
    _require_class_organizer(db, account, class_id)
    return _to_response(_load_membership(db, class_id, account_id))


def create_class_invite(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    payload: ClassInviteCreate,
) -> ClassMemberResponse:
    _require_class_organizer(db, account, class_id, lock_class=True)
    target = db.scalar(
        select(Account).where(func.lower(Account.email) == payload.email)
    )
    if target is None:
        raise APIError(404, "account_not_found", "No account has that email address.")

    membership = db.scalar(
        _membership_statement(class_id, target.account_id).with_for_update()
    )
    if membership and membership.status == MembershipStatus.ACTIVE:
        raise APIError(
            409,
            "already_class_member",
            "That account is already an active class member.",
        )
    if membership and membership.status == MembershipStatus.INVITED:
        raise APIError(409, "invite_already_exists", "That account is already invited.")

    now = datetime.now(UTC).replace(tzinfo=None)
    if membership is None:
        membership = ClassMembership(
            class_id=class_id,
            account_id=target.account_id,
            role=ClassRole.MEMBER,
            status=MembershipStatus.INVITED,
            joined_via=JoinedVia.INVITE,
            invited_by_id=account.account_id,
            decided_by_id=account.account_id,
            decided_at=now,
        )
        db.add(membership)
    else:
        membership.role = ClassRole.MEMBER
        membership.status = MembershipStatus.INVITED
        membership.joined_via = JoinedVia.INVITE
        membership.invited_by_id = account.account_id
        membership.decided_by_id = account.account_id
        membership.decided_at = now

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise APIError(
            409,
            "invite_already_exists",
            "That account already has a membership or invitation.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500, "class_invite_create_failed", "Could not create the class invite."
        ) from exc

    return _to_response(_load_membership(db, class_id, target.account_id))


def cancel_class_invite(
    db: Session, account: CurrentAccount, class_id: int, account_id: int
) -> None:
    _require_class_organizer(db, account, class_id, lock_class=True)
    membership = db.scalar(
        _membership_statement(class_id, account_id).with_for_update()
    )
    if membership is None or membership.status != MembershipStatus.INVITED:
        raise APIError(404, "invite_not_found", "Class invite not found.")

    membership.status = MembershipStatus.REMOVED
    membership.decided_by_id = account.account_id
    membership.decided_at = datetime.now(UTC).replace(tzinfo=None)
    _commit(db, "class_invite_cancel_failed", "Could not cancel the class invite.")


def accept_class_invite(
    db: Session, account: CurrentAccount, class_id: int
) -> ClassMemberResponse:
    _load_class(db, class_id)
    result = db.execute(
        update(ClassMembership)
        .where(
            ClassMembership.class_id == class_id,
            ClassMembership.account_id == account.account_id,
            ClassMembership.status == MembershipStatus.INVITED,
        )
        .values(
            status=MembershipStatus.ACTIVE,
            role=ClassRole.MEMBER,
            joined_via=JoinedVia.INVITE,
            decided_by_id=account.account_id,
            decided_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise APIError(404, "invite_not_found", "Class invite not found.")
    _commit(db, "class_invite_accept_failed", "Could not accept the class invite.")
    return _to_response(_load_membership(db, class_id, account.account_id))


def decline_class_invite(db: Session, account: CurrentAccount, class_id: int) -> None:
    _load_class(db, class_id)
    result = db.execute(
        update(ClassMembership)
        .where(
            ClassMembership.class_id == class_id,
            ClassMembership.account_id == account.account_id,
            ClassMembership.status == MembershipStatus.INVITED,
        )
        .values(
            status=MembershipStatus.LEFT,
            decided_by_id=account.account_id,
            decided_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise APIError(404, "invite_not_found", "Class invite not found.")
    _commit(db, "class_invite_decline_failed", "Could not decline the class invite.")


def update_class_member(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    account_id: int,
    payload: ClassMemberUpdate,
) -> ClassMemberResponse:
    _require_class_organizer(db, account, class_id, lock_class=True)
    membership = _load_membership(db, class_id, account_id, lock=True)
    if membership.status != MembershipStatus.ACTIVE:
        raise APIError(409, "class_member_not_active", "Class member is not active.")

    new_role = payload.role
    if (
        membership.role == ClassRole.ORGANIZER
        and new_role == ClassRole.MEMBER
    ):
        _protect_last_organizer(db, membership)

    if membership.role != new_role:
        membership.role = new_role
        membership.decided_by_id = account.account_id
        membership.decided_at = datetime.now(UTC).replace(tzinfo=None)
        _commit(
            db,
            "class_member_update_failed",
            "Could not update the class member.",
        )

    return _to_response(_load_membership(db, class_id, account_id))


def remove_class_member(
    db: Session, account: CurrentAccount, class_id: int, account_id: int
) -> None:
    _require_class_organizer(db, account, class_id, lock_class=True)
    membership = _load_membership(db, class_id, account_id, lock=True)
    if membership.status != MembershipStatus.ACTIVE:
        raise APIError(409, "class_member_not_active", "Class member is not active.")

    _protect_last_organizer(db, membership)
    membership.status = MembershipStatus.REMOVED
    membership.decided_by_id = account.account_id
    membership.decided_at = datetime.now(UTC).replace(tzinfo=None)
    _commit(
        db,
        "class_member_remove_failed",
        "Could not remove the class member.",
    )
