"""Who may take part in a class's live sessions.

Every session belongs to a class. Only ACTIVE members of that class may join
it, reconnect, receive live events or answer; the join code alone is not
enough. Sessions from before V3 with no class (old open sessions) are
read-only history: nobody can join or answer in them any more.
"""

from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import LiveSession, MembershipStatus
from app.services.class_authorization import get_class_membership


def may_play(db: Session, session: LiveSession, account_id: int) -> bool:
    """True when the account may join or answer in the session."""
    if session.class_id is None:
        return False
    membership = get_class_membership(db, session.class_id, account_id)
    return membership is not None and membership.status == MembershipStatus.ACTIVE


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
