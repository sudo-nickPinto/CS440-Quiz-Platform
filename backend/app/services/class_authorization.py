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
    membership: ClassMembership
    is_faculty: bool

    @property
    def is_organizer(self) -> bool:
        return (
            self.is_faculty
            and self.membership.status == MembershipStatus.ACTIVE
            and self.membership.role == ClassRole.ORGANIZER
        )


def require_active_faculty(account: CurrentAccount) -> None:
    if not account.is_active:
        raise APIError(
            403,
            "inactive_account",
            "This account is inactive.",
        )

    if not account.is_admin:
        raise APIError(
            403,
            "faculty_required",
            "Only active faculty accounts can create classes.",
        )


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
    if not account.is_active:
        raise APIError(404, "class_not_found", "Class not found.")

    class_ = get_class(db, class_id)
    membership = get_class_membership(db, class_id, account.account_id)

    if membership is None or membership.status != MembershipStatus.ACTIVE:
        raise APIError(404, "class_not_found", "Class not found.")

    return ClassAccess(
        class_=class_,
        membership=membership,
        is_faculty=account.is_admin,
    )


def require_class_organizer(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassAccess:
    access = require_class_member(db, account, class_id)

    if not access.is_organizer:
        raise APIError(
            403,
            "not_class_organizer",
            "Only an active faculty organizer can perform this action.",
        )

    return access


def require_class_host(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassAccess:
    access = require_class_organizer(db, account, class_id)

    if access.class_.archived_at is not None:
        raise APIError(
            409,
            "class_archived",
            "An archived class cannot start new sessions.",
        )

    return access
