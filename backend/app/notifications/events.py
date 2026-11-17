"""App events pushed over `/ws/notifications` (LIVE_PROTOCOL.md §11).

Each event has two layers:

- a sync resolver that takes a DB session and returns who gets the event and
  what it says (run through `hub.run_db`, so it gets its own session), and
- an async `notify_*` entry point that a route schedules after its commit
  with FastAPI `BackgroundTasks`, so it runs after the response is sent.

Payloads carry ids, titles and status only: nothing a recipient could not
already fetch over HTTP. A failed notification is logged and swallowed, so
it never fails or rolls back the request that triggered it.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal, get_args

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    Class,
    ClassMembership,
    ClassRole,
    LiveSession,
    MembershipStatus,
    Quiz,
    QuizSubmission,
    QuizVersion,
)
from app.models.account import FACULTY_ACCOUNT_TYPE
from app.notifications.hub import NotificationHub

logger = logging.getLogger(__name__)

SubmissionAction = Literal["submitted", "approved", "rejected", "withdrawn"]
SUBMISSION_ACTIONS = frozenset(get_args(SubmissionAction))
# Actions whose outcome the quiz's author also needs to see.
_DECISIONS = frozenset({"approved", "rejected"})


@dataclass(frozen=True, slots=True)
class Notification:
    account_ids: frozenset[int]
    payload: dict


def class_organizer_ids(db: Session, class_id: int) -> set[int]:
    """Accounts allowed to decide the class's submissions.

    Same rule as `ClassAccess.is_organizer`: an ACTIVE ORGANIZER membership
    held by an active faculty account.
    """
    return set(
        db.scalars(
            select(ClassMembership.account_id)
            .join(Account, Account.account_id == ClassMembership.account_id)
            .where(
                ClassMembership.class_id == class_id,
                ClassMembership.role == ClassRole.ORGANIZER,
                ClassMembership.status == MembershipStatus.ACTIVE,
                Account.is_active.is_(True),
                Account.account_type == FACULTY_ACCOUNT_TYPE,
            )
        )
    )


def active_member_ids(db: Session, class_id: int) -> set[int]:
    """Active accounts with an ACTIVE membership (any role) in the class."""
    return set(
        db.scalars(
            select(ClassMembership.account_id)
            .join(Account, Account.account_id == ClassMembership.account_id)
            .where(
                ClassMembership.class_id == class_id,
                ClassMembership.status == MembershipStatus.ACTIVE,
                Account.is_active.is_(True),
            )
        )
    )


def resolve_submission_changed(
    db: Session,
    submission_id: int,
    action: str,
    actor_account_id: int,
) -> Notification | None:
    if action not in SUBMISSION_ACTIONS:
        raise ValueError(f"Unknown submission action: {action!r}")
    row = db.execute(
        select(QuizSubmission, QuizVersion, Quiz, Class)
        .join(
            QuizVersion,
            QuizVersion.quiz_version_id == QuizSubmission.quiz_version_id,
        )
        .join(Quiz, Quiz.quiz_id == QuizVersion.quiz_id)
        .join(Class, Class.class_id == QuizSubmission.class_id)
        .where(QuizSubmission.submission_id == submission_id)
    ).one_or_none()
    if row is None:
        return None
    submission, version, quiz, class_ = row

    recipients = class_organizer_ids(db, class_.class_id)
    involved = {submission.submitted_by_id}
    if action in _DECISIONS:
        involved.add(quiz.author_id)
    # Only people who can still open the class may hear about it.
    recipients |= involved & active_member_ids(db, class_.class_id)
    # The actor is not excluded: their other tabs should update too. Clients
    # compare actor_account_id to skip a toast for their own action.
    return Notification(
        account_ids=frozenset(recipients),
        payload={
            "type": "submission_changed",
            "action": action,
            "submission_id": submission.submission_id,
            "class_id": class_.class_id,
            "quiz_id": quiz.quiz_id,
            "quiz_title": version.title,
            "class_name": class_.name,
            "status": submission.status.value,
            "actor_account_id": actor_account_id,
        },
    )


def resolve_session_live(
    db: Session,
    session_id: int,
) -> list[Notification]:
    row = db.execute(
        select(LiveSession, QuizVersion, Class, Account.display_name)
        .join(
            QuizVersion,
            QuizVersion.quiz_version_id == LiveSession.quiz_version_id,
        )
        .join(Class, Class.class_id == LiveSession.class_id)
        .join(Account, Account.account_id == LiveSession.host_id)
        .where(LiveSession.session_id == session_id)
    ).one_or_none()
    # The inner join on Class also drops old sessions with no class.
    if row is None:
        return []
    session, version, class_, host_name = row

    recipients = active_member_ids(db, class_.class_id) - {session.host_id}
    organizers = class_organizer_ids(db, class_.class_id) & recipients
    # session_id is what the class page's Live button joins and navigates
    # with; join_code is the same code members see in
    # GET /classes/{class_id}/active-sessions.
    payload = {
        "type": "session_live",
        "session_id": session.session_id,
        "class_id": class_.class_id,
        "class_name": class_.name,
        "quiz_title": version.title,
        "host_name": host_name,
        "join_code": session.join_code,
    }
    # role is the recipient's role in the class: members get the "join now"
    # popup, co-organizers only refresh their Live button.
    return [
        Notification(
            account_ids=frozenset(recipients - organizers),
            payload={**payload, "role": ClassRole.MEMBER.value},
        ),
        Notification(
            account_ids=frozenset(organizers),
            payload={**payload, "role": ClassRole.ORGANIZER.value},
        ),
    ]


async def _deliver(hub: NotificationHub, notification: Notification | None) -> None:
    if notification is not None and notification.account_ids:
        await hub.send_to_accounts(notification.account_ids, notification.payload)


async def notify_submission_changed(
    hub: NotificationHub,
    *,
    submission_id: int,
    action: SubmissionAction,
    actor_account_id: int,
) -> None:
    """Tell the right accounts a quiz submission changed. Call after commit.

    Every action reaches the class's organizers and the submitter;
    approved/rejected also reach the quiz's author.
    """
    try:
        notification = await hub.run_db(
            resolve_submission_changed, submission_id, action, actor_account_id
        )
        await _deliver(hub, notification)
    except Exception:
        logger.exception(
            "Could not send submission_changed for submission %s (%s)",
            submission_id,
            action,
        )


async def notify_session_live(
    hub: NotificationHub,
    *,
    session_id: int,
    actor_account_id: int,
) -> None:
    """Tell the class's active members, except the host, a lobby opened.

    Call after the session is committed. Sessions with no class send nothing.
    """
    try:
        notifications = await hub.run_db(resolve_session_live, session_id)
        await asyncio.gather(
            *(_deliver(hub, notification) for notification in notifications)
        )
    except Exception:
        logger.exception(
            "Could not send session_live for session %s opened by account %s",
            session_id,
            actor_account_id,
        )
