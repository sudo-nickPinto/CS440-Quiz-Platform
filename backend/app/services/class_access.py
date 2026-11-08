"""Who may take part in a class's live sessions.

Every session belongs to a class. Only ACTIVE members of that class may join
it, reconnect, receive live events or answer; the join code alone is not
enough. Sessions from before V3 with no class (old open sessions) are
read-only history: nobody can join or answer in them any more.
"""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    LiveSession,
    LiveSessionStatus,
    MembershipStatus,
    SessionParticipant,
)
from app.services.class_authorization import get_class_membership


def may_play(db: Session, session: LiveSession, account_id: int) -> bool:
    """True when the account may join or answer in the session."""
    if session.class_id is None:
        return False
    membership = get_class_membership(db, session.class_id, account_id)
    return membership is not None and membership.status == MembershipStatus.ACTIVE


def leave_class_sessions(
    db: Session,
    class_id: int,
    account_id: int,
    left_at: datetime,
) -> list[int]:
    """Mark the account as left in the class's live sessions.

    Called in the same transaction that removes the account from the class,
    or records that they left it; the caller commits. Returns the sessions
    whose participant row changed, so the live hub can update their hosts.
    """
    # Lock the sessions first, in id order, as end_session and leave_session
    # lock theirs, so this can't interleave with final results.
    session_ids = list(
        db.scalars(
            select(LiveSession.session_id)
            .where(
                LiveSession.class_id == class_id,
                LiveSession.status.in_(
                    (LiveSessionStatus.LOBBY, LiveSessionStatus.ACTIVE)
                ),
            )
            .order_by(LiveSession.session_id)
            .with_for_update()
        )
    )
    if not session_ids:
        return []
    left = list(
        db.scalars(
            select(SessionParticipant.session_id).where(
                SessionParticipant.session_id.in_(session_ids),
                SessionParticipant.account_id == account_id,
                SessionParticipant.left_at.is_(None),
            )
        )
    )
    if left:
        db.execute(
            update(SessionParticipant)
            .where(
                SessionParticipant.session_id.in_(left),
                SessionParticipant.account_id == account_id,
                SessionParticipant.left_at.is_(None),
            )
            .values(left_at=left_at)
        )
    return sorted(left)


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
