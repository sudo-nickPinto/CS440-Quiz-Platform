"""WebSocket tests for /ws/sessions/{id} (LIVE_PROTOCOL.md §8.5).

Tokens are real signed JWTs checked by the live auth code against a fake JWKS,
the same approach as test_auth.py. REST setup (quiz, session, joins) uses the
dependency override from test_session_api.py.
"""

import asyncio
import threading
import time
from collections.abc import Iterator
from types import SimpleNamespace

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect

from app import accounts as accounts_module
from app import auth
from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import Base
from app.api.routes import live as live_routes
from app.live.hub import LiveConnection, LiveHub
from app.live.protocol import CloseCode
from app.main import create_app
from app.models import (
    Account,
    AccountRole,
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    LiveSession,
    LiveSessionStatus,
    MembershipStatus,
    SessionParticipant,
)
from tests.test_accounts import AUDIENCE, DOMAIN, PRIVATE_KEY, make_token
from tests.class_quiz_helpers import (
    create_approved_quiz,
    host_quiz,
    post_class_quiz,
)

QUIZ_PAYLOAD = {
    "title": "Live Quiz",
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
NAMES = ["host", "alice", "bob", "outsider"]


@pytest.fixture
def live(monkeypatch) -> Iterator[tuple[TestClient, dict[str, CurrentAccount]]]:
    fake_jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(
            key=PRIVATE_KEY.public_key()
        )
    )
    monkeypatch.setattr(auth, "_jwks_client", lambda domain: fake_jwks)

    app = create_app(
        Settings(database_url="sqlite://", auth0_domain=DOMAIN, auth0_audience=AUDIENCE)
    )
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.database.engine)
        with app.state.database.engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE account_identity ("
                    " auth0_sub VARCHAR(255) NOT NULL PRIMARY KEY,"
                    " account_id INTEGER NOT NULL REFERENCES account (account_id))"
                )
            )
        people: dict[str, CurrentAccount] = {}
        with app.state.database.session_factory() as db:
            for name in NAMES:
                model = Account(
                    auth0_sub=f"test|{name}",
                    email=f"{name}@test.invalid",
                    display_name=name.title(),
                    # One preset avatar so the payloads carry a non-null value.
                    avatar_key="owl.sky" if name == "alice" else None,
                )
                db.add(model)
                db.flush()
                db.execute(
                    text(
                        "INSERT INTO account_identity (auth0_sub, account_id) "
                        "VALUES (:sub, :id)"
                    ),
                    {"sub": f"test|{name}", "id": model.account_id},
                )
                people[name] = CurrentAccount(model.account_id, AccountRole.USER, True)
            db.commit()
        serialize_db_calls(app)
        yield client, people


def serialize_db_calls(app) -> None:
    """In-memory SQLite is one shared connection, so concurrent hub DB calls
    (e.g. one answer's close check racing the next answer) would interleave
    transactions. MySQL gives each call its own connection; here we take turns.
    """
    lock = threading.Lock()
    factory = app.state.database.session_factory

    async def run_db(fn, *args, **kwargs):
        def call():
            with lock, factory() as db:
                return fn(db, *args, **kwargs)

        return await run_in_threadpool(call)

    app.state.live_hub.run_db = run_db


