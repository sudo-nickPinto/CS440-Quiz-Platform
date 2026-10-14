"""WebSocket tests for /ws/sessions/{id} (LIVE_PROTOCOL.md §8.5).

Tokens are real signed JWTs checked by the live auth code against a fake JWKS,
the same approach as test_auth.py. REST setup (quiz, session, joins) uses the
dependency override from test_session_api.py.
"""

import asyncio
import threading
from collections.abc import Iterator
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from starlette.websockets import WebSocketDisconnect

from app import accounts as accounts_module
from app import auth
from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import Base
from app.live.hub import LiveConnection, LiveHub
from app.live.protocol import CloseCode
from app.main import create_app
from app.models import Account, AccountRole
from tests.test_accounts import AUDIENCE, DOMAIN, PRIVATE_KEY, make_token

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
    assert sent == ['{"type": "session_state"}', '{"type": "question_opened"}']
