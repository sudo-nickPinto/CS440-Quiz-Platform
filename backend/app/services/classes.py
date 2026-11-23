from collections import defaultdict, deque
from datetime import UTC, datetime
import secrets
from threading import Lock
from time import monotonic

from sqlalchemy import or_, select
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
from app.schemas.classes import (
    ClassCreate,
    ClassJoin,
    ClassResponse,
    ClassSemester,
    ClassSemesterCreate,
    ClassUpdate,
)
from app.services.class_authorization import (
    ClassAccess,
    require_active_faculty,
    require_class_member,
    require_class_organizer,
)
from app.models.account import Account, AccountRole, effective_role
from app.services.class_roster import find_roster_entry

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


def _family_links(
    db: Session,
    account: CurrentAccount,
    classes: list[Class],
) -> dict[int, list[ClassSemester]]:
    """The semesters of each course that the caller organizes.

    Switching semesters is an organizer tool, so students get an empty list,
    and an organizer never learns about a semester they aren't part of.
    One query for any number of classes.
    """
    if not classes or not account.is_admin:
        # Only faculty can be organizers (ClassAccess.is_organizer).
        return {}
    roots = {class_.parent_class_id or class_.class_id for class_ in classes}
    rows = db.scalars(
        select(Class)
        .join(ClassMembership, ClassMembership.class_id == Class.class_id)
        .where(
            Class.deleted_at.is_(None),
            or_(Class.class_id.in_(roots), Class.parent_class_id.in_(roots)),
            ClassMembership.account_id == account.account_id,
            ClassMembership.status == MembershipStatus.ACTIVE,
            ClassMembership.role == ClassRole.ORGANIZER,
        )
        .order_by(Class.created_at, Class.class_id)
    ).all()
    grouped: dict[int, list[ClassSemester]] = defaultdict(list)
    for row in rows:
        root = row.parent_class_id or row.class_id
        grouped[root].append(
            ClassSemester(
                class_id=row.class_id,
                semester=row.semester,
                archived=row.archived_at is not None,
            )
        )
    return {
        class_.class_id: grouped.get(class_.parent_class_id or class_.class_id, [])
        for class_ in classes
    }


def _to_response(
    class_: Class,
    membership: ClassMembership | None,
    semesters: list[ClassSemester] | None = None,
) -> ClassResponse:
    active_membership = (
        membership
        if membership is not None and membership.status == MembershipStatus.ACTIVE
        else None
    )

    may_view_code = (
        active_membership is not None
        and active_membership.role == ClassRole.ORGANIZER
        and active_membership.account.is_active
        and effective_role(active_membership.account.account_type) == AccountRole.ADMIN
    )

    return ClassResponse(
        class_id=class_.class_id,
        name=class_.name,
        semester=class_.semester,
        parent_class_id=class_.parent_class_id,
        semesters=semesters or [],
        created_by_id=class_.created_by_id,
        join_code=_format_join_code(class_.join_code) if may_view_code else None,
        joining_open=class_.joining_open,
        archived_at=class_.archived_at,
        created_at=class_.created_at,
        updated_at=class_.updated_at,
        current_role=(
            active_membership.role if active_membership is not None else None
        ),
        membership_status=membership.status if membership is not None else None,
    )


def _access_response(
    db: Session,
    account: CurrentAccount,
    access: ClassAccess,
) -> ClassResponse:
    links = _family_links(db, account, [access.class_])
    return _to_response(
        access.class_,
        access.membership,
        links.get(access.class_.class_id, []),
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
    require_active_faculty(account)

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
        semester=payload.semester,
        created_by_id=account.account_id,
        join_code=code,
        memberships=[membership],
    )

    db.add(class_)
    _commit(db, "class_create_failed", "Could not create the class.")

    links = _family_links(db, account, [class_])
    return _to_response(class_, membership, links.get(class_.class_id, []))


def list_classes(
    db: Session,
    account: CurrentAccount,
) -> list[ClassResponse]:
    if not account.is_active:
        raise APIError(403, "inactive_account", "This account is inactive.")

    rows = db.execute(
        select(Class, ClassMembership)
        .join(ClassMembership, ClassMembership.class_id == Class.class_id)
        .where(
            ClassMembership.account_id == account.account_id,
            ClassMembership.status.in_(
                (
                    MembershipStatus.ACTIVE,
                    MembershipStatus.INVITED,
                    # Waiting for an organizer to approve a join request.
                    MembershipStatus.REQUESTED,
                )
            ),
            # Trashed classes are listed by GET /trash instead.
            Class.deleted_at.is_(None),
        )
        .order_by(Class.created_at.desc(), Class.class_id.desc())
    ).all()

    links = _family_links(db, account, [class_ for class_, _ in rows])
    return [
        _to_response(class_, membership, links.get(class_.class_id, []))
        for class_, membership in rows
    ]