def as_account(client: TestClient, account: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: account


def make_session(client: TestClient, people: dict[str, CurrentAccount]) -> dict:
    as_account(client, people["host"])
    quiz = post_class_quiz(client, QUIZ_PAYLOAD)
    assert quiz.status_code == 201
    session = host_quiz(
        client,
        quiz.json()["quiz_id"],
        # Everyone but the outsider is in the class.
        members=[
            account.account_id
            for name, account in people.items()
            if name != "outsider"
        ],
    )
    assert session.status_code == 201
    return session.json()


def join(client: TestClient, account: CurrentAccount, join_code: str) -> dict:
    as_account(client, account)
    response = client.post("/sessions/join", json={"join_code": join_code})
    assert response.status_code == 201
    return response.json()


def ws_url(session_id: int) -> str:
    return f"/ws/sessions/{session_id}"


def authenticate(ws, name: str) -> dict:
    ws.send_json({"type": "auth", "token": make_token(sub=f"test|{name}")})
    return ws.receive_json()


def receive_until(ws, message_type: str) -> list[dict]:
    messages = []
    while True:
        message = ws.receive_json()
        messages.append(message)
        if message["type"] == message_type:
            return messages


def assert_closed_with(ws, code: int) -> None:
    with pytest.raises(WebSocketDisconnect) as closed:
        ws.receive_json()
    assert closed.value.code == code


def test_shared_countdown_opens_question_after_three_seconds(live):
    client, people = live
    session = make_session(client, people)
    sid = session["session_id"]
    join(client, people["alice"], session["join_code"])
    with client.websocket_connect(ws_url(sid)) as host, client.websocket_connect(ws_url(sid)) as alice:
        authenticate(host, "host")
        authenticate(alice, "alice")
        alice.send_json({"type": "start_countdown", "request_id": "denied"})
        assert receive_until(alice, "error")[-1]["code"] == "session_host_denied"
        started = time.monotonic()
        host.send_json({"type": "start_countdown", "request_id": "start"})
        assert receive_until(host, "countdown_tick")[-1]["number"] == 3
        assert receive_until(alice, "countdown_tick")[-1]["number"] == 3
        # Duplicate requests do not restart the clock or open twice.
        host.send_json({"type": "start_countdown", "request_id": "duplicate"})
        for number in (2, 1):
            assert receive_until(host, "countdown_tick")[-1]["number"] == number
            assert receive_until(alice, "countdown_tick")[-1]["number"] == number
        # A fresh participant connection gets the current beat in its snapshot.
        with client.websocket_connect(ws_url(sid)) as reconnected:
            assert authenticate(reconnected, "alice")["countdown"] == 1
            opened = receive_until(host, "question_opened")[-1]
            assert time.monotonic() - started >= 2.9
            assert receive_until(reconnected, "question_opened")[-1] == opened


def test_host_can_cancel_shared_countdown(live):
    client, people = live
    session = make_session(client, people)
    sid = session["session_id"]
    join(client, people["alice"], session["join_code"])
    with client.websocket_connect(ws_url(sid)) as host, client.websocket_connect(ws_url(sid)) as alice:
        authenticate(host, "host")
        authenticate(alice, "alice")
        host.send_json({"type": "start_countdown"})
        receive_until(alice, "countdown_tick")
        host.send_json({"type": "cancel_countdown"})
        receive_until(host, "countdown_cancelled")
        receive_until(alice, "countdown_cancelled")
        time.sleep(3.1)
        with client.websocket_connect(ws_url(sid)) as fresh:
            state = authenticate(fresh, "alice")
            assert state["countdown"] is None
            assert state["session"]["status"] == "LOBBY"
            assert state["current_question"] is None


def test_host_and_two_participants_play_one_question(live) -> None:
    client, people = live
    session = make_session(client, people)
    sid = session["session_id"]

    with client.websocket_connect(ws_url(sid)) as host:
        state = authenticate(host, "host")
        assert state["type"] == "session_state"
        assert state["role"] == "host"
        assert state["session"]["join_code"] == session["join_code"]

        # REST joins reach the connected host through the after-join hook.
        for name in ("alice", "bob"):
            joined = join(client, people[name], session["join_code"])
            event = host.receive_json()
            assert event == {
                "type": "participant_joined",
                "session_participant_id": joined["participant"][
                    "session_participant_id"
                ],
                "display_name": name.title(),
                "avatar_key": "owl.sky" if name == "alice" else None,
                "participant_count": 1 if name == "alice" else 2,
            }

        with (
            client.websocket_connect(ws_url(sid)) as alice,
            client.websocket_connect(ws_url(sid)) as bob,
        ):
            for ws, name in ((alice, "alice"), (bob, "bob")):
                state = authenticate(ws, name)
                assert state["type"] == "session_state"
                assert state["role"] == "participant"
                assert state["host_connected"] is True
                assert "join_code" not in state["session"]

            host.send_json(
                {"type": "open_question", "question_order": 1, "request_id": "o1"}
            )
            opened = receive_until(host, "question_opened")[-1]
            sqid = opened["session_question_id"]
            correct = opened["choices"][0]["choice_id"]
            for ws in (alice, bob):
                assert ws.receive_json()["type"] == "question_opened"

            for ws in (alice, bob):
                ws.send_json(
                    {
                        "type": "submit_answer",
                        "session_question_id": sqid,
                        "choice_id": correct,
                        "request_id": "a1",
                    }
                )
                assert ws.receive_json()["type"] == "ack"

            for ws in (alice, bob):
                assert ws.receive_json()["type"] == "question_closed"
                results = ws.receive_json()
                assert results["type"] == "question_results"
                assert results["me"]["is_correct"] is True
                assert len(results["leaderboard"]) == 2

            host_messages = receive_until(host, "question_results")
            assert [m["type"] for m in host_messages].count("question_closed") == 1
            # No duplicate close is queued behind the results.
            for ws in (host, alice, bob):
                ws.send_json({"type": "ping"})
                assert ws.receive_json() == {"type": "pong"}

        # Reconnecting gets a fresh snapshot first, with the closed question.
        with client.websocket_connect(ws_url(sid)) as alice_again:
            state = authenticate(alice_again, "alice")
            assert state["type"] == "session_state"
            assert state["current_question"] is None
            assert state["last_question"]["session_question_id"] == sqid
            assert state["last_question"]["question_text"] == "Ready?"
            assert state["last_results"]["me"]["is_correct"] is True


def test_invalid_token_closes_with_4401(live) -> None:
    client, people = live
    sid = make_session(client, people)["session_id"]
    with client.websocket_connect(ws_url(sid)) as ws:
        ws.send_json({"type": "auth", "token": "not-a-jwt"})
        assert_closed_with(ws, CloseCode.UNAUTHORIZED)


def test_expired_token_closes_with_4401(live) -> None:
    client, people = live
    sid = make_session(client, people)["session_id"]
    with client.websocket_connect(ws_url(sid)) as ws:
        ws.send_json({"type": "auth", "token": make_token(sub="test|host", exp_offset=-60)})
        assert_closed_with(ws, CloseCode.UNAUTHORIZED)


def skewed_token(sub: str, *, iat_offset: int = 0, exp_offset: int = 3600) -> str:
    now = int(time.time())
    claims = {
        "sub": sub,
        "aud": AUDIENCE,
        "iss": f"https://{DOMAIN}/",
        "iat": now + iat_offset,
        "exp": now + exp_offset,
    }
    return jwt.encode(claims, PRIVATE_KEY, algorithm="RS256")


@pytest.mark.parametrize(
    ("iat_offset", "exp_offset"),
    [(2, 3600), (0, -2)],
    ids=["issued-slightly-in-future", "expired-just-now"],
)
def test_small_clock_skew_is_tolerated_like_http(live, iat_offset, exp_offset) -> None:
    """The socket accepts the same small clock skew as HTTP."""
    client, people = live
    sid = make_session(client, people)["session_id"]
    token = skewed_token("test|host", iat_offset=iat_offset, exp_offset=exp_offset)

    client.app.dependency_overrides.clear()  # REST checks the real token too
    assert client.get("/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    with client.websocket_connect(ws_url(sid)) as ws:
        ws.send_json({"type": "auth", "token": token})
        assert ws.receive_json()["type"] == "session_state"


def test_token_issued_beyond_leeway_closes_with_4401(live) -> None:
    client, people = live
    sid = make_session(client, people)["session_id"]

    token = skewed_token(
        "test|host",
        iat_offset=auth.TOKEN_LEEWAY_SECONDS + 60,
    )

    with client.websocket_connect(ws_url(sid)) as ws:
        ws.send_json({"type": "auth", "token": token})
        assert_closed_with(ws, CloseCode.UNAUTHORIZED)


def test_idle_socket_closes_with_retryable_1001_not_1000(live, monkeypatch) -> None:
    # 1000 means "session over" to clients (§7); an idle drop must not.
    monkeypatch.setattr(live_routes, "IDLE_TIMEOUT_SECONDS", 0.2)
    client, people = live
    sid = make_session(client, people)["session_id"]
    with client.websocket_connect(ws_url(sid)) as ws:
        assert authenticate(ws, "host")["type"] == "session_state"
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
    assert closed.value.code == CloseCode.GOING_AWAY == 1001
    assert closed.value.reason == "idle_timeout"


def test_missing_token_closes_with_4401(live) -> None:
    client, people = live
    sid = make_session(client, people)["session_id"]
    with client.websocket_connect(ws_url(sid)) as ws:
        ws.send_json({"type": "auth"})
        assert_closed_with(ws, CloseCode.UNAUTHORIZED)


def test_first_message_not_auth_closes_with_4400(live) -> None:
    client, people = live
    sid = make_session(client, people)["session_id"]
    with client.websocket_connect(ws_url(sid)) as ws:
        ws.send_json({"type": "ping"})
        assert_closed_with(ws, CloseCode.MALFORMED)


def test_unverified_new_account_closes_with_4403_not_1011(live, monkeypatch) -> None:
    client, people = live
    sid = make_session(client, people)["session_id"]
    monkeypatch.setattr(
        accounts_module,
        "_fetch_profile",
        lambda domain, token: {"email": "new@test.invalid", "email_verified": False},
    )
    with client.websocket_connect(ws_url(sid)) as ws:
        ws.send_json({"type": "auth", "token": make_token(sub="auth0|brand-new")})
        assert_closed_with(ws, CloseCode.FORBIDDEN)


def test_inactive_account_closes_with_4403(live) -> None:
    client, people = live
    sid = make_session(client, people)["session_id"]
    with client.app.state.database.engine.begin() as conn:
        conn.execute(
            text("UPDATE account SET is_active = 0 WHERE account_id = :id"),
            {"id": people["host"].account_id},
        )
    with client.websocket_connect(ws_url(sid)) as ws:
        ws.send_json({"type": "auth", "token": make_token(sub="test|host")})
        assert_closed_with(ws, CloseCode.FORBIDDEN)


def test_non_member_closes_with_4403(live) -> None:
    client, people = live
    sid = make_session(client, people)["session_id"]
    with client.websocket_connect(ws_url(sid)) as ws:
        ws.send_json({"type": "auth", "token": make_token(sub="test|outsider")})
        assert_closed_with(ws, CloseCode.FORBIDDEN)


def test_removed_class_member_closes_with_4403_after_joining(live) -> None:
    client, people = live
    host_id = people["host"].account_id
    with client.app.state.database.session_factory() as db:
        db.get(Account, host_id).account_type = "ADMINISTRATOR"
        db.commit()
    people["host"] = CurrentAccount(host_id, AccountRole.ADMIN, True)
    with client.app.state.database.session_factory() as db:
        class_ = Class(
            name="Socket class",
            created_by_id=people["host"].account_id,
            join_code="WSCLASS1",
        )
        db.add(class_)
        db.flush()
        for name, role in (
            ("host", ClassRole.ORGANIZER),
            ("alice", ClassRole.MEMBER),
        ):
            db.add(
                ClassMembership(
                    class_id=class_.class_id,
                    account_id=people[name].account_id,
                    role=role,
                    status=MembershipStatus.ACTIVE,
                    joined_via=(
                        JoinedVia.CREATOR if name == "host" else JoinedVia.CODE
                    ),
                )
            )
        db.commit()
        class_id = class_.class_id

    as_account(client, people["host"])
    quiz = create_approved_quiz(client, class_id, QUIZ_PAYLOAD)
    session = client.post(
        f"/classes/{class_id}/quizzes/{quiz['quiz_id']}/sessions"
    )
    assert session.status_code == 201
    joined = join(client, people["alice"], session.json()["join_code"])
    assert joined["participant"]["account_id"] == people["alice"].account_id

    with client.app.state.database.session_factory() as db:
        membership = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == people["alice"].account_id,
            )
        )
        assert membership is not None
        membership.status = MembershipStatus.REMOVED
        db.commit()

    with client.websocket_connect(ws_url(session.json()["session_id"])) as ws:
        ws.send_json({"type": "auth", "token": make_token(sub="test|alice")})
        assert_closed_with(ws, CloseCode.FORBIDDEN)


