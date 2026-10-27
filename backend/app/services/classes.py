from collections import defaultdict, deque
from datetime import UTC, datetime
import secrets
from threading import Lock
from time import monotonic

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.classes import (
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    MembershipStatus,
)
from app.schemas.classes import ClassCreate, ClassJoin, ClassResponse, ClassUpdate
from app.services.class_authorization import (
    ClassAccess,
    require_class_member,
    require_class_organizer,
)
from app.services.class_memberships import _protect_last_organizer

CLASS_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CLASS_CODE_LENGTH = 8
CLASS_CODE_ATTEMPTS = 20
# Class codes are 8 characters from a 31-letter alphabet, so guessing is
# already impractical; this just stops one account hammering the endpoint.
JOIN_ATTEMPTS_PER_WINDOW = 10
JOIN_WINDOW_SECONDS = 60.0

# Per-process, so each worker keeps its own window. Good enough for a limit
# whose job is slowing scripts down, not exact accounting.
_join_attempts: dict[int, deque[float]] = defaultdict(deque)
_join_attempts_lock = Lock()


def _utc_now_milliseconds() -> datetime:
    now = datetime.now(UTC).replace(tzinfo=None)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


def generate_class_code() -> str:
    return "".join(
        secrets.choice(CLASS_CODE_ALPHABET) for _ in range(CLASS_CODE_LENGTH)
    )


def _generate_unique_code(
    db: Session,
    *,
    error_code: str,
    error_message: str,
) -> str:
    try:
        for _ in range(CLASS_CODE_ATTEMPTS):
            code = generate_class_code()
            existing_class_id = db.scalar(
                select(Class.class_id).where(Class.join_code == code)
            )
            if existing_class_id is None:
                return code
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, error_code, error_message) from exc
    raise APIError(500, error_code, error_message)


def _format_join_code(code: str | None) -> str | None:
    if code is None:
        return None
    return f"{code[:4]}-{code[4:]}"


def _to_response(
    class_: Class,
    membership: ClassMembership | None,
    *,
    is_global_admin: bool,
) -> ClassResponse:
    active_membership = (
        membership
        if membership is not None and membership.status == MembershipStatus.ACTIVE
        else None
    )
    may_view_code = is_global_admin or (
        active_membership is not None
        and active_membership.role == ClassRole.ORGANIZER
    )
    return ClassResponse(
        class_id=class_.class_id,
        name=class_.name,
        created_by_id=class_.created_by_id,
        join_code=_format_join_code(class_.join_code) if may_view_code else None,
        joining_open=class_.joining_open,
        archived_at=class_.archived_at,
        created_at=class_.created_at,
        updated_at=class_.updated_at,
        current_role=(
            None
            if is_global_admin or active_membership is None
            else active_membership.role
        ),
        membership_status=(
            None if is_global_admin or membership is None else membership.status
        ),
    )


def _access_response(access: ClassAccess) -> ClassResponse:
    return _to_response(
        access.class_,
        access.membership,
        is_global_admin=access.is_global_admin,
    )


def _commit(db: Session, code: str, message: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, code, message) from exc


def create_class(
    db: Session,
    account: CurrentAccount,
    payload: ClassCreate,
) -> ClassResponse:
    code = _generate_unique_code(
        db,
        error_code="class_create_failed",
        error_message="Could not create the class.",
    )
    membership = ClassMembership(
        account_id=account.account_id,
        role=ClassRole.ORGANIZER,
        status=MembershipStatus.ACTIVE,
        joined_via=JoinedVia.CREATOR,
    )
    class_ = Class(
        name=payload.name,
        created_by_id=account.account_id,
        join_code=code,
        memberships=[membership],
    )
    db.add(class_)
    _commit(db, "class_create_failed", "Could not create the class.")
    return _to_response(class_, membership, is_global_admin=account.is_admin)


def list_classes(
    db: Session,
    account: CurrentAccount,
) -> list[ClassResponse]:
    ordering = (Class.created_at.desc(), Class.class_id.desc())
    if account.is_admin:
        classes = db.scalars(select(Class).order_by(*ordering)).all()
        return [
            _to_response(class_, None, is_global_admin=True) for class_ in classes
        ]

    rows = db.execute(
        select(Class, ClassMembership)
        .join(ClassMembership, ClassMembership.class_id == Class.class_id)
        .where(
            ClassMembership.account_id == account.account_id,
            ClassMembership.status.in_(
                (MembershipStatus.ACTIVE, MembershipStatus.INVITED)
            ),
        )
        .order_by(*ordering)
    ).all()
    return [
        _to_response(class_, membership, is_global_admin=False)
        for class_, membership in rows
    ]


