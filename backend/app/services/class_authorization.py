from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.classes import (
    Class,
    ClassMembership,
    ClassRole,
    MembershipStatus,
)


@dataclass(frozen=True, slots=True)
class ClassAccess:
    class_: Class
    membership: ClassMembership | None
    is_global_admin: bool


def get_class(db: Session, class_id: int) -> Class:
    class_ = db.get(Class, class_id)
    if class_ is None:
        raise APIError(404, "class_not_found", "Class not found.")
    return class_


def get_class_membership(
    db: Session,
    class_id: int,
    account_id: int,
) -> ClassMembership | None:
    return db.scalar(
        select(ClassMembership).where(
            ClassMembership.class_id == class_id,
            ClassMembership.account_id == account_id,
        )
    )


def require_class_member(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassAccess:
    class_ = get_class(db, class_id)
    membership = get_class_membership(db, class_id, account.account_id)
    access = ClassAccess(
        class_=class_,
        membership=membership,
        is_global_admin=account.is_admin,
    )

    if account.is_admin:
        return access
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        raise APIError(404, "class_not_found", "Class not found.")
    return access


def require_class_organizer(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassAccess:
    access = require_class_member(db, account, class_id)
    if access.is_global_admin:
        return access
    if access.membership is None or access.membership.role != ClassRole.ORGANIZER:
        raise APIError(
            403,
            "not_class_organizer",
            "Only a class organizer or global Admin can perform this action.",
        )
    return access


def require_class_host(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassAccess:
    """Allow starting a live session for a class: an active organizer or a
    global Admin, and the class must not be archived.

    This only checks the class. Session creation still has to check that the
    account is the quiz's author.
    """
    access = require_class_organizer(db, account, class_id)
    if access.class_.archived_at is not None:
        raise APIError(
            409,
            "class_archived",
            "An archived class cannot start new sessions.",
        )
    return access
