from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.api.routes import notifications_live
from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import Base
from app.live.protocol import CloseCode, LiveCloseError
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.quiz import QuizVersion
from app.notifications import events
from tests.class_quiz_helpers import add_member, host_quiz, make_class, publish_quiz

URL = "/ws/notifications"


@pytest.fixture
def notification_client(
    monkeypatch,
) -> Iterator[tuple[TestClient, CurrentAccount, CurrentAccount]]:
    app = create_app(
        Settings(
            database_url="sqlite://",
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
        )
    )
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.database.engine)
        with app.state.database.session_factory() as db:
            first = Account(
                auth0_sub="auth0|first",
                email="first@example.com",
                display_name="First",
                is_active=True,
            )
            second = Account(
                auth0_sub="auth0|second",
                email="second@example.com",
                display_name="Second",
                is_active=True,
            )
            db.add_all([first, second])
            db.commit()
            accounts = {
                "first-token": CurrentAccount(first.account_id, AccountRole.USER, True),
                "second-token": CurrentAccount(
                    second.account_id, AccountRole.USER, True
                ),
            }

        def fake_authenticate(db, settings, token):
            if token not in accounts:
                raise LiveCloseError(CloseCode.UNAUTHORIZED, "invalid_token")
            return accounts[token]

        monkeypatch.setattr(notifications_live, "authenticate_token", fake_authenticate)
        yield client, accounts["first-token"], accounts["second-token"]


def _authenticate(socket, token: str) -> dict:
    socket.send_json({"type": "auth", "token": token})
    return socket.receive_json()


def test_socket_authenticates_and_receives_ready(notification_client) -> None:
    client, _, _ = notification_client
    with client.websocket_connect(URL) as socket:
        assert _authenticate(socket, "first-token") == {"type": "notifications_ready"}


@pytest.mark.parametrize(
    ("first_message", "code"),
    [
        ({"type": "auth"}, CloseCode.UNAUTHORIZED),
        ({"type": "auth", "token": "bad-token"}, CloseCode.UNAUTHORIZED),
        ({"type": "ping"}, CloseCode.MALFORMED),
    ],
    ids=["missing-token", "invalid-token", "not-auth"],
)
def test_bad_auth_closes_socket(notification_client, first_message, code) -> None:
    client, _, _ = notification_client
    with client.websocket_connect(URL) as socket:
        socket.send_json(first_message)
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
    assert closed.value.code == code


def test_send_to_accounts_reaches_every_socket_of_listed_accounts_only(
    notification_client,
) -> None:
    client, first, _ = notification_client
    hub = client.app.state.notification_hub
    event = {"type": "test_event", "value": 1}

    with (
        client.websocket_connect(URL) as tab_one,
        client.websocket_connect(URL) as tab_two,
        client.websocket_connect(URL) as other,
    ):
        _authenticate(tab_one, "first-token")
        _authenticate(tab_two, "first-token")
        _authenticate(other, "second-token")

        client.portal.call(
            hub.send_to_accounts, [first.account_id, first.account_id], event
        )

        assert tab_one.receive_json() == event
        assert tab_two.receive_json() == event
        # The other account got nothing: its next message is the pong.
        other.send_json({"type": "ping"})
        assert other.receive_json() == {"type": "pong"}
        # Each tab got the event exactly once despite the duplicate id.
        tab_one.send_json({"type": "ping"})
        assert tab_one.receive_json() == {"type": "pong"}


def test_ping_gets_pong(notification_client) -> None:
    client, _, _ = notification_client
    with client.websocket_connect(URL) as socket:
        _authenticate(socket, "first-token")
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}


# App events (app/notifications/events.py) over real HTTP routes.

EVENT_QUIZ = {
    "title": "Week 4",
    "questions": [
        {
            "question_text": "Ready?",
            "choices": [
                {"choice_text": "Yes", "is_correct": True},
                {"choice_text": "No", "is_correct": False},
            ],
        }
    ],
}


