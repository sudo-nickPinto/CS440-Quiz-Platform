"""The trash: classes, quizzes and hosted sessions deleted by mistake.

Nothing here really deletes a row. Results, approvals and reports point at
classes, quizzes and sessions, so moving one to the trash sets its
`deleted_at` (migration 0017) and restoring clears it. While it is set:

- a class looks missing everywhere (class_authorization.get_class), and so
  do its quizzes, sessions and reports;
- a quiz looks missing (quizzes._quiz_query) and leaves its class's quiz
  lists, approval queue and hostable quizzes;
- a session leaves hosting history, "quizzes taken", and the class's
  reports and grades, and direct results/report/export/correction URLs
  look like the session is missing;
- a quiz's questions leave collaborator and organizer question-bank
  views (the owner's own bank copies stay).

Who may move what:
- a class: its active faculty organizers;
- a quiz: its owner, while an active member of the quiz's class;
- a session: its host, once the session has ended.

Moving and restoring are idempotent. Something running live can't be moved,
so a game never ends up in the trash mid-question.

Deleting a class permanently (by hand, or 30 days after it was trashed) also
deletes the quizzes and sessions of that class that were in the trash, so
nothing is left behind that points at a class you can't restore.

Bulk restore and delete (/trash/restore, /trash/purge) are all or nothing: if
one id can't be changed, nothing is.
"""

from datetime import UTC, datetime, timedelta
from math import ceil

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentAccount
from app.errors import APIError
from app.models.classes import Class, ClassMembership, ClassRole, MembershipStatus
from app.models.quiz import Quiz, QuizVersion
from app.models.session import LiveSession, LiveSessionStatus
from app.schemas.trash import (
    TrashedClass,
    TrashedQuiz,
    TrashedSession,
    TrashResponse,
    TrashSelection,
)
from app.services.class_authorization import ClassAccess, get_class_membership
from app.services.classes import check_semester_label, lock_course
from app.services.quizzes import _latest_editor_version

LIVE_STATUSES = (LiveSessionStatus.LOBBY, LiveSessionStatus.ACTIVE)
ENDED_STATUSES = (LiveSessionStatus.COMPLETED, LiveSessionStatus.CANCELLED)
# Class feedback: a trashed row is restorable for 30 days, then it leaves
# the trash for good. The row stays so old results still have something to
# point at.
TRASH_DAYS = 30