def faculty_class_session(client: TestClient, people) -> tuple[int, dict]:
    """A class where host and bob are faculty organizers and alice is a
    member, with a lobby for an approved quiz that alice has joined."""
    for name in ("host", "bob"):
        account_id = people[name].account_id
        with client.app.state.database.session_factory() as db:
            db.get(Account, account_id).account_type = "ADMINISTRATOR"
            db.commit()
        people[name] = CurrentAccount(account_id, AccountRole.ADMIN, True)
    with client.app.state.database.session_factory() as db:
        class_ = Class(
            name="Eviction class",
            created_by_id=people["host"].account_id,
            join_code="WSCLASS2",
        )
        db.add(class_)
        db.flush()
        for name, role in (
            ("host", ClassRole.ORGANIZER),
            ("bob", ClassRole.ORGANIZER),
            ("alice", ClassRole.MEMBER),
        ):
            db.add(
                ClassMembership(
                    class_id=class_.class_id,
                    account_id=people[name].account_id,
                    role=role,
                    status=MembershipStatus.ACTIVE,
                    joined_via=JoinedVia.CODE,
                )
            )
        db.commit()
        class_id = class_.class_id

    as_account(client, people["host"])
    quiz = create_approved_quiz(client, class_id, QUIZ_PAYLOAD)
    session = client.post(f"/classes/{class_id}/quizzes/{quiz['quiz_id']}/sessions")
    assert session.status_code == 201
    join(client, people["alice"], session.json()["join_code"])
    return class_id, session.json()


