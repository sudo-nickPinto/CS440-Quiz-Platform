"""Who may take part in a class's live sessions (task 6).

A session belongs to the class of its quiz. When the session has a class, only
ACTIVE members of that class may join it or answer in it; the join code alone
is not enough. A session without a class behaves as it did before classes.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    Class,
    ClassMembership,
    LiveSession,
    MembershipStatus,
    Quiz,
)


def parse_quiz_class_map(raw: str) -> dict[int, int]:
    mapping: dict[int, int] = {}
    for pair in raw.split(","):
        if not pair.strip():
            continue
        quiz_id, _, class_id = pair.partition(":")
        mapping[int(quiz_id.strip())] = int(class_id.strip())
    return mapping


def class_id_for_quiz(db: Session, quiz: Quiz, quiz_class_map: str = "") -> int | None:
    """The class a new session of this quiz belongs to.

    TEMPORARY: quizzes have no class yet (task 5), so this reads the dev-only
    DEV_QUIZ_CLASS_MAP setting. When task 5 adds quiz.class_id, return that
    instead and drop the setting; nothing else needs to change.
    """
    class_id = parse_quiz_class_map(quiz_class_map).get(quiz.quiz_id)
    if class_id is None:
        return None
    class_ = db.get(Class, class_id)
    if class_ is None or class_.archived_at is not None:
        raise APIError(
            409,
            "quiz_class_unavailable",
            "The quiz's class does not exist or has been archived.",
        )
    return class_id


def is_active_member(db: Session, class_id: int, account_id: int) -> bool:
    return (
        db.scalar(
            select(ClassMembership.membership_id).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == account_id,
                ClassMembership.status == MembershipStatus.ACTIVE,
            )
        )
        is not None
    )


def may_play(db: Session, session: LiveSession, account_id: int) -> bool:
    """True when the account may join or answer in the session."""
    return session.class_id is None or is_active_member(
        db, session.class_id, account_id
    )


def require_session_class_member(
    db: Session,
    session: LiveSession,
    account: CurrentAccount,
) -> None:
    if not may_play(db, session, account.account_id):
        raise APIError(
            403,
            "not_class_member",
            "Only active members of this class can take part in the session.",
        )
