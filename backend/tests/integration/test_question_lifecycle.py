from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.models import (
    Account,
    AccountRole,
    LiveSession,
    LiveSessionStatus,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.schemas.live_question import QuestionCloseReason, QuestionOpenedEvent
from app.schemas.response import ResponseSubmit
from app.services.live_questions import close_question_if_ready, open_question
from app.services.responses import submit_response


QUIZ_PAYLOAD = {
    "title": "MySQL lifecycle quiz",
    "questions": [
        {
            "question_text": "Which option should be selected?",
            "time_limit_seconds": 30,
            "base_points": 1000,
            "choices": [
                {"choice_text": "This option", "is_correct": True},
                {"choice_text": "Another option", "is_correct": False},
            ],
        }
    ],
}

# This is the complete child-first order used by the migrated test database.
CLEANUP_TABLES = [
    "result",
    "response",
    "session_question",
    "session_participant",
    "live_session",
    "answer_choice",
    "question",
    "quiz_version",
    "quiz_collaborator",
    "quiz_group",
    "quiz",
    "group_membership",
    "course_group",
    "account_identity",
    "account",
]


@dataclass(frozen=True)
class LifecycleContext:
    client: TestClient
    db: Session
    host: CurrentAccount
    first_participant: CurrentAccount
    second_participant: CurrentAccount
    late_participant: CurrentAccount


@dataclass(frozen=True)
class OpenQuestionContext:
    session_id: int
    choice_id: int
    join_code: str
    opened: QuestionOpenedEvent


def _cleanup_and_verify(client: TestClient) -> None:
    engine = client.app.state.database.engine
    with engine.begin() as connection:
        for table in CLEANUP_TABLES:
            connection.execute(text(f"DELETE FROM {table}"))

        remaining = {
            table: connection.scalar(text(f"SELECT COUNT(*) FROM {table}"))
            for table in CLEANUP_TABLES
        }

    assert remaining == {table: 0 for table in CLEANUP_TABLES}


@pytest.fixture
def lifecycle_context(
    mysql_quiz_client: tuple[TestClient, CurrentAccount, CurrentAccount],
) -> Iterator[LifecycleContext]:
    client, host, first_participant = mysql_quiz_client
    engine = client.app.state.database.engine
    if engine.url.database != "quizdb_test":
        pytest.fail("Lifecycle integration tests require exactly quizdb_test.")

    db = Session(engine)
    applied = set(db.execute(text("SELECT version FROM schema_migrations")).scalars())
    if "0005_optional_session_group" not in applied:
        db.close()
        pytest.fail("Apply migrations 0001 through 0005 to quizdb_test first.")

    unique = uuid4().hex
    second_account = Account(
        auth0_sub=f"test|lifecycle-second-{unique}",
        email=f"lifecycle-second-{unique}@example.test",
        display_name="Second participant",
        account_type="STUDENT",
    )
    late_account = Account(
        auth0_sub=f"test|lifecycle-late-{unique}",
        email=f"lifecycle-late-{unique}@example.test",
        display_name="Late participant",
        account_type="STUDENT",
    )
    db.add_all([second_account, late_account])
    db.flush()
    second_account_id = second_account.account_id
    late_account_id = late_account.account_id
    db.commit()

    try:
        yield LifecycleContext(
            client=client,
            db=db,
            host=host,
            first_participant=first_participant,
            second_participant=CurrentAccount(
                second_account_id,
                AccountRole.USER,
                True,
            ),
            late_participant=CurrentAccount(
                late_account_id,
                AccountRole.USER,
                True,
            ),
        )
    finally:
        db.close()
        _cleanup_and_verify(client)


def _use_account(client: TestClient, account: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: account


def _join_session(
    context: LifecycleContext,
    account: CurrentAccount,
    join_code: str,
) -> int:
    _use_account(context.client, account)
    response = context.client.post(
        "/sessions/join",
        json={"join_code": join_code},
    )
    assert response.status_code == 201
    return response.json()["participant"]["session_participant_id"]


def _create_and_open_question(
    context: LifecycleContext,
) -> OpenQuestionContext:
    _use_account(context.client, context.host)
    quiz_response = context.client.post("/quizzes", json=QUIZ_PAYLOAD)
    assert quiz_response.status_code == 201
    quiz = quiz_response.json()

    lobby_response = context.client.post(
        f"/quizzes/{quiz['quiz_id']}/sessions"
    )
    assert lobby_response.status_code == 201
    lobby = lobby_response.json()
    assert lobby["status"] == LiveSessionStatus.LOBBY.value

    _join_session(
        context,
        context.first_participant,
        lobby["join_code"],
    )
    _join_session(
        context,
        context.second_participant,
        lobby["join_code"],
    )

    context.db.expire_all()
    joined_at = context.db.scalars(
        select(SessionParticipant.joined_at).where(
            SessionParticipant.session_id == lobby["session_id"],
            SessionParticipant.account_id.in_(
                [
                    context.first_participant.account_id,
                    context.second_participant.account_id,
                ]
            ),
        )
    ).all()
    assert len(joined_at) == 2
    opened_at = max(joined_at) + timedelta(milliseconds=1)

    opened = open_question(
        context.db,
        context.host,
        lobby["session_id"],
        1,
        opened_at=opened_at,
    )

    return OpenQuestionContext(
        session_id=lobby["session_id"],
        choice_id=quiz["version"]["questions"][0]["choices"][0]["choice_id"],
        join_code=lobby["join_code"],
        opened=opened,
    )


def test_mysql_question_closes_early_after_opening_roster_answers(
    lifecycle_context: LifecycleContext,
) -> None:
    context = lifecycle_context
    flow = _create_and_open_question(context)

    context.db.expire_all()
    session = context.db.get(LiveSession, flow.session_id)
    played = context.db.get(
        SessionQuestion,
        flow.opened.session_question_id,
    )
    assert session is not None
    assert played is not None
    assert flow.opened.opened_at.tzinfo is None
    assert flow.opened.closes_at == flow.opened.opened_at + timedelta(seconds=30)
    assert session.status == LiveSessionStatus.ACTIVE
    assert session.started_at == flow.opened.opened_at
    assert session.current_question_order == 1
    assert played.opened_at == flow.opened.opened_at
    assert played.closes_at == flow.opened.closes_at

    submit_response(
        context.db,
        context.first_participant,
        flow.session_id,
        flow.opened.session_question_id,
        ResponseSubmit(choice_id=flow.choice_id),
        submitted_at=flow.opened.opened_at + timedelta(seconds=1),
    )
    first_check = close_question_if_ready(
        context.db,
        flow.session_id,
        flow.opened.session_question_id,
        checked_at=flow.opened.opened_at + timedelta(seconds=2),
    )
    assert first_check is None
    context.db.expire_all()
    still_open = context.db.get(
        SessionQuestion,
        flow.opened.session_question_id,
    )
    assert still_open is not None
    assert still_open.status == SessionQuestionStatus.OPEN
    context.db.rollback()

    late_participant_id = _join_session(
        context,
        context.late_participant,
        flow.join_code,
    )
    context.db.expire_all()
    late_participant = context.db.get(
        SessionParticipant,
        late_participant_id,
    )
    assert late_participant is not None
    late_participant.joined_at = flow.opened.opened_at + timedelta(milliseconds=1)
    context.db.commit()

    submit_response(
        context.db,
        context.second_participant,
        flow.session_id,
        flow.opened.session_question_id,
        ResponseSubmit(choice_id=flow.choice_id),
        submitted_at=flow.opened.opened_at + timedelta(seconds=3),
    )
    closed = close_question_if_ready(
        context.db,
        flow.session_id,
        flow.opened.session_question_id,
        checked_at=flow.opened.opened_at + timedelta(seconds=4),
    )

    assert closed is not None
    assert closed.reason == QuestionCloseReason.ALL_ANSWERED
    assert closed.eligible_count == 2
    assert closed.answered_count == 2
    assert late_participant.joined_at > flow.opened.opened_at


def test_mysql_question_closes_once_at_deadline(
    lifecycle_context: LifecycleContext,
) -> None:
    context = lifecycle_context
    flow = _create_and_open_question(context)

    submit_response(
        context.db,
        context.first_participant,
        flow.session_id,
        flow.opened.session_question_id,
        ResponseSubmit(choice_id=flow.choice_id),
        submitted_at=flow.opened.opened_at + timedelta(seconds=1),
    )
    checked_at = flow.opened.closes_at + timedelta(milliseconds=1)
    closed = close_question_if_ready(
        context.db,
        flow.session_id,
        flow.opened.session_question_id,
        checked_at=checked_at,
    )

    assert closed is not None
    assert closed.reason == QuestionCloseReason.DEADLINE
    assert closed.eligible_count == 2
    assert closed.answered_count == 1
    assert closed.closed_at == checked_at

    context.db.expire_all()
    played = context.db.get(
        SessionQuestion,
        flow.opened.session_question_id,
    )
    assert played is not None
    assert played.status == SessionQuestionStatus.CLOSED
    assert played.closed_at == checked_at

    repeated = close_question_if_ready(
        context.db,
        flow.session_id,
        flow.opened.session_question_id,
        checked_at=checked_at + timedelta(seconds=1),
    )
    assert repeated is None