def set_membership_status(client, class_id: int, account_id: int, status) -> None:
    with client.app.state.database.session_factory() as db:
        membership = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == account_id,
            )
        )
        membership.status = status
        db.commit()


def assert_eventually_closed_with(ws, code: int) -> list[dict]:
    """Read past any queued messages until the server closes the socket."""
    seen = []
    with pytest.raises(WebSocketDisconnect) as closed:
        while True:
            seen.append(ws.receive_json())
    assert closed.value.code == code
    return seen


def test_removed_host_cannot_reconnect(live) -> None:
    client, people = live
    class_id, session = faculty_class_session(client, people)
    set_membership_status(
        client, class_id, people["host"].account_id, MembershipStatus.REMOVED
    )

    with client.websocket_connect(ws_url(session["session_id"])) as ws:
        ws.send_json({"type": "auth", "token": make_token(sub="test|host")})
        assert_closed_with(ws, CloseCode.FORBIDDEN)


def test_host_of_an_old_session_without_a_class_cannot_connect(live) -> None:
    client, people = live
    _, session = faculty_class_session(client, people)
    with client.app.state.database.session_factory() as db:
        old = LiveSession(
            quiz_version_id=session["quiz_version_id"],
            host_id=people["host"].account_id,
            class_id=None,
            join_code="135790",
            status=LiveSessionStatus.LOBBY,
        )
        db.add(old)
        db.commit()
        old_id = old.session_id

    with client.websocket_connect(ws_url(old_id)) as ws:
        ws.send_json({"type": "auth", "token": make_token(sub="test|host")})
        assert_closed_with(ws, CloseCode.FORBIDDEN)


