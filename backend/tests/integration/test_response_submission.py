from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.models import (
    Account,
    AccountRole,
    AnswerChoice,
    LiveSession,
    LiveSessionStatus,
    Question,
    Quiz,
    QuizStatus,
    QuizVersion,
    QuizVisibility,
    Response,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)


@dataclass
class ResponseScenario:
    session_id: int
    session_question_id: int
    participant_id: int
    correct_choice_id: int
    incorrect_choice_id: int
    other_question_choice_id: int


@dataclass
class ResponseContext:
    client: TestClient
    db: Session
    participant: CurrentAccount
    scenario: ResponseScenario


@pytest.fixture
def response_context(
    mysql_quiz_client: tuple[TestClient, CurrentAccount, CurrentAccount],
) -> Iterator[ResponseContext]:
    client, host_account, participant_account = mysql_quiz_client
    mysql_session = Session(client.app.state.database.engine)
    applied = set(
        mysql_session.execute(text("SELECT version FROM schema_migrations")).scalars()
    )
    if "0005_optional_session_group" not in applied:
        mysql_session.close()
        pytest.fail("Apply migrations 0001 through 0005 to the test database first.")

    unique = uuid4().hex
    correct_choice = AnswerChoice(
        choice_order=1,
        choice_text="Correct",
        is_correct=True,
    )
    incorrect_choice = AnswerChoice(
        choice_order=2,
        choice_text="Incorrect",
        is_correct=False,
    )
    question = Question(
        question_order=1,
        question_text="Which answer is correct?",
        time_limit_seconds=30,
        base_points=1000,
        choices=[correct_choice, incorrect_choice],
    )
    other_choice = AnswerChoice(
        choice_order=1,
        choice_text="Different question",
        is_correct=True,
    )
    other_question = Question(
        question_order=2,
        question_text="A different question",
        time_limit_seconds=30,
        base_points=1000,
        choices=[
            other_choice,
            AnswerChoice(
                choice_order=2,
                choice_text="Other option",
                is_correct=False,
            ),
        ],
    )
    version = QuizVersion(
        version_number=1,
        title="Response submission integration test",
        published_at=datetime.now(UTC).replace(tzinfo=None),
        questions=[question, other_question],
    )
    quiz = Quiz(
        author_id=host_account.account_id,
        status=QuizStatus.PUBLISHED,
        visibility=QuizVisibility.PUBLIC,
        versions=[version],
    )
    mysql_session.add(quiz)
    mysql_session.flush()

    now = datetime.now(UTC).replace(tzinfo=None)
    live_session = LiveSession(
        quiz_version_id=version.quiz_version_id,
        host_id=host_account.account_id,
        group_id=None,
        join_code=unique[:6].upper(),
        status=LiveSessionStatus.ACTIVE,
        current_question_order=1,
        started_at=now - timedelta(seconds=2),
    )
    participant = SessionParticipant(
        session=live_session,
        account_id=participant_account.account_id,
    )
    played_question = SessionQuestion(
        session=live_session,
        question=question,
        status=SessionQuestionStatus.OPEN,
        opened_at=now - timedelta(seconds=2),
        closes_at=now + timedelta(seconds=28),
    )
    mysql_session.add_all([live_session, participant, played_question])
    mysql_session.flush()

    scenario = ResponseScenario(
        session_id=live_session.session_id,
        session_question_id=played_question.session_question_id,
        participant_id=participant.session_participant_id,
        correct_choice_id=correct_choice.choice_id,
        incorrect_choice_id=incorrect_choice.choice_id,
        other_question_choice_id=other_choice.choice_id,
    )
    mysql_session.commit()
    client.app.dependency_overrides[get_active_account] = lambda: participant_account

    try:
        yield ResponseContext(
            client=client,
            db=mysql_session,
            participant=participant_account,
            scenario=scenario,
        )
    finally:
        mysql_session.close()


def response_url(scenario: ResponseScenario) -> str:
    return (
        f"/sessions/{scenario.session_id}/questions/"
        f"{scenario.session_question_id}/responses"
    )


def test_correct_response_is_saved_with_server_calculated_score(
    response_context: ResponseContext,
) -> None:
    scenario = response_context.scenario
    result = response_context.client.post(
        response_url(scenario),
        json={"choice_id": scenario.correct_choice_id},
    )

    assert result.status_code == 201
    body = result.json()
    assert "is_correct" not in body
    assert "points_awarded" not in body
    assert "response_time_ms" not in body

    response_context.db.expire_all()
    saved = response_context.db.scalar(
        select(Response).where(Response.response_id == body["response_id"])
    )
    assert saved is not None
    assert saved.session_participant_id == scenario.participant_id
    assert saved.choice_id == scenario.correct_choice_id
    assert saved.is_correct is True
    assert 500 <= saved.points_awarded <= 1000
    assert saved.response_time_ms >= 2_000


def test_incorrect_response_receives_zero_points(
    response_context: ResponseContext,
) -> None:
    scenario = response_context.scenario
    result = response_context.client.post(
        response_url(scenario),
        json={"choice_id": scenario.incorrect_choice_id},
    )

    assert result.status_code == 201
    response_context.db.expire_all()
    saved = response_context.db.scalar(
        select(Response).where(
            Response.response_id == result.json()["response_id"]
        )
    )
    assert saved is not None
    assert saved.is_correct is False
    assert saved.points_awarded == 0


def test_duplicate_response_is_rejected(
    response_context: ResponseContext,
) -> None:
    scenario = response_context.scenario
    first = response_context.client.post(
        response_url(scenario),
        json={"choice_id": scenario.correct_choice_id},
    )
    duplicate = response_context.client.post(
        response_url(scenario),
        json={"choice_id": scenario.incorrect_choice_id},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "response_already_submitted"


def test_response_after_server_deadline_is_rejected(
    response_context: ResponseContext,
) -> None:
    scenario = response_context.scenario
    played_question = response_context.db.get(
        SessionQuestion, scenario.session_question_id
    )
    assert played_question is not None
    played_question.closes_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(
        milliseconds=1
    )
    response_context.db.commit()

    result = response_context.client.post(
        response_url(scenario),
        json={"choice_id": scenario.correct_choice_id},
    )

    assert result.status_code == 409
    assert result.json()["error"]["code"] == "response_deadline_passed"


def test_account_that_did_not_join_cannot_submit(
    response_context: ResponseContext,
) -> None:
    scenario = response_context.scenario
    unique = uuid4().hex
    outsider = Account(
        auth0_sub=f"test|response-outsider-{unique}",
        email=f"response-outsider-{unique}@example.test",
        display_name="Response test outsider",
        account_type="STUDENT",
    )
    response_context.db.add(outsider)
    response_context.db.commit()
    response_context.client.app.dependency_overrides[get_active_account] = (
        lambda: CurrentAccount(outsider.account_id, AccountRole.USER, True)
    )

    result = response_context.client.post(
        response_url(scenario),
        json={"choice_id": scenario.correct_choice_id},
    )

    assert result.status_code == 403
    assert result.json()["error"]["code"] == "not_session_participant"


def test_choice_from_another_question_is_rejected(
    response_context: ResponseContext,
) -> None:
    scenario = response_context.scenario
    result = response_context.client.post(
        response_url(scenario),
        json={"choice_id": scenario.other_question_choice_id},
    )

    assert result.status_code == 422
    assert result.json()["error"]["code"] == "choice_not_for_question"
