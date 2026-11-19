"""The live WebSocket working with REST and the database, on migrated MySQL.

Covers what tests/test_live_host_controls.py does not run on MySQL: joins and
answers sent over REST reaching open sockets (PR #38), the snapshot a
reconnecting tab rebuilds from the stored game (PRs #38 and #47), socket
sign-in through the real account lookup (PRs #21 and #38), and the class
rules on joining, answering and connecting (PR #61).
"""

import jwt
from sqlalchemy import func, select, text

from app import accounts
from app.auth import get_active_account
from app.live.protocol import CloseCode
from app.models import (
    Account,
    LiveSessionStatus,
    MembershipStatus,
    Response,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from tests.class_quiz_helpers import add_member
from tests.integration.live_support import (  # noqa: F401
    bearer,
    mysql_live,
    stored_session,
)
from tests.test_accounts import make_token
from tests.test_live_host_controls import (
    answer,
    as_account,
    closed_code,
    connect,
    join,
    make_session,
    open_question,
    receive_until,
)


def socket_close_code(client, session_id: int, token: str) -> int:
    with client.websocket_connect(f"/ws/sessions/{session_id}") as ws:
        ws.send_json({"type": "auth", "token": token})
        return closed_code(ws)


def assert_quiet(*sockets) -> None:
    """Nothing else is queued on these sockets: the next reply is the pong."""
    for ws in sockets:
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}


def test_rest_joins_and_answers_drive_the_live_game(mysql_live) -> None:
    client, people = mysql_live
    session = make_session(client, people)
    sid = session["session_id"]

    host_cm, host, host_state = connect(client, sid, "host")
    assert host_state["role"] == "host"
    assert host_state["session"]["join_code"] == session["join_code"]
    assert host_state["participant_count"] == 0

    # Joining is REST, by code or by id; the host's socket hears each join.
    join(client, people["alice"], session["join_code"])
    as_account(client, people["bob"])
    assert client.post(f"/sessions/{sid}/join").status_code == 201
    joined = [host.receive_json() for _ in range(2)]
    assert [
        (e["type"], e["display_name"], e["participant_count"]) for e in joined
    ] == [("participant_joined", "Alice", 1), ("participant_joined", "Bob", 2)]

    alice_cm, alice, alice_state = connect(client, sid, "alice")
    assert alice_state["role"] == "participant"
    assert alice_state["participant_count"] == 2
    assert alice_state["host_connected"] is True
    assert "join_code" not in alice_state["session"]
    bob_cm, bob, _ = connect(client, sid, "bob")

    q1 = open_question(host, 1)
    sqid = q1["session_question_id"]
    for ws in (alice, bob):
        assert ws.receive_json()["type"] == "question_opened"

    # Alice answers over her socket; the host sees the progress.
    answer(alice, q1, correct=True)
    progress = receive_until(host, "answer_progress")[-1]
    assert (progress["answered_count"], progress["eligible_count"]) == (1, 2)

    # A second tab replaces her first socket and rebuilds from the database.
    alice2_cm, alice2, again = connect(client, sid, "alice")
    assert closed_code(alice) == CloseCode.REPLACED
    alice_cm.__exit__(None, None, None)
    assert again["current_question"]["session_question_id"] == sqid
    assert again["my_answer"]["choice_id"] == q1["choices"][0]["choice_id"]

    # Bob answers over REST; the receipt hides correctness until the close.
    as_account(client, people["bob"])
    receipt = client.post(
        f"/sessions/{sid}/questions/{sqid}/responses",
        json={"choice_id": q1["choices"][1]["choice_id"]},
    )
    assert receipt.status_code == 201
    assert set(receipt.json()) == {
        "response_id",
        "session_question_id",
        "choice_id",
        "submitted_at",
    }

    # That REST answer was the last one, so the question closes for everyone,
    # once.
    host_msgs = receive_until(host, "question_results")
    progress = [m for m in host_msgs if m["type"] == "answer_progress"]
    assert (progress[-1]["answered_count"], progress[-1]["eligible_count"]) == (2, 2)
    closes = [m for m in host_msgs if m["type"] == "question_closed"]
    assert [(c["reason"], c["answered_count"]) for c in closes] == [
        ("ALL_ANSWERED", 2)
    ]
    for ws, scored in ((alice2, True), (bob, False)):
        msgs = receive_until(ws, "question_results")
        assert [m["type"] for m in msgs] == ["question_closed", "question_results"]
        assert msgs[0]["reason"] == "ALL_ANSWERED"
        assert (msgs[-1]["me"]["points_awarded"] > 0) is scored
    assert_quiet(host, alice2, bob)

    with client.app.state.database.session_factory() as db:
        stored = db.execute(
            select(Account.display_name, Response.is_correct, Response.points_awarded)
            .join(
                SessionParticipant,
                SessionParticipant.session_participant_id
                == Response.session_participant_id,
            )
            .join(Account, Account.account_id == SessionParticipant.account_id)
            .where(Response.session_question_id == sqid)
            .order_by(Account.display_name)
        ).all()
        question = db.get(SessionQuestion, sqid)
        assert question.status == SessionQuestionStatus.CLOSED
        assert question.closed_at is not None
    assert [(name, correct) for name, correct, _ in stored] == [
        ("Alice", True),
        ("Bob", False),
    ]
    assert stored[0][2] > 0 and stored[1][2] == 0
    live = stored_session(client, sid)
    assert live.status == LiveSessionStatus.ACTIVE
    assert live.current_question_order == 1
    assert live.started_at is not None

    # Bob reloads between questions and gets the last results back.
    bob_cm.__exit__(None, None, None)
    bob_cm, bob, state = connect(client, sid, "bob")
    assert state["session"]["status"] == "ACTIVE"
    assert state["current_question"] is None
    assert state["last_question"]["session_question_id"] == sqid
    assert state["last_results"]["me"]["points_awarded"] == 0
    for cm in (host_cm, alice2_cm, bob_cm):
        cm.__exit__(None, None, None)