@pytest.fixture
def event_client(monkeypatch) -> Iterator[tuple[TestClient, dict, dict]]:
    """A class run by `faculty` with `owner` and `classmate` as members.

    Sockets authenticate with the account's name as the token, and
    `act(name)` picks the account HTTP requests run as.
    """
    app = create_app(
        Settings(
            database_url="sqlite://",
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
        )
    )
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.database.engine)
        accounts: dict[str, CurrentAccount] = {}
        with app.state.database.session_factory() as db:
            for name in ("faculty", "owner", "classmate", "outsider"):
                model = Account(
                    auth0_sub=f"auth0|{name}",
                    email=f"{name}@example.edu",
                    display_name=name.title(),
                    account_type="ADMINISTRATOR" if name == "faculty" else None,
                    is_active=True,
                )
                db.add(model)
                db.flush()
                accounts[name] = CurrentAccount(
                    model.account_id,
                    AccountRole.ADMIN if name == "faculty" else AccountRole.USER,
                    True,
                )
            db.commit()

        def fake_authenticate(db, settings, token):
            if token not in accounts:
                raise LiveCloseError(CloseCode.UNAUTHORIZED, "invalid_token")
            return accounts[token]

        monkeypatch.setattr(notifications_live, "authenticate_token", fake_authenticate)
        actor = {"value": accounts["owner"]}
        app.dependency_overrides[get_active_account] = lambda: actor["value"]

        class_id = make_class(client, accounts["faculty"].account_id, "CS 440")
        add_member(client, class_id, accounts["owner"].account_id)
        add_member(client, class_id, accounts["classmate"].account_id)

        def act(name: str) -> None:
            actor["value"] = accounts[name]

        yield client, {"class_id": class_id, "act": act}, accounts
        app.dependency_overrides.clear()


def _published_quiz(client: TestClient, class_id: int) -> tuple[int, int]:
    """Create and publish a quiz as the current account: (quiz_id, version_id)."""
    created = client.post(f"/classes/{class_id}/quizzes", json=EVENT_QUIZ)
    assert created.status_code == 201, created.text
    quiz_id = created.json()["quiz_id"]
    publish_quiz(client, quiz_id)
    with client.app.state.database.session_factory() as db:
        version_id = db.scalar(
            select(QuizVersion.quiz_version_id).where(QuizVersion.quiz_id == quiz_id)
        )
    return quiz_id, version_id