def get_class(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassResponse:
    return _access_response(require_class_member(db, account, class_id))


def update_class(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    payload: ClassUpdate,
) -> ClassResponse:
    access = require_class_organizer(db, account, class_id)
    class_ = access.class_
    if class_.archived_at is not None and payload.joining_open is True:
        raise APIError(409, "class_archived", "An archived class cannot be reopened.")

    if "name" in payload.model_fields_set:
        class_.name = payload.name
    if "joining_open" in payload.model_fields_set:
        class_.joining_open = payload.joining_open
    _commit(db, "class_update_failed", "Could not update the class.")
    return _access_response(access)


def rotate_class_code(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassResponse:
    access = require_class_organizer(db, account, class_id)
    class_ = access.class_
    if class_.archived_at is not None:
        raise APIError(
            409,
            "class_archived",
            "An archived class cannot receive a new code.",
        )

    class_.join_code = _generate_unique_code(
        db,
        error_code="class_code_update_failed",
        error_message="Could not update the class code.",
    )
    class_.joining_open = True
    _commit(
        db,
        "class_code_update_failed",
        "Could not update the class code.",
    )
    return _access_response(access)


def archive_class(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassResponse:
    access = require_class_organizer(db, account, class_id)
    class_ = access.class_
    if class_.archived_at is not None:
        return _access_response(access)

    class_.archived_at = _utc_now_milliseconds()
    class_.joining_open = False
    class_.join_code = None
    _commit(db, "class_archive_failed", "Could not archive the class.")
    return _access_response(access)


def _check_join_rate(account_id: int) -> None:
    now = monotonic()
    with _join_attempts_lock:
        attempts = _join_attempts[account_id]
        while attempts and now - attempts[0] > JOIN_WINDOW_SECONDS:
            attempts.popleft()
        if len(attempts) >= JOIN_ATTEMPTS_PER_WINDOW:
            raise APIError(
                429,
                "too_many_join_attempts",
                "Too many class codes tried. Wait a minute and try again.",
            )
        attempts.append(now)


def join_class(
    db: Session,
    account: CurrentAccount,
    payload: ClassJoin,
) -> ClassResponse:
    _check_join_rate(account.account_id)
    class_ = db.scalar(
        select(Class).where(Class.join_code == payload.code).with_for_update()
    )
    if class_ is None:
        raise APIError(404, "class_code_not_found", "No class has that code.")
    if class_.archived_at is not None or not class_.joining_open:
        raise APIError(
            403, "class_joining_closed", "This class isn't accepting new members."
        )

    membership = db.scalar(
        select(ClassMembership)
        .where(
            ClassMembership.class_id == class_.class_id,
            ClassMembership.account_id == account.account_id,
        )
        .with_for_update()
    )
    if membership is None:
        membership = ClassMembership(
            class_id=class_.class_id,
            account_id=account.account_id,
            role=ClassRole.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_via=JoinedVia.CODE,
        )
        db.add(membership)
    elif membership.status == MembershipStatus.ACTIVE:
        raise APIError(
            409, "already_class_member", "You're already in this class."
        )
    elif membership.status == MembershipStatus.REMOVED:
        # Only an organizer can undo a removal, by inviting them again.
        raise APIError(
            403,
            "class_member_removed",
            "You were removed from this class. Ask an organizer to invite you.",
        )
    else:
        # A pending invite or a past membership; the code works for both.
        membership.status = MembershipStatus.ACTIVE
        membership.role = ClassRole.MEMBER
        membership.joined_via = JoinedVia.CODE
        membership.decided_by_id = account.account_id
        membership.decided_at = _utc_now_milliseconds()

    try:
        db.commit()
    except IntegrityError as exc:
        # Two join requests raced; the other one already added the row.
        db.rollback()
        raise APIError(
            409, "already_class_member", "You're already in this class."
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, "class_join_failed", "Could not join the class.") from exc
    return _to_response(class_, membership, is_global_admin=False)


def leave_class(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> None:
    access = require_class_member(db, account, class_id)
    membership = access.membership
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        # An Admin browsing a class they never joined has nothing to leave.
        raise APIError(409, "not_class_member", "You aren't a member of this class.")

    _protect_last_organizer(db, membership)
    membership.status = MembershipStatus.LEFT
    membership.decided_by_id = account.account_id
    membership.decided_at = _utc_now_milliseconds()
    _commit(db, "class_leave_failed", "Could not leave the class.")
