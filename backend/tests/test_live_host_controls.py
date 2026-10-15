"""End-to-end WebSocket tests for the host controls (skip, end, cancel) and leave.

Each test runs on in-memory SQLite and, when TEST_DATABASE_URL is set, again on
the migrated MySQL test database, where the hub's DB calls really run
concurrently. Tokens are real signed JWTs, as in test_live_websocket.py.
"""

import os
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app import auth
from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import Base
from app.live.protocol import CloseCode
from app.main import create_app
from app.models import Account, AccountRole
from tests.integration.conftest import cleanup_database
from tests.test_accounts import AUDIENCE, DOMAIN, PRIVATE_KEY, make_token
from tests.test_live_websocket import serialize_db_calls

QUIZ_PAYLOAD = {
    "title": "Host Controls Quiz",
    "questions": [
        {
            "question_text": f"Question {n}?",
            "time_limit_seconds": 30,
            "choices": [
                {"choice_text": "Right", "is_correct": True},
                {"choice_text": "Wrong", "is_correct": False},
            ],
        }
        for n in (1, 2, 3)
    ],
}
NAMES = ["host", "alice", "bob", "outsider"]


def _mysql_url() -> str:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run the MySQL variant.")
    parsed = make_url(url)
    if not parsed.drivername.startswith("mysql") or "test" not in (
        parsed.database or ""
    ):
        pytest.fail("TEST_DATABASE_URL must be a MySQL database named *test*.")
    return url


@pytest.fixture(params=["sqlite", "mysql"])
def live(request, monkeypatch) -> Iterator[tuple[TestClient, dict[str, CurrentAccount]]]:
    fake_jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(
            key=PRIVATE_KEY.public_key()
        )
    )
    monkeypatch.setattr(auth, "_jwks_client", lambda domain: fake_jwks)

    mysql = request.param == "mysql"
    database_url = _mysql_url() if mysql else "sqlite://"
    app = create_app(
        Settings(database_url=database_url, auth0_domain=DOMAIN, auth0_audience=AUDIENCE)
    )
    with TestClient(app) as client:
        if mysql:
            cleanup_database(app)
        else:
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
        if not mysql:
            serialize_db_calls(app)
        try:
            yield client, people
        finally:
            app.dependency_overrides.clear()
            if mysql:
                cleanup_database(app)


# Helpers ---------------------------------------------------------------------


def as_account(client: TestClient, account: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: account


def make_session(client: TestClient, people: dict[str, CurrentAccount]) -> dict:
    as_account(client, people["host"])
    quiz = client.post("/quizzes", json=QUIZ_PAYLOAD)
    assert quiz.status_code == 201
    session = client.post(f"/quizzes/{quiz.json()['quiz_id']}/sessions")
    assert session.status_code == 201
    return session.json()


def join(client: TestClient, account: CurrentAccount, join_code: str) -> dict:
    as_account(client, account)
    response = client.post("/sessions/join", json={"join_code": join_code})
    assert response.status_code == 201
    return response.json()


def connect(client: TestClient, session_id: int, name: str):
    ws = client.websocket_connect(f"/ws/sessions/{session_id}")
    socket = ws.__enter__()
    socket.send_json({"type": "auth", "token": make_token(sub=f"test|{name}")})
    state = socket.receive_json()
    assert state["type"] == "session_state", state
    return ws, socket, state


def receive_until(ws, message_type: str) -> list[dict]:
    messages = []
    while True:
        message = ws.receive_json()
        messages.append(message)
        if message["type"] == message_type:
            return messages


def closed_code(ws) -> int:
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect) as closed:
        while True:
            ws.receive_json()
    return closed.value.code


def open_question(host, order: int) -> dict:
    host.send_json({"type": "open_question", "question_order": order})
    return receive_until(host, "question_opened")[-1]


def answer(ws, opened: dict, *, correct: bool = True) -> dict:
    choice = opened["choices"][0 if correct else 1]["choice_id"]
    ws.send_json(
        {
            "type": "submit_answer",
            "session_question_id": opened["session_question_id"],
            "choice_id": choice,
        }
    )
    ack = ws.receive_json()
    assert ack["type"] == "ack", ack
    return ack


# Tests -----------------------------------------------------------------------


