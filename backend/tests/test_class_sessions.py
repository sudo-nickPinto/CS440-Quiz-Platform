from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import CurrentAccount
from app.models import (
    Account,
    AccountRole,
    AnswerChoice,
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    LiveSession,
    LiveSessionStatus,
    MembershipStatus,
    Question,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from tests.test_session_api import create_quiz, session_client, use_account

__all__ = ["session_client"]


@pytest.fixture
def class_setup(
    session_client: tuple[TestClient, dict[str, CurrentAccount]],
) -> tuple[TestClient, dict[str, CurrentAccount], int]:
    """A class where author organizes, participant is an active member, and
    invited/removed hold those statuses. "other" stays outside the class."""
    client, accounts = session_client
    with client.app.state.database.session_factory() as db:
        for name in ["member", "invited", "removed"]:
            model = Account(
                auth0_sub=f"test|{name}",
                email=f"{name}@test.invalid",
                display_name=name.title(),
            )
            db.add(model)
            db.flush()
            accounts[name] = CurrentAccount(model.account_id, AccountRole.USER, True)

        class_ = Class(
            name="CS 440",
            created_by_id=accounts["author"].account_id,
            join_code="ABCD2345",
        )
        db.add(class_)
        db.flush()
        for name, role, status, via in [
            ("author", ClassRole.ORGANIZER, MembershipStatus.ACTIVE, JoinedVia.CREATOR),
            ("participant", ClassRole.MEMBER, MembershipStatus.ACTIVE, JoinedVia.CODE),
            ("member", ClassRole.MEMBER, MembershipStatus.ACTIVE, JoinedVia.CODE),
            ("invited", ClassRole.MEMBER, MembershipStatus.INVITED, JoinedVia.INVITE),
            ("removed", ClassRole.MEMBER, MembershipStatus.REMOVED, JoinedVia.CODE),
        ]:
            db.add(
                ClassMembership(
                    class_id=class_.class_id,
                    account_id=accounts[name].account_id,
                    role=role,
                    status=status,
                    joined_via=via,
                )
            )
        db.commit()
        class_id = class_.class_id
    return client, accounts, class_id


def host(client: TestClient, quiz_id: int, class_id: int | None):
    return client.post(f"/quizzes/{quiz_id}/sessions", json={"class_id": class_id})


def error_code(response) -> str:
    return response.json()["error"]["code"]


def test_organizer_creates_class_scoped_session(class_setup) -> None:
    client, _, class_id = class_setup
    quiz = create_quiz(client)

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 201
    assert response.json()["class_id"] == class_id


def test_plain_member_cannot_host_for_the_class(class_setup) -> None:
    client, accounts, class_id = class_setup
    use_account(client, accounts["member"])
    quiz = create_quiz(client)

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 403
    assert error_code(response) == "not_class_organizer"


def test_archived_class_cannot_start_sessions(class_setup) -> None:
    client, _, class_id = class_setup
    with client.app.state.database.session_factory() as db:
        class_ = db.get(Class, class_id)
        class_.archived_at = datetime(2026, 10, 1)
        class_.join_code = None
        class_.joining_open = False
        db.commit()
    quiz = create_quiz(client)

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 409
    assert error_code(response) == "class_archived"


def test_no_class_creates_an_open_session(class_setup) -> None:
    client, accounts, _ = class_setup
    quiz = create_quiz(client)

    with_null = host(client, quiz["quiz_id"], None)
    without_body = client.post(f"/quizzes/{quiz['quiz_id']}/sessions")

    assert with_null.status_code == 201
    assert with_null.json()["class_id"] is None
    assert without_body.status_code == 201
    assert without_body.json()["class_id"] is None
    # Anyone with the code can join an open session, as before classes.
    use_account(client, accounts["other"])
    joined = client.post(
        "/sessions/join", json={"join_code": with_null.json()["join_code"]}
    )
    assert joined.status_code == 201


def test_active_members_join_a_class_session(class_setup) -> None:
    client, accounts, class_id = class_setup
    quiz = create_quiz(client)
    session = host(client, quiz["quiz_id"], class_id).json()

    use_account(client, accounts["participant"])
    by_code = client.post("/sessions/join", json={"join_code": session["join_code"]})
    use_account(client, accounts["member"])
    by_id = client.post(f"/sessions/{session['session_id']}/join")

    assert by_code.status_code == 201
    assert by_id.status_code == 201
    listed = client.get(f"/classes/{class_id}/active-sessions")
    assert listed.status_code == 200
    assert [row["session_id"] for row in listed.json()] == [session["session_id"]]
    assert listed.json()[0]["joined"] is True
    assert listed.json()[0]["left"] is False


def test_departed_participant_is_labeled_and_cannot_rejoin(class_setup) -> None:
    client, accounts, class_id = class_setup
    quiz = create_quiz(client)
    session = host(client, quiz["quiz_id"], class_id).json()
    use_account(client, accounts["participant"])
    joined = client.post(
        "/sessions/join", json={"join_code": session["join_code"]}
    )
    assert joined.status_code == 201

    with client.app.state.database.session_factory() as db:
        participant = db.scalar(
            select(SessionParticipant).where(
                SessionParticipant.session_id == session["session_id"],
                SessionParticipant.account_id == accounts["participant"].account_id,
            )
        )
        assert participant is not None
        participant.left_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()

    listed = client.get(f"/classes/{class_id}/active-sessions")
    assert listed.status_code == 200
    assert listed.json()[0]["joined"] is False
    assert listed.json()[0]["left"] is True

    rejoin = client.post(f"/sessions/{session['session_id']}/join")
    assert rejoin.status_code == 409
    assert error_code(rejoin) == "session_already_joined"


def test_removed_member_cannot_answer_after_joining(class_setup) -> None:
    client, accounts, class_id = class_setup
    quiz = create_quiz(client)
    session = host(client, quiz["quiz_id"], class_id).json()
    use_account(client, accounts["participant"])
    joined = client.post(
        "/sessions/join", json={"join_code": session["join_code"]}
    )
    assert joined.status_code == 201

    now = datetime.now(UTC).replace(tzinfo=None)
    with client.app.state.database.session_factory() as db:
        live_session = db.get(LiveSession, session["session_id"])
        assert live_session is not None
        question = db.scalar(
            select(Question).where(
                Question.quiz_version_id == live_session.quiz_version_id,
                Question.question_order == 1,
            )
        )
        assert question is not None
        choice = db.scalar(
            select(AnswerChoice).where(
                AnswerChoice.question_id == question.question_id,
                AnswerChoice.choice_order == 1,
            )
        )
        assert choice is not None
        membership = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == accounts["participant"].account_id,
            )
        )
        assert membership is not None
        membership.status = MembershipStatus.REMOVED
        live_session.status = LiveSessionStatus.ACTIVE
        live_session.current_question_order = 1
        played = SessionQuestion(
            session_id=live_session.session_id,
            question_id=question.question_id,
            status=SessionQuestionStatus.OPEN,
            opened_at=now - timedelta(seconds=1),
            closes_at=now + timedelta(seconds=29),
        )
        db.add(played)
        db.commit()
        session_question_id = played.session_question_id
        choice_id = choice.choice_id

    response = client.post(
        f"/sessions/{session['session_id']}/questions/"
        f"{session_question_id}/responses",
        json={"choice_id": choice_id},
    )
    assert response.status_code == 403
    assert error_code(response) == "not_class_member"


@pytest.mark.parametrize("name", ["invited", "removed", "other"])
def test_invited_removed_and_outside_users_cannot_join(class_setup, name) -> None:
    client, accounts, class_id = class_setup
    quiz = create_quiz(client)
    session = host(client, quiz["quiz_id"], class_id).json()
    use_account(client, accounts[name])

    by_code = client.post("/sessions/join", json={"join_code": session["join_code"]})
    by_id = client.post(f"/sessions/{session['session_id']}/join")
    listed = client.get(f"/classes/{class_id}/active-sessions")

    assert by_code.status_code == 403
    assert error_code(by_code) == "not_class_member"
    assert by_id.status_code == 404
    assert error_code(by_id) == "session_not_found"
    assert listed.status_code == 404
    assert error_code(listed) == "class_not_found"


def test_open_session_cannot_be_joined_by_session_id(class_setup) -> None:
    client, accounts, _ = class_setup
    quiz = create_quiz(client)
    session = host(client, quiz["quiz_id"], None).json()
    use_account(client, accounts["participant"])

    response = client.post(f"/sessions/{session['session_id']}/join")

    assert response.status_code == 404
    assert error_code(response) == "session_not_found"