def _submit(client: TestClient, class_id: int, version_id: int) -> int:
    response = client.post(
        f"/classes/{class_id}/quiz-submissions",
        json={"quiz_version_id": version_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["submission_id"]


def _assert_nothing_pending(socket) -> None:
    socket.send_json({"type": "ping"})
    assert socket.receive_json() == {"type": "pong"}


def _submission_event(
    action: str,
    status: str,
    submission_id: int,
    class_id: int,
    quiz_id: int,
    actor: CurrentAccount,
) -> dict:
    return {
        "type": "submission_changed",
        "action": action,
        "submission_id": submission_id,
        "class_id": class_id,
        "quiz_id": quiz_id,
        "quiz_title": "Week 4",
        "class_name": "CS 440",
        "status": status,
        "actor_account_id": actor.account_id,
    }


def test_organizer_hears_member_submit_and_others_hear_nothing(event_client) -> None:
    client, ctx, accounts = event_client
    class_id = ctx["class_id"]
    quiz_id, version_id = _published_quiz(client, class_id)

    with (
        client.websocket_connect(URL) as faculty,
        client.websocket_connect(URL) as owner,
        client.websocket_connect(URL) as outsider,
    ):
        _authenticate(faculty, "faculty")
        _authenticate(owner, "owner")
        _authenticate(outsider, "outsider")

        submission_id = _submit(client, class_id, version_id)

        assert faculty.receive_json() == _submission_event(
            "submitted",
            "PENDING",
            submission_id,
            class_id,
            quiz_id,
            accounts["owner"],
        )
        _assert_nothing_pending(owner)
        _assert_nothing_pending(outsider)


@pytest.mark.parametrize(
    ("decision", "action"),
    [("APPROVED", "approved"), ("REJECTED", "rejected")],
)
def test_submitter_hears_decision(event_client, decision, action) -> None:
    client, ctx, accounts = event_client
    class_id = ctx["class_id"]
    quiz_id, version_id = _published_quiz(client, class_id)

    with (
        client.websocket_connect(URL) as faculty,
        client.websocket_connect(URL) as owner,
        client.websocket_connect(URL) as classmate,
        client.websocket_connect(URL) as outsider,
    ):
        _authenticate(faculty, "faculty")
        _authenticate(owner, "owner")
        _authenticate(classmate, "classmate")
        _authenticate(outsider, "outsider")

        submission_id = _submit(client, class_id, version_id)
        assert faculty.receive_json()["action"] == "submitted"

        ctx["act"]("faculty")
        response = client.patch(
            f"/classes/{class_id}/quiz-submissions/{submission_id}",
            json={"status": decision},
        )
        assert response.status_code == 200, response.text

        expected = _submission_event(
            action, decision, submission_id, class_id, quiz_id, accounts["faculty"]
        )
        assert owner.receive_json() == expected
        # The deciding organizer's own tabs update too.
        assert faculty.receive_json() == expected
        _assert_nothing_pending(classmate)
        _assert_nothing_pending(outsider)


def test_organizer_hears_withdraw(event_client) -> None:
    client, ctx, accounts = event_client
    class_id = ctx["class_id"]
    quiz_id, version_id = _published_quiz(client, class_id)

    with client.websocket_connect(URL) as faculty:
        _authenticate(faculty, "faculty")
        submission_id = _submit(client, class_id, version_id)
        assert faculty.receive_json()["action"] == "submitted"

        response = client.delete(
            f"/classes/{class_id}/quiz-submissions/{submission_id}"
        )
        assert response.status_code == 204

        assert faculty.receive_json() == _submission_event(
            "withdrawn",
            "WITHDRAWN",
            submission_id,
            class_id,
            quiz_id,
            accounts["owner"],
        )


def test_failed_notification_does_not_fail_the_request(
    event_client, monkeypatch, caplog
) -> None:
    client, ctx, _ = event_client
    _, version_id = _published_quiz(client, ctx["class_id"])

    def broken(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(events, "resolve_submission_changed", broken)

    _submit(client, ctx["class_id"], version_id)
    assert "Could not send submission_changed" in caplog.text


def test_members_hear_session_live_but_host_and_outsider_do_not(
    event_client,
) -> None:
    client, ctx, accounts = event_client
    class_id = ctx["class_id"]
    ctx["act"]("faculty")
    quiz_id, _ = _published_quiz(client, class_id)

    with (
        client.websocket_connect(URL) as faculty,
        client.websocket_connect(URL) as classmate,
        client.websocket_connect(URL) as owner,
        client.websocket_connect(URL) as outsider,
    ):
        _authenticate(faculty, "faculty")
        _authenticate(classmate, "classmate")
        _authenticate(owner, "owner")
        _authenticate(outsider, "outsider")

        response = host_quiz(client, quiz_id, members=[])
        assert response.status_code == 201, response.text
        session = response.json()

        expected = {
            "type": "session_live",
            "session_id": session["session_id"],
            "class_id": class_id,
            "class_name": "CS 440",
            "quiz_title": "Week 4",
            "host_name": "Faculty",
            "join_code": session["join_code"],
        }
        assert classmate.receive_json() == expected
        assert owner.receive_json() == expected
        _assert_nothing_pending(faculty)
        _assert_nothing_pending(outsider)