def test_full_game_with_skip_auto_close_and_end(live) -> None:
    """The Sunday demo: join, skip Q1, everyone answers Q2, end during Q3."""
    client, people = live
    session = make_session(client, people)
    sid = session["session_id"]

    host_cm, host, _ = connect(client, sid, "host")
    joined = {
        name: join(client, people[name], session["join_code"])["participant"]
        for name in ("alice", "bob")
    }
    for _ in range(2):
        assert host.receive_json()["type"] == "participant_joined"
    alice_cm, alice, _ = connect(client, sid, "alice")
    bob_cm, bob, _ = connect(client, sid, "bob")

    # Q1: the host skips before anyone answers.
    q1 = open_question(host, 1)
    for ws in (alice, bob):
        assert ws.receive_json()["type"] == "question_opened"
    host.send_json(
        {
            "type": "close_question",
            "session_question_id": q1["session_question_id"],
            "request_id": "skip-1",
        }
    )
    host_msgs = receive_until(host, "question_results")
    assert host_msgs[0] == {
        "type": "ack",
        "request_id": "skip-1",
        "session_question_id": q1["session_question_id"],
    }
    closed = [m for m in host_msgs if m["type"] == "question_closed"]
    assert len(closed) == 1 and closed[0]["reason"] == "HOST"
    assert closed[0]["answered_count"] == 0
    for ws in (alice, bob):
        assert ws.receive_json()["reason"] == "HOST"
        results = ws.receive_json()
        assert results["type"] == "question_results"
        assert results["me"]["points_awarded"] == 0

    # Q2: both answer, so it closes on its own.
    q2 = open_question(host, 2)
    for ws in (alice, bob):
        assert ws.receive_json()["type"] == "question_opened"
    answer(alice, q2, correct=True)
    answer(bob, q2, correct=False)
    closed = [
        m for m in receive_until(host, "question_results") if m["type"] == "question_closed"
    ]
    assert [m["reason"] for m in closed] == ["ALL_ANSWERED"]
    for ws in (alice, bob):
        assert ws.receive_json()["reason"] == "ALL_ANSWERED"
        assert ws.receive_json()["type"] == "question_results"

    # Q3: Alice answers, then the host ends the game with Q3 still open.
    q3 = open_question(host, 3)
    for ws in (alice, bob):
        assert ws.receive_json()["type"] == "question_opened"
    answer(alice, q3, correct=True)
    host.send_json({"type": "end_session", "request_id": "end"})

    host_msgs = receive_until(host, "session_ended")
    types = [m["type"] for m in host_msgs]
    assert {"type": "ack", "request_id": "end"} in host_msgs
    # Close, results, then the end, in that order, each exactly once.
    tail = [t for t in types if t in ("question_closed", "question_results", "session_ended")]
    assert tail == ["question_closed", "question_results", "session_ended"]
    assert host_msgs[types.index("question_closed")]["reason"] == "HOST"
    host_end = host_msgs[-1]
    assert host_end["reason"] == "COMPLETED"
    assert [
        (row["display_name"], row["total_score"] > 0, row["correct_count"], row["final_rank"])
        for row in host_end["standings"]
    ] == [("Alice", True, 2, 1), ("Bob", False, 0, 2)]

    for ws, name in ((alice, "alice"), (bob, "bob")):
        msgs = receive_until(ws, "session_ended")
        assert [m["type"] for m in msgs] == [
            "question_closed",
            "question_results",
            "session_ended",
        ]
        ended = msgs[-1]
        assert ended["reason"] == "COMPLETED"
        assert ended["me"]["session_participant_id"] == (
            joined[name]["session_participant_id"]
        )
        assert [e["display_name"] for e in ended["leaderboard"]] == ["Alice", "Bob"]
        assert "standings" not in ended
        assert set(ended["leaderboard"][0]) == {"display_name", "total_score", "final_rank"}

    # Every socket is closed normally once the game is over.
    for ws in (host, alice, bob):
        assert closed_code(ws) == CloseCode.NORMAL
    for cm in (host_cm, alice_cm, bob_cm):
        cm.__exit__(None, None, None)

    # The final results survive a page reload through REST.
    as_account(client, people["host"])
    rest = client.get(f"/sessions/{sid}/results")
    assert rest.status_code == 200
    assert rest.json()["standings"] == host_end["standings"]
    as_account(client, people["bob"])
    rest = client.get(f"/sessions/{sid}/results").json()
    assert rest["me"]["display_name"] == "Bob"
    assert rest["leaderboard"][0]["display_name"] == "Alice"

    # Reconnecting to a finished session shows the final screen (4410).
    with client.websocket_connect(f"/ws/sessions/{sid}") as late:
        late.send_json({"type": "auth", "token": make_token(sub="test|alice")})
        assert closed_code(late) == CloseCode.SESSION_OVER