def get_class(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassResponse:
    return _access_response(db, account, require_class_member(db, account, class_id))


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

    if "semester" in payload.model_fields_set:
        # Before any other change, so the course lock is taken first.
        check_semester_label(db, class_, payload.semester)
        class_.semester = payload.semester
    if "name" in payload.model_fields_set:
        class_.name = payload.name
    if "joining_open" in payload.model_fields_set:
        class_.joining_open = payload.joining_open
    _commit(db, "class_update_failed", "Could not update the class.")
    return _access_response(db, account, access)


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
    return _access_response(db, account, access)


def archive_class(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassResponse:
    access = require_class_organizer(db, account, class_id)
    class_ = access.class_
    if class_.archived_at is not None:
        return _access_response(db, account, access)

    class_.archived_at = _utc_now_milliseconds()
    class_.joining_open = False
    class_.join_code = None
    _commit(db, "class_archive_failed", "Could not archive the class.")
    return _access_response(db, account, access)


def unarchive_class(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> ClassResponse:
    """Make an archived class active again.

    Archiving threw the old code away, so the class gets a new one. Joining
    opens again; code joins still wait for an organizer to approve them.
    """
    access = require_class_organizer(db, account, class_id)
    class_ = access.class_
    if class_.archived_at is None:
        return _access_response(db, account, access)

    class_.join_code = _generate_unique_code(
        db,
        error_code="class_unarchive_failed",
        error_message="Could not unarchive the class.",
    )
    class_.joining_open = True
    class_.archived_at = None
    _commit(db, "class_unarchive_failed", "Could not unarchive the class.")
    return _access_response(db, account, access)


def lock_course(db: Session, class_id: int) -> None:
    """Lock the first class of the course that `class_id` belongs to.

    Every change to a course's semesters takes this lock first, before any
    other class row, so two requests can't both add the same semester and
    can't deadlock each other.
    """
    parent_id = db.scalar(select(Class.parent_class_id).where(Class.class_id == class_id))
    db.execute(
        select(Class.class_id)
        .where(Class.class_id == (parent_id or class_id))
        .with_for_update()
    )


def _lock_family(db: Session, class_: Class) -> list[Class]:
    """Lock the course and return all of its semesters that still exist.

    Semesters in the trash count, because they can be restored. The rows are
    read with FOR UPDATE so MySQL returns the newest data, not the snapshot
    this transaction started with.
    """
    root_id = class_.parent_class_id or class_.class_id
    lock_course(db, class_.class_id)
    return list(
        db.scalars(
            select(Class)
            .where(
                Class.purged_at.is_(None),
                or_(Class.class_id == root_id, Class.parent_class_id == root_id),
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    )


def _refuse_duplicate(
    siblings: list[Class],
    class_id: int | None,
    label: str,
) -> None:
    wanted = label.casefold()
    if any(
        row.class_id != class_id and (row.semester or "").casefold() == wanted
        for row in siblings
    ):
        raise APIError(
            409,
            "semester_exists",
            "This course already has that semester.",
        )


def check_semester_label(db: Session, class_: Class, label: str | None) -> None:
    """Refuse a label that would break the course's semesters.

    Used when a class's semester changes and when a class comes back from
    the trash: no two semesters of a course share a label, and a course with
    more than one semester has a label on every one of them.
    """
    siblings = _lock_family(db, class_)
    others = [row for row in siblings if row.class_id != class_.class_id]
    if label is None:
        if others:
            raise APIError(
                409,
                "semester_required",
                "A course with more than one semester needs a semester on each class.",
            )
        return
    _refuse_duplicate(others, class_.class_id, label)


def create_semester(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    payload: ClassSemesterCreate,
) -> ClassResponse:
    """Another empty semester of this course, managed from the same class.

    It keeps the course name and gets its own code. Students and quizzes
    are not copied. The organizers of the semester you started from are.
    """
    access = require_class_organizer(db, account, class_id)
    source = access.class_
    root_id = source.parent_class_id or source.class_id
    siblings = _lock_family(db, source)
    if any(row.semester is None for row in siblings):
        # Every semester of a course has a label, so the semester switcher
        # never shows "No semester". Old classes made before semesters
        # existed get one with PATCH /classes/{id} first.
        raise APIError(
            409,
            "semester_missing",
            "Set this class's semester before starting a new one.",
        )
    _refuse_duplicate(siblings, None, payload.semester)

    organizers = db.scalars(
        select(ClassMembership).where(
            ClassMembership.class_id == source.class_id,
            ClassMembership.status == MembershipStatus.ACTIVE,
            ClassMembership.role == ClassRole.ORGANIZER,
        )
    ).all()
    organizer_ids = {row.account_id for row in organizers}
    organizer_ids.add(account.account_id)

    code = _generate_unique_code(
        db,
        error_code="semester_create_failed",
        error_message="Could not start the new semester.",
    )
    created = Class(
        name=source.name,
        semester=payload.semester,
        parent_class_id=root_id,
        created_by_id=account.account_id,
        join_code=code,
        memberships=[
            ClassMembership(
                account_id=organizer_id,
                role=ClassRole.ORGANIZER,
                status=MembershipStatus.ACTIVE,
                joined_via=(
                    JoinedVia.CREATOR
                    if organizer_id == account.account_id
                    else JoinedVia.INVITE
                ),
            )
            for organizer_id in organizer_ids
        ],
    )
    db.add(created)
    _commit(db, "semester_create_failed", "Could not start the new semester.")
    membership = next(
        row for row in created.memberships if row.account_id == account.account_id
    )
    links = _family_links(db, account, [created])
    return _to_response(created, membership, links.get(created.class_id, []))


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
    if class_ is None or class_.deleted_at is not None:
        raise APIError(404, "class_code_not_found", "No class has that code.")
    if class_.archived_at is not None or not class_.joining_open:
        raise APIError(
            403, "class_joining_closed", "This class isn't accepting new students."
        )

    membership = db.scalar(
        select(ClassMembership)
        .where(
            ClassMembership.class_id == class_.class_id,
            ClassMembership.account_id == account.account_id,
        )
        .with_for_update()
    )
    if membership is not None and membership.status == MembershipStatus.ACTIVE:
        raise APIError(409, "already_class_member", "You're already in this class.")
    if membership is not None and membership.status == MembershipStatus.REMOVED:
        # Only an organizer can undo a removal, by inviting them again.
        raise APIError(
            403,
            "class_member_removed",
            "You were removed from this class. Ask an organizer to invite you.",
        )
    if membership is not None and membership.status == MembershipStatus.REQUESTED:
        # Asking twice changes nothing; the request is still waiting.
        links = _family_links(db, account, [class_])
        return _to_response(class_, membership, links.get(class_.class_id, []))

    # Using the code is a request an organizer approves (Approvals ->
    # Students). Someone already invited, or on the imported roster by their
    # verified email (or an earlier link), was chosen by an organizer, so
    # they are in straight away. A roster name alone doesn't count: names
    # can be edited, so that request waits for an organizer.
    now = _utc_now_milliseconds()
    person = db.get(Account, account.account_id)
    roster_entry = (
        find_roster_entry(db, class_.class_id, person) if person is not None else None
    )
    was_invited = (
        membership is not None and membership.status == MembershipStatus.INVITED
    )
    approved = roster_entry is not None or was_invited
    if roster_entry is not None:
        roster_entry.account_id = account.account_id

    if membership is None:
        membership = ClassMembership(
            class_id=class_.class_id,
            account_id=account.account_id,
            role=ClassRole.MEMBER,
            joined_via=JoinedVia.CODE,
        )
        db.add(membership)
    membership.status = (
        MembershipStatus.ACTIVE if approved else MembershipStatus.REQUESTED
    )
    membership.role = ClassRole.MEMBER
    # Preserve an independent invitation when both it and a roster row exist.
    # Otherwise, a roster match is the reason this code join becomes active,
    # and must remain identifiable if that roster entry is later corrected.
    membership.joined_via = (
        JoinedVia.INVITE
        if was_invited
        else JoinedVia.ROSTER
        if roster_entry is not None
        else JoinedVia.CODE
    )
    membership.decided_by_id = account.account_id
    membership.decided_at = now

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
    links = _family_links(db, account, [class_])
    return _to_response(class_, membership, links.get(class_.class_id, []))


def leave_class(
    db: Session,
    account: CurrentAccount,
    class_id: int,
) -> None:
    """Reject self-service departure; organizers control class rosters."""
    raise APIError(
        403,
        "class_self_leave_disabled",
        "Ask a class organizer to remove you from the class.",
    )