def test_host_removed_while_connected_is_disconnected(live) -> None:
    client, people = live
    class_id, session = faculty_class_session(client, people)
    sid = session["session_id"]
    hub = client.app.state.live_hub

    with client.websocket_connect(ws_url(sid)) as host_ws, client.websocket_connect(
        ws_url(sid)
    ) as alice_ws:
        assert authenticate(host_ws, "host")["type"] == "session_state"
        assert authenticate(alice_ws, "alice")["type"] == "session_state"

        as_account(client, people["bob"])
        removed = client.delete(
            f"/classes/{class_id}/members/{people['host'].account_id}"
        )
        assert removed.status_code == 204

        assert_eventually_closed_with(host_ws, CloseCode.FORBIDDEN)
        # The participant hears that the host is gone, as with any disconnect.
        status = receive_until(alice_ws, "host_status")[-1]
        assert status["connected"] is False
        assert not hub.host_connected(sid)


def test_participant_removed_while_connected_stops_getting_events(live) -> None:
    client, people = live
    class_id, session = faculty_class_session(client, people)
    sid = session["session_id"]
    hub = client.app.state.live_hub

    with client.websocket_connect(ws_url(sid)) as host_ws, client.websocket_connect(
        ws_url(sid)
    ) as alice_ws:
        assert authenticate(host_ws, "host")["type"] == "session_state"
        assert authenticate(alice_ws, "alice")["type"] == "session_state"

        as_account(client, people["host"])
        removed = client.delete(
            f"/classes/{class_id}/members/{people['alice'].account_id}"
        )
        assert removed.status_code == 204

        assert_eventually_closed_with(alice_ws, CloseCode.FORBIDDEN)
        assert people["alice"].account_id not in hub._sessions.get(sid, {})

    # Reconnecting is refused too.
    with client.websocket_connect(ws_url(sid)) as ws:
        ws.send_json({"type": "auth", "token": make_token(sub="test|alice")})
        assert_closed_with(ws, CloseCode.FORBIDDEN)