def _now() -> datetime:
    now = datetime.now(UTC).replace(tzinfo=None)
    return now.replace(microsecond=(now.microsecond // 1000) * 1000)


def _expires(deleted_at: datetime) -> datetime:
    return deleted_at + timedelta(days=TRASH_DAYS)


def _days_left(deleted_at: datetime) -> int:
    remaining = (_expires(deleted_at) - _now()).total_seconds()
    if remaining <= 0:
        return 0
    return ceil(remaining / 86400)


def _stamp(deleted_at: datetime) -> dict:
    return {
        "deleted_at": _utc(deleted_at),
        "expires_at": _utc(_expires(deleted_at)),
        "days_left": _days_left(deleted_at),
    }


def _purge_class_contents(db: Session, class_id: int, now: datetime) -> None:
    """A class is gone for good, so its trashed quizzes and sessions go too.

    Otherwise they would stay in the trash asking for a class that can't be
    restored any more.
    """
    for model in (Quiz, LiveSession):
        db.execute(
            update(model)
            .where(
                model.class_id == class_id,
                model.deleted_at.is_not(None),
                model.purged_at.is_(None),
            )
            .values(purged_at=now)
            .execution_options(synchronize_session=False)
        )


def expire_trash(db: Session) -> None:
    """Retire anything that has been in the trash for 30 days."""
    cutoff = _now() - timedelta(days=TRASH_DAYS)
    now = _now()
    changed = False
    for model in (Class, Quiz, LiveSession):
        rows = db.scalars(
            select(model).where(
                model.deleted_at.is_not(None),
                model.purged_at.is_(None),
                model.deleted_at <= cutoff,
            )
        ).all()
        for row in rows:
            row.purged_at = now
            if model is Class:
                _purge_class_contents(db, row.class_id, now)
            changed = True
    if changed:
        _commit(db, "trash_expire_failed", "Could not expire the trash.")


def _check_restorable(row, kind: str) -> None:
    # Gone for good: deleted by hand, or past its 30 days (expire_trash marks
    # those on its next run).
    if row.purged_at is not None or _days_left(row.deleted_at) == 0:
        raise _gone(kind)


def _gone(kind: str) -> APIError:
    return APIError(404, f"{kind}_not_found", f"{kind.capitalize()} not found.")


def _utc(value: datetime | None) -> datetime | None:
    # MySQL hands back naive UTC datetimes; label them so clients don't guess.
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _commit(db: Session, code: str, message: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, code, message) from exc


def _class_in_trash() -> APIError:
    return APIError(
        409,
        "class_in_trash",
        "This class is in the trash. Restore the class first.",
    )


def _check_parent_class(class_: Class, kind: str, allow_trashed_class: bool) -> None:
    """A quiz or session can't be restored while its class is in the trash.

    Once the class is deleted for good, the quiz or session is gone too.
    """
    if class_.purged_at is not None:
        raise _gone(kind)
    if not allow_trashed_class and class_.deleted_at is not None:
        raise _class_in_trash()


def _has_live_session(db: Session, *conditions) -> bool:
    return (
        db.scalar(
            select(LiveSession.session_id)
            .where(*conditions, LiveSession.status.in_(LIVE_STATUSES))
            .limit(1)
        )
        is not None
    )


# -- Classes ---------------------------------------------------------------


def _require_organizer(db: Session, account: CurrentAccount, class_id: int) -> Class:
    """require_class_organizer, but it also finds classes in the trash."""
    class_ = db.scalar(
        select(Class).where(Class.class_id == class_id).with_for_update()
    )
    membership = (
        get_class_membership(db, class_id, account.account_id)
        if class_ is not None and account.is_active
        else None
    )
    if membership is None or membership.status != MembershipStatus.ACTIVE:
        raise APIError(404, "class_not_found", "Class not found.")
    if not ClassAccess(class_, membership, is_faculty=account.is_admin).is_organizer:
        raise APIError(
            403,
            "not_class_organizer",
            "Only an active faculty organizer can perform this action.",
        )
    return class_


def trash_class(db: Session, account: CurrentAccount, class_id: int) -> None:
    class_ = _require_organizer(db, account, class_id)
    if class_.deleted_at is not None:
        return
    if _has_live_session(db, LiveSession.class_id == class_id):
        raise APIError(
            409,
            "class_has_live_session",
            "End the live session in this class before moving it to the trash.",
        )
    class_.deleted_at = _now()
    _commit(db, "class_trash_failed", "Could not move the class to the trash.")


def _restore_class(db: Session, account: CurrentAccount, class_id: int) -> None:
    # The course lock comes before the class row lock (see lock_course).
    lock_course(db, class_id)
    class_ = _require_organizer(db, account, class_id)
    if class_.deleted_at is None:
        return
    _check_restorable(class_, "class")
    if class_.semester is not None:
        # While it was in the trash, the course may have started the same
        # semester again. Two "Fall 2026" classes in one course can't both
        # exist.
        check_semester_label(db, class_, class_.semester)
    class_.deleted_at = None


def _purge_class(db: Session, account: CurrentAccount, class_id: int) -> None:
    class_ = _require_organizer(db, account, class_id)
    if class_.deleted_at is None or class_.purged_at is not None:
        raise _gone("class")
    now = _now()
    class_.purged_at = now
    _purge_class_contents(db, class_id, now)


def restore_class(db: Session, account: CurrentAccount, class_id: int) -> None:
    expire_trash(db)
    _restore_class(db, account, class_id)
    _commit(db, "class_restore_failed", "Could not restore the class.")


# -- Quizzes ---------------------------------------------------------------


def _require_quiz_owner(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
    *,
    allow_trashed_class: bool = False,
) -> Quiz:
    # Locked, like archive_quiz: the quiz row serializes edits and publishing.
    quiz = db.scalar(
        select(Quiz)
        .where(Quiz.quiz_id == quiz_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    # Only the owner; being a class organizer or a collaborator isn't enough.
    if quiz is None or quiz.author_id != account.account_id:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    if quiz.class_id is not None:
        membership = get_class_membership(db, quiz.class_id, account.account_id)
        if membership is None or membership.status != MembershipStatus.ACTIVE:
            raise APIError(404, "quiz_not_found", "Quiz not found.")
        _check_parent_class(
            db.get(Class, quiz.class_id), "quiz", allow_trashed_class
        )
    return quiz


def trash_quiz(db: Session, account: CurrentAccount, quiz_id: int) -> None:
    quiz = _require_quiz_owner(db, account, quiz_id)
    if quiz.deleted_at is not None:
        return
    versions = select(QuizVersion.quiz_version_id).where(
        QuizVersion.quiz_id == quiz_id
    )
    if _has_live_session(db, LiveSession.quiz_version_id.in_(versions)):
        raise APIError(
            409,
            "quiz_has_live_session",
            "End the live session of this quiz before moving it to the trash.",
        )
    quiz.deleted_at = _now()
    _commit(db, "quiz_trash_failed", "Could not move the quiz to the trash.")


def _restore_quiz(db: Session, account: CurrentAccount, quiz_id: int) -> None:
    quiz = _require_quiz_owner(db, account, quiz_id)
    if quiz.deleted_at is None:
        return
    _check_restorable(quiz, "quiz")
    quiz.deleted_at = None


def _purge_quiz(db: Session, account: CurrentAccount, quiz_id: int) -> None:
    quiz = _require_quiz_owner(db, account, quiz_id, allow_trashed_class=True)
    if quiz.deleted_at is None or quiz.purged_at is not None:
        raise _gone("quiz")
    quiz.purged_at = _now()


def restore_quiz(db: Session, account: CurrentAccount, quiz_id: int) -> None:
    expire_trash(db)
    _restore_quiz(db, account, quiz_id)
    _commit(db, "quiz_restore_failed", "Could not restore the quiz.")


# -- Sessions --------------------------------------------------------------


def _require_session_host(
    db: Session,
    account: CurrentAccount,
    session_id: int,
    *,
    allow_trashed_class: bool = False,
) -> LiveSession:
    session = db.scalar(
        select(LiveSession)
        .where(LiveSession.session_id == session_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if session is None or session.host_id != account.account_id:
        raise APIError(404, "session_not_found", "Session not found.")
    if session.class_id is not None:
        # The same rule as hosting history: still an active class member.
        membership = get_class_membership(db, session.class_id, account.account_id)
        if membership is None or membership.status != MembershipStatus.ACTIVE:
            raise APIError(404, "session_not_found", "Session not found.")
        _check_parent_class(
            db.get(Class, session.class_id), "session", allow_trashed_class
        )
    return session


def trash_session(db: Session, account: CurrentAccount, session_id: int) -> None:
    session = _require_session_host(db, account, session_id)
    if session.deleted_at is not None:
        return
    if session.status not in ENDED_STATUSES:
        raise APIError(
            409,
            "session_not_ended",
            "End the session before moving it to the trash.",
        )
    session.deleted_at = _now()
    _commit(db, "session_trash_failed", "Could not move the session to the trash.")


def _restore_session(db: Session, account: CurrentAccount, session_id: int) -> None:
    session = _require_session_host(db, account, session_id)
    if session.deleted_at is None:
        return
    _check_restorable(session, "session")
    session.deleted_at = None


def _purge_session(db: Session, account: CurrentAccount, session_id: int) -> None:
    session = _require_session_host(
        db, account, session_id, allow_trashed_class=True
    )
    if session.deleted_at is None or session.purged_at is not None:
        raise _gone("session")
    session.purged_at = _now()


def restore_session(db: Session, account: CurrentAccount, session_id: int) -> None:
    expire_trash(db)
    _restore_session(db, account, session_id)
    _commit(db, "session_restore_failed", "Could not restore the session.")


def _all_or_nothing(db: Session, steps, code: str, message: str) -> None:
    """Run every step in one transaction: one bad id and nothing changes."""
    try:
        for step in steps:
            step()
    except Exception:
        db.rollback()
        raise
    _commit(db, code, message)


def restore_selected(
    db: Session, account: CurrentAccount, selection: TrashSelection
) -> None:
    expire_trash(db)
    # Classes first, so a quiz or session selected with its class can be
    # restored in the same request.
    _all_or_nothing(
        db,
        [lambda i=i: _restore_class(db, account, i) for i in selection.class_ids]
        + [lambda i=i: _restore_quiz(db, account, i) for i in selection.quiz_ids]
        + [
            lambda i=i: _restore_session(db, account, i)
            for i in selection.session_ids
        ],
        "trash_restore_failed",
        "Could not restore the selected items.",
    )


def purge_selected(
    db: Session, account: CurrentAccount, selection: TrashSelection
) -> None:
    expire_trash(db)
    # Quizzes and sessions first: deleting a class also deletes its trashed
    # quizzes and sessions, and they may be in the same selection.
    _all_or_nothing(
        db,
        [lambda i=i: _purge_quiz(db, account, i) for i in selection.quiz_ids]
        + [
            lambda i=i: _purge_session(db, account, i)
            for i in selection.session_ids
        ]
        + [lambda i=i: _purge_class(db, account, i) for i in selection.class_ids],
        "trash_purge_failed",
        "Could not delete the selected items permanently.",
    )


# -- Listing ---------------------------------------------------------------


def _trashed_classes(db: Session, account: CurrentAccount) -> list[TrashedClass]:
    if not account.is_admin:
        # Only faculty organize classes, so nobody else has any to restore.
        return []
    classes = db.scalars(
        select(Class)
        .join(ClassMembership, ClassMembership.class_id == Class.class_id)
        .where(
            ClassMembership.account_id == account.account_id,
            ClassMembership.status == MembershipStatus.ACTIVE,
            ClassMembership.role == ClassRole.ORGANIZER,
            Class.deleted_at.is_not(None),
            Class.purged_at.is_(None),
        )
        .order_by(Class.deleted_at.desc(), Class.class_id.desc())
    ).all()
    return [
        TrashedClass(
            class_id=class_.class_id,
            name=class_.name,
            semester=class_.semester,
            archived=class_.archived_at is not None,
            **_stamp(class_.deleted_at),
        )
        for class_ in classes
    ]


def _trashed_quizzes(db: Session, account: CurrentAccount) -> list[TrashedQuiz]:
    rows = db.execute(
        select(Quiz, Class)
        .outerjoin(Class, Class.class_id == Quiz.class_id)
        .where(
            Quiz.author_id == account.account_id,
            Quiz.deleted_at.is_not(None),
            Quiz.purged_at.is_(None),
        )
        .options(selectinload(Quiz.versions))
        .order_by(Quiz.deleted_at.desc(), Quiz.quiz_id.desc())
    ).all()
    items = []
    for quiz, class_ in rows:
        if class_ is not None:
            if class_.purged_at is not None:
                continue
            membership = get_class_membership(db, class_.class_id, account.account_id)
            if membership is None or membership.status != MembershipStatus.ACTIVE:
                continue
        items.append(
            TrashedQuiz(
                quiz_id=quiz.quiz_id,
                title=_latest_editor_version(quiz).title,
                class_id=quiz.class_id,
                class_name=class_.name if class_ is not None else None,
                class_in_trash=class_ is not None and class_.deleted_at is not None,
                **_stamp(quiz.deleted_at),
            )
        )
    return items


def _trashed_sessions(db: Session, account: CurrentAccount) -> list[TrashedSession]:
    rows = db.execute(
        select(LiveSession, QuizVersion.quiz_id, QuizVersion.title, Class)
        .join(QuizVersion, QuizVersion.quiz_version_id == LiveSession.quiz_version_id)
        .outerjoin(Class, Class.class_id == LiveSession.class_id)
        .where(
            LiveSession.host_id == account.account_id,
            LiveSession.deleted_at.is_not(None),
            LiveSession.purged_at.is_(None),
        )
        .order_by(LiveSession.deleted_at.desc(), LiveSession.session_id.desc())
    ).all()
    items = []
    for session, quiz_id, title, class_ in rows:
        if class_ is not None:
            if class_.purged_at is not None:
                continue
            membership = get_class_membership(db, class_.class_id, account.account_id)
            if membership is None or membership.status != MembershipStatus.ACTIVE:
                continue
        items.append(
            TrashedSession(
                session_id=session.session_id,
                quiz_id=quiz_id,
                quiz_title=title,
                class_id=session.class_id,
                class_name=class_.name if class_ is not None else None,
                class_in_trash=class_ is not None and class_.deleted_at is not None,
                status=session.status,
                ended_at=_utc(session.ended_at),
                **_stamp(session.deleted_at),
            )
        )
    return items


def list_trash(db: Session, account: CurrentAccount) -> TrashResponse:
    if not account.is_active:
        raise APIError(403, "inactive_account", "This account is inactive.")
    expire_trash(db)
    return TrashResponse(
        classes=_trashed_classes(db, account),
        quizzes=_trashed_quizzes(db, account),
        sessions=_trashed_sessions(db, account),
    )
