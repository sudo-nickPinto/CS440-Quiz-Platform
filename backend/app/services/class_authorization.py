from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.classes import (
    Class,
    ClassRole,
    ClassMembership,
    MembershipStatus,
)


@dataclass(frozen=True, slots=True)
class ClassAccess:
    class_: Class
    role: ClassRole | None
    is_global_admin: bool

    @property
    def is_organizer(self) -> bool:
        return self.is_global_admin or self.role == ClassRole.ORGANIZER


def get_class_access(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassAccess:
    """Return access without revealing inaccessible classes to nonmembers."""
    class_ = db.get(Class, class_id)
    if class_ is None:
        raise APIError(404, "class_not_found", "Class not found.")
    if account.is_admin:
        return ClassAccess(class_=class_, role=None, is_global_admin=True)

    membership = db.scalar(
        select(ClassMembership).where(
            ClassMembership.class_id == class_id,
            ClassMembership.account_id == account.account_id,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
    )
    if membership is None:
        # Use the same response as an unknown class so membership cannot be
        # inferred by probing IDs.
        raise APIError(404, "class_not_found", "Class not found.")

    return ClassAccess(class_=class_, role=membership.role, is_global_admin=False)


def require_class_member(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassAccess:
    return get_class_access(db, account, class_id)


def require_class_organizer(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    *,
    code: str = "not_class_organizer",
    message: str = "Only a class organizer or global Admin can access this data.",
) -> ClassAccess:
    access = get_class_access(db, account, class_id)
    if not access.is_organizer:
        raise APIError(403, code, message)
    return access