def test_participant_who_leaves_the_class_is_disconnected(live) -> None:
    client, people = live
    class_id, session = faculty_class_session(client, people)
    sid = session["session_id"]

    with client.websocket_connect(ws_url(sid)) as alice_ws:
        assert authenticate(alice_ws, "alice")["type"] == "session_state"

        as_account(client, people["alice"])
        assert client.delete(f"/classes/{class_id}/membership").status_code == 204

        assert_eventually_closed_with(alice_ws, CloseCode.FORBIDDEN)


def left_at(client, session_id: int, account_id: int):
    with client.app.state.database.session_factory() as db:
        return db.scalar(
            select(SessionParticipant.left_at).where(
                SessionParticipant.session_id == session_id,
                SessionParticipant.account_id == account_id,
            )
        )


def test_removing_a_lobby_participant_updates_the_host_count(live) -> None:
    client, people = live
    class_id, session = faculty_class_session(client, people)
    sid = session["session_id"]
    join(client, people["bob"], session["join_code"])

    with client.websocket_connect(ws_url(sid)) as host_ws:
        state = authenticate(host_ws, "host")
        assert state["participant_count"] == 2

        as_account(client, people["host"])
        removed = client.delete(
            f"/classes/{class_id}/members/{people['alice'].account_id}"
        )
        assert removed.status_code == 204

        event = receive_until(host_ws, "participant_left")[-1]
        assert event["display_name"] == "Alice"
        assert event["participant_count"] == 1

    assert left_at(client, sid, people["alice"].account_id) is not None
    assert left_at(client, sid, people["bob"].account_id) is None
    # A fresh snapshot shows the smaller lobby too.
    with client.websocket_connect(ws_url(sid)) as host_ws:
        assert authenticate(host_ws, "host")["participant_count"] == 1


def test_removing_the_last_unanswered_participant_closes_the_question(live) -> None:
    client, people = live
    class_id, session = faculty_class_session(client, people)
    sid = session["session_id"]
    join(client, people["bob"], session["join_code"])

    with (
        client.websocket_connect(ws_url(sid)) as host_ws,
        client.websocket_connect(ws_url(sid)) as bob_ws,
    ):
        authenticate(host_ws, "host")
        authenticate(bob_ws, "bob")
        host_ws.send_json(
            {"type": "open_question", "question_order": 1, "request_id": "o1"}
        )
        opened = receive_until(host_ws, "question_opened")[-1]
        sqid = opened["session_question_id"]
        assert receive_until(bob_ws, "question_opened")

        # Bob answers; Alice never does, so the question stays open.
        bob_ws.send_json(
            {
                "type": "submit_answer",
                "session_question_id": sqid,
                "choice_id": opened["choices"][0]["choice_id"],
                "request_id": "a1",
            }
        )
        assert bob_ws.receive_json()["type"] == "ack"
        progress = receive_until(host_ws, "answer_progress")[-1]
        assert (progress["answered_count"], progress["eligible_count"]) == (1, 2)

        as_account(client, people["host"])
        removed = client.delete(
            f"/classes/{class_id}/members/{people['alice'].account_id}"
        )
        assert removed.status_code == 204

        messages = receive_until(host_ws, "question_closed")
        closed = messages[-1]
        assert closed["reason"] == "ALL_ANSWERED"
        assert (closed["answered_count"], closed["eligible_count"]) == (1, 1)
        left = [m for m in messages if m["type"] == "participant_left"]
        assert left and left[0]["participant_count"] == 1
        assert receive_until(bob_ws, "question_closed")


