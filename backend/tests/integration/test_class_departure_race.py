"""Class roster removal vs. live sessions, on real MySQL."""

import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    Account,
    AccountRole,
    ClassMembership,
    ClassRole,
    JoinedVia,
    LiveSession,
    MembershipStatus,
    SessionParticipant,
)
from app.services.classes import leave_class
from app.services.sessions import join_session
from tests.integration.test_response_submission import (  # noqa: F401
    ResponseContext,
    response_context,
)

HOLD_SECONDS = 0.5


def _session(context: ResponseContext) -> LiveSession:
    context.db.expire_all()
    return context.db.get(LiveSession, context.scenario.session_id)


def test_self_leave_is_rejected_without_changing_the_participant(
    response_context: ResponseContext,
) -> None:
    session = _session(response_context)
    participant = response_context.participant

    with Session(response_context.client.app.state.database.engine) as db:
        try:
            leave_class(db, participant, session.class_id)
        except APIError as exc:
            assert exc.status_code == 403
            assert exc.code == "class_self_leave_disabled"
        else:
            raise AssertionError("self-service class departure was allowed")

    response_context.db.rollback()
    row = response_context.db.scalar(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session.session_id,
            SessionParticipant.account_id == participant.account_id,
        )
    )
    assert row.left_at is None


def test_join_waits_for_a_removal_that_is_committing(
    response_context: ResponseContext,
) -> None:
    session = _session(response_context)
    db = response_context.db
    late = Account(
        auth0_sub=f"test|late-{session.session_id}",
        email=f"late-{session.session_id}@test.invalid",
        display_name="Late",
    )
    db.add(late)
    db.flush()
    db.add(
        ClassMembership(
            class_id=session.class_id,
            account_id=late.account_id,
            role=ClassRole.MEMBER,
            joined_via=JoinedVia.CODE,
        )
    )
    db.commit()
    late_account = CurrentAccount(late.account_id, AccountRole.USER, True)

    engine = response_context.client.app.state.database.engine
    with Session(engine) as removal:
        # The removal holds the membership row, like remove_class_member does.
        membership = removal.scalar(
            select(ClassMembership)
            .where(
                ClassMembership.class_id == session.class_id,
                ClassMembership.account_id == late.account_id,
            )
            .with_for_update()
        )
        membership.status = MembershipStatus.REMOVED
        removal.flush()

        outcome: dict = {}

        def join() -> None:
            with Session(engine) as joiner:
                try:
                    outcome["joined"] = join_session(
                        joiner, late_account, session.join_code
                    )
                except APIError as exc:
                    outcome["error"] = exc.code

        thread = threading.Thread(target=join)
        thread.start()
        time.sleep(HOLD_SECONDS)
        assert thread.is_alive(), "the join did not wait for the removal"
        removal.commit()
        thread.join(5)

    assert outcome == {"error": "not_class_member"}
    db.expire_all()
    assert (
        db.scalar(
            select(SessionParticipant.session_participant_id).where(
                SessionParticipant.session_id == session.session_id,
                SessionParticipant.account_id == late.account_id,
            )
        )
        is None
    )