def test_participant_leaves_and_host_is_told(live) -> None:
    client, people = live
    session = make_session(client, people)
    sid = session["session_id"]
    host_cm, host, _ = connect(client, sid, "host")
    for name in ("alice", "bob"):
        join(client, people[name], session["join_code"])
        assert host.receive_json()["type"] == "participant_joined"
    bob_cm, bob, _ = connect(client, sid, "bob")

    bob.send_json({"type": "leave", "request_id": "bye"})
    assert bob.receive_json() == {"type": "ack", "request_id": "bye"}
    assert closed_code(bob) == CloseCode.NORMAL
    bob_cm.__exit__(None, None, None)

    left = host.receive_json()
    assert left["type"] == "participant_left"
    assert left["display_name"] == "Bob"
    assert left["participant_count"] == 1

    # Having left, Bob can't come back on the same membership.
    with client.websocket_connect(f"/ws/sessions/{sid}") as again:
        again.send_json({"type": "auth", "token": make_token(sub="test|bob")})
        assert closed_code(again) == CloseCode.FORBIDDEN

    host.send_json({"type": "ping"})
    assert host.receive_json() == {"type": "pong"}
    host_cm.__exit__(None, None, None)


def test_host_cancels_in_lobby(live) -> None:
    client, people = live
    session = make_session(client, people)
    sid = session["session_id"]
    host_cm, host, _ = connect(client, sid, "host")
    join(client, people["alice"], session["join_code"])
    assert host.receive_json()["type"] == "participant_joined"
    alice_cm, alice, _ = connect(client, sid, "alice")

    host.send_json({"type": "cancel_session", "request_id": "c"})
    assert host.receive_json() == {"type": "ack", "request_id": "c"}
    for ws in (host, alice):
        ended = ws.receive_json()
        assert ended["type"] == "session_ended"
        assert ended["reason"] == "CANCELLED"
        assert closed_code(ws) == CloseCode.NORMAL
    for cm in (host_cm, alice_cm):
        cm.__exit__(None, None, None)

    as_account(client, people["host"])
    rest = client.get(f"/sessions/{sid}/results").json()
    assert rest["status"] == "CANCELLED"
    assert rest["standings"] == []


def test_controls_are_host_only_and_errors_keep_the_socket(live) -> None:
    client, people = live
    session = make_session(client, people)
    sid = session["session_id"]
    host_cm, host, _ = connect(client, sid, "host")
    join(client, people["alice"], session["join_code"])
    assert host.receive_json()["type"] == "participant_joined"
    alice_cm, alice, _ = connect(client, sid, "alice")

    # Ending before the quiz starts is refused; cancel is the lobby action.
    host.send_json({"type": "end_session", "request_id": "e"})
    error = host.receive_json()
    assert (error["type"], error["code"], error["request_id"]) == (
        "error",
        "session_not_started",
        "e",
    )
    host.send_json({"type": "leave"})
    assert host.receive_json()["code"] == "session_participant_denied"

    q1 = open_question(host, 1)
    assert alice.receive_json()["type"] == "question_opened"
    for command in (
        {"type": "close_question", "session_question_id": q1["session_question_id"]},
        {"type": "end_session"},
        {"type": "cancel_session"},
    ):
        alice.send_json({**command, "request_id": "nope"})
        error = alice.receive_json()
        assert (error["type"], error["code"]) == ("error", "session_host_denied")

    # Cancelling an active game is refused; ending it is the way out.
    host.send_json({"type": "cancel_session"})
    assert host.receive_json()["code"] == "session_not_cancellable"

    # Nothing above closed Q1 or the sockets.
    for ws in (host, alice):
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}

    # A malformed control message is still a protocol error (4400).
    alice.send_json({"type": "close_question"})
    assert closed_code(alice) == CloseCode.MALFORMED
    for cm in (host_cm, alice_cm):
        cm.__exit__(None, None, None)


def test_results_rest_rejects_outsiders_and_unfinished_sessions(live) -> None:
    client, people = live
    session = make_session(client, people)
    sid = session["session_id"]
    join(client, people["alice"], session["join_code"])

    as_account(client, people["host"])
    response = client.get(f"/sessions/{sid}/results")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "results_not_ready"

    as_account(client, people["outsider"])
    response = client.get(f"/sessions/{sid}/results")
    assert response.status_code == 403