def test_leaving_the_class_mid_question_also_frees_the_question(live) -> None:
    client, people = live
    class_id, session = faculty_class_session(client, people)
    sid = session["session_id"]
    join(client, people["bob"], session["join_code"])

    with client.websocket_connect(ws_url(sid)) as host_ws:
        authenticate(host_ws, "host")
        host_ws.send_json(
            {"type": "open_question", "question_order": 1, "request_id": "o1"}
        )
        opened = receive_until(host_ws, "question_opened")[-1]
        sqid = opened["session_question_id"]

        as_account(client, people["bob"])
        answered = client.post(
            f"/sessions/{sid}/questions/{sqid}/responses",
            json={"choice_id": opened["choices"][0]["choice_id"]},
        )
        assert answered.status_code == 201

        as_account(client, people["alice"])
        assert client.delete(f"/classes/{class_id}/membership").status_code == 204

        closed = receive_until(host_ws, "question_closed")[-1]
        assert closed["reason"] == "ALL_ANSWERED"
        assert closed["eligible_count"] == 1


def test_removing_a_member_leaves_other_classes_sessions_alone(live) -> None:
    client, people = live
    class_id, session = faculty_class_session(client, people)
    sid = session["session_id"]
    hub = client.app.state.live_hub

    with client.websocket_connect(ws_url(sid)) as alice_ws:
        assert authenticate(alice_ws, "alice")["type"] == "session_state"
        # A class with no live sessions: nothing to close.
        other_class = Class(
            name="Other", created_by_id=people["host"].account_id, join_code="OTHER123"
        )
        with client.app.state.database.session_factory() as db:
            db.add(other_class)
            db.commit()
            other_id = other_class.class_id
        client.portal.call(hub.evict_class_member, other_id, people["alice"].account_id)

        assert people["alice"].account_id in hub._sessions[sid]


def test_unknown_session_closes_with_4404(live) -> None:
    client, _ = live
    with client.websocket_connect(ws_url(9999)) as ws:
        ws.send_json({"type": "auth", "token": make_token(sub="test|host")})
        assert_closed_with(ws, CloseCode.NOT_FOUND)


class FakeSocket:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, data: str) -> None:
        self.sent.append(data)

    async def close(self, code: int, reason: str = "") -> None:
        pass


def test_broadcast_during_snapshot_is_delivered_after_session_state() -> None:
    """A broadcast racing the snapshot build must queue behind session_state."""

    async def scenario() -> list[str]:
        hub = LiveHub(SimpleNamespace())
        socket = FakeSocket()
        conn = LiveConnection(
            websocket=socket,
            session_id=1,
            account=CurrentAccount(1, AccountRole.USER, True),
            role="participant",
            session_participant_id=10,
        )

        async def slow_snapshot() -> dict:
            # The socket is registered now, so this broadcast targets it.
            racing = asyncio.create_task(hub.broadcast(1, {"type": "question_opened"}))
            await asyncio.sleep(0.01)
            assert not racing.done()
            return {"type": "session_state"}

        await hub.connect(conn, slow_snapshot)
        await asyncio.sleep(0.01)
        return socket.sent

    sent = asyncio.run(scenario())
    assert sent == ['{"type": "session_state", "countdown": null}', '{"type": "question_opened"}']