def test_socket_sign_in_uses_the_real_account_lookup(mysql_live, monkeypatch) -> None:
    client, people = mysql_live
    session = make_session(client, people)
    sid = session["session_id"]
    profiles = {
        "auth0|newcomer": {
            "email": "newcomer@test.invalid",
            "email_verified": True,
            "name": "Newcomer",
        },
        "auth0|unverified": {
            "email": "unverified@test.invalid",
            "email_verified": False,
            "name": "Unverified",
        },
    }

    def fetch_profile(domain: str, token: str) -> dict:
        # Stands in for Auth0's /userinfo, keyed by the token's login.
        sub = jwt.decode(token, options={"verify_signature": False})["sub"]
        return dict(profiles[sub])

    monkeypatch.setattr(accounts, "_fetch_profile", fetch_profile)

    # A first-ever login over the socket creates the account and its login
    # row, then the class check turns them away.
    newcomer = socket_close_code(client, sid, make_token(sub="auth0|newcomer"))
    assert newcomer == CloseCode.FORBIDDEN
    with client.app.state.database.engine.connect() as conn:
        created = conn.execute(
            text(
                "SELECT a.email, a.display_name, i.auth0_sub FROM account a "
                "JOIN account_identity i ON i.account_id = a.account_id "
                "WHERE a.email = 'newcomer@test.invalid'"
            )
        ).all()
    assert [tuple(row) for row in created] == [
        ("newcomer@test.invalid", "Newcomer", "auth0|newcomer")
    ]

    # An unverified email is refused before anything is stored.
    unverified = socket_close_code(client, sid, make_token(sub="auth0|unverified"))
    assert unverified == CloseCode.FORBIDDEN
    with client.app.state.database.session_factory() as db:
        assert db.scalar(
            select(func.count(Account.account_id)).where(
                Account.email == "unverified@test.invalid"
            )
        ) == 0

    # Bad and expired tokens are 4401; an unknown session is 4404.
    assert socket_close_code(
        client, sid, make_token(sub="test|alice", audience="someone-else")
    ) == CloseCode.UNAUTHORIZED
    assert socket_close_code(
        client, sid, make_token(sub="test|alice", exp_offset=-3600)
    ) == CloseCode.UNAUTHORIZED
    assert socket_close_code(
        client, sid + 10_000, make_token(sub="test|alice")
    ) == CloseCode.NOT_FOUND

    # A deactivated member is turned away by the socket and by REST alike.
    with client.app.state.database.session_factory() as db:
        db.get(Account, people["alice"].account_id).is_active = False
        db.commit()
    assert socket_close_code(
        client, sid, make_token(sub="test|alice")
    ) == CloseCode.FORBIDDEN
    client.app.dependency_overrides.pop(get_active_account, None)
    refused = client.post(
        "/sessions/join",
        json={"join_code": session["join_code"]},
        headers=bearer("alice"),
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "inactive_account"


def test_class_membership_gates_joining_answering_and_sockets(mysql_live) -> None:
    client, people = mysql_live
    session = make_session(client, people)
    sid = session["session_id"]
    class_id = session["class_id"]
    assert class_id is not None

    # Someone outside the class can't find, join or watch the session.
    as_account(client, people["outsider"])
    by_code = client.post("/sessions/join", json={"join_code": session["join_code"]})
    assert by_code.status_code == 403
    assert by_code.json()["error"]["code"] == "not_class_member"
    by_id = client.post(f"/sessions/{sid}/join")
    assert by_id.status_code == 404
    assert by_id.json()["error"]["code"] == "session_not_found"
    assert client.get(f"/classes/{class_id}/active-sessions").status_code == 404
    assert socket_close_code(
        client, sid, make_token(sub="test|outsider")
    ) == CloseCode.FORBIDDEN

    # A member sees it on the class page and joins with the Live button.
    as_account(client, people["alice"])
    listed = client.get(f"/classes/{class_id}/active-sessions").json()
    assert [(row["session_id"], row["joined"], row["is_host"]) for row in listed] == [
        (sid, False, False)
    ]
    assert client.post(f"/sessions/{sid}/join").status_code == 201
    listed = client.get(f"/classes/{class_id}/active-sessions").json()
    assert [(row["session_id"], row["joined"]) for row in listed] == [(sid, True)]
    join(client, people["bob"], session["join_code"])

    host_cm, host, _ = connect(client, sid, "host")
    q1 = open_question(host, 1)
    sqid = q1["session_question_id"]

    # Alice is removed from the class mid-question: her answer is refused
    # and not stored, and she can't reconnect.
    add_member(client, class_id, people["alice"].account_id, MembershipStatus.REMOVED)
    as_account(client, people["alice"])
    refused = client.post(
        f"/sessions/{sid}/questions/{sqid}/responses",
        json={"choice_id": q1["choices"][0]["choice_id"]},
    )
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "not_class_member"
    assert socket_close_code(
        client, sid, make_token(sub="test|alice")
    ) == CloseCode.FORBIDDEN

    # Bob, still a member, answers normally.
    as_account(client, people["bob"])
    accepted = client.post(
        f"/sessions/{sid}/questions/{sqid}/responses",
        json={"choice_id": q1["choices"][0]["choice_id"]},
    )
    assert accepted.status_code == 201
    with client.app.state.database.session_factory() as db:
        answered_by = db.scalars(
            select(SessionParticipant.account_id)
            .join(
                Response,
                Response.session_participant_id
                == SessionParticipant.session_participant_id,
            )
            .where(Response.session_question_id == sqid)
        ).all()
    assert answered_by == [people["bob"].account_id]
    host_cm.__exit__(None, None, None)
