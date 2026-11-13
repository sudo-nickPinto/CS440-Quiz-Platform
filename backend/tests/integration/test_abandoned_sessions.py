"""Auto-ending live sessions whose host is gone (PR #53), on migrated MySQL.

The reaper's passes run through the hub in the app's own event loop
(client.portal), against real sockets and real database rows, so these cover
the clock in LiveHub, abandon_session's transaction, and the broadcasts that
follow it together.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select

from app.errors import APIError
from app.live.protocol import CloseCode
from app.models import (
    Account,
    LiveSessionStatus,
    Result,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.services.session_end import abandon_session, end_session
from tests.integration.live_support import (  # noqa: F401
    live_app,
    mysql_live,
    stored_session,
    wait_for_host_to_leave,
    wait_until,
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


def reap(client, abandon_after_seconds: float) -> None:
    """Run one reaper pass, as the background loop would."""
    hub = client.app.state.live_hub
    client.portal.call(hub.reap_abandoned, abandon_after_seconds)


def result_rows(client, session_id: int) -> list[tuple[str, int, int, int]]:
    """(display name, total, correct, rank) for every stored Result row."""
    with client.app.state.database.session_factory() as db:
        rows = db.execute(
            select(
                Account.display_name,
                Result.total_score,
                Result.correct_count,
                Result.final_rank,
            )
            .join(
                SessionParticipant,
                SessionParticipant.session_participant_id
                == Result.session_participant_id,
            )
            .join(Account, Account.account_id == SessionParticipant.account_id)
            .where(SessionParticipant.session_id == session_id)
            .order_by(Result.final_rank, Account.display_name)
        ).all()
    return [tuple(row) for row in rows]


def assert_session_over(client, session_id: int, name: str) -> None:
    """A fresh socket to an ended session is sent to the final screen."""
    with client.websocket_connect(f"/ws/sessions/{session_id}") as late:
        late.send_json({"type": "auth", "token": make_token(sub=f"test|{name}")})
        assert closed_code(late) == CloseCode.SESSION_OVER


def test_abandoned_lobby_is_cancelled_and_sockets_are_closed(mysql_live) -> None:
    client, people = mysql_live
    session = make_session(client, people)
    sid = session["session_id"]

    host_cm, host, _ = connect(client, sid, "host")
    join(client, people["alice"], session["join_code"])
    assert host.receive_json()["type"] == "participant_joined"
    alice_cm, alice, state = connect(client, sid, "alice")
    assert state["host_connected"] is True

    host_cm.__exit__(None, None, None)
    wait_for_host_to_leave(client, sid)

    reap(client, 0)

    ended = receive_until(alice, "session_ended")[-1]
    assert ended["reason"] == "CANCELLED"
    assert ended["leaderboard"] == []
    assert closed_code(alice) == CloseCode.NORMAL
    alice_cm.__exit__(None, None, None)

    stored = stored_session(client, sid)
    assert stored.status == LiveSessionStatus.CANCELLED
    assert stored.ended_at is not None
    assert result_rows(client, sid) == []

    as_account(client, people["host"])
    results = client.get(f"/sessions/{sid}/results")
    assert results.status_code == 200
    assert results.json()["status"] == "CANCELLED"
    assert results.json()["standings"] == []

    # A later pass finds nothing left to end, and the session stays over.
    reap(client, 0)
    assert stored_session(client, sid).ended_at == stored.ended_at
    assert_session_over(client, sid, "alice")


def test_abandoned_game_is_completed_with_final_results(mysql_live) -> None:
    client, people = mysql_live
    session = make_session(client, people)
    sid = session["session_id"]

    host_cm, host, _ = connect(client, sid, "host")
    for name in ("alice", "bob"):
        join(client, people[name], session["join_code"])
        assert host.receive_json()["type"] == "participant_joined"
    alice_cm, alice, _ = connect(client, sid, "alice")
    bob_cm, bob, _ = connect(client, sid, "bob")

    # Q1 is open and only Alice has answered when the host's tab goes away.
    q1 = open_question(host, 1)
    for ws in (alice, bob):
        assert ws.receive_json()["type"] == "question_opened"
    answer(alice, q1, correct=True)
    host_cm.__exit__(None, None, None)
    wait_for_host_to_leave(client, sid)

    reap(client, 0)

    for ws in (alice, bob):
        msgs = receive_until(ws, "session_ended")
        tail = [
            m["type"]
            for m in msgs
            if m["type"] in ("question_closed", "question_results", "session_ended")
        ]
        # The open question is closed and scored before the game ends.
        assert tail == ["question_closed", "question_results", "session_ended"]
        ended = msgs[-1]
        assert ended["reason"] == "COMPLETED"
        assert [row["display_name"] for row in ended["leaderboard"]] == [
            "Alice",
            "Bob",
        ]
        assert closed_code(ws) == CloseCode.NORMAL
    for cm in (alice_cm, bob_cm):
        cm.__exit__(None, None, None)

    stored = stored_session(client, sid)
    assert stored.status == LiveSessionStatus.COMPLETED
    assert stored.ended_at is not None
    with client.app.state.database.session_factory() as db:
        assert db.scalar(
            select(SessionQuestion.status).where(
                SessionQuestion.session_question_id == q1["session_question_id"]
            )
        ) == SessionQuestionStatus.CLOSED

    rows = result_rows(client, sid)
    assert [(name, correct, rank) for name, _, correct, rank in rows] == [
        ("Alice", 1, 1),
        ("Bob", 0, 2),
    ]
    assert rows[0][1] > 0 and rows[1][1] == 0

    # The stored results are what the results page shows after a reload.
    as_account(client, people["host"])
    standings = client.get(f"/sessions/{sid}/results").json()["standings"]
    assert [
        (row["display_name"], row["total_score"], row["correct_count"], row["final_rank"])
        for row in standings
    ] == rows
    assert_session_over(client, sid, "bob")


def test_only_sessions_without_a_host_for_long_enough_are_ended(mysql_live) -> None:
    client, people = mysql_live
    hosted = make_session(client, people)["session_id"]
    host_left = make_session(client, people)["session_id"]
    never_hosted = make_session(client, people)["session_id"]

    hosted_cm, hosted_ws, _ = connect(client, hosted, "host")
    left_cm, _, _ = connect(client, host_left, "host")
    left_cm.__exit__(None, None, None)
    wait_for_host_to_leave(client, host_left)

    # Inside the grace period nothing ends, including a session that was
    # never seen with a host: its clock starts at this pass.
    reap(client, 3600)
    for sid in (hosted, host_left, never_hosted):
        assert stored_session(client, sid).status == LiveSessionStatus.LOBBY

    reap(client, 0)
    assert stored_session(client, host_left).status == LiveSessionStatus.CANCELLED
    assert stored_session(client, never_hosted).status == LiveSessionStatus.CANCELLED
    # A session with its host connected is never ended, however long it sits.
    assert stored_session(client, hosted).status == LiveSessionStatus.LOBBY
    hosted_ws.send_json({"type": "ping"})
    assert hosted_ws.receive_json() == {"type": "pong"}
    hosted_cm.__exit__(None, None, None)


def test_host_who_comes_back_restarts_the_clock(mysql_live) -> None:
    client, people = mysql_live
    sid = make_session(client, people)["session_id"]
    grace = 1.0

    host_cm, _, _ = connect(client, sid, "host")
    host_cm.__exit__(None, None, None)
    wait_for_host_to_leave(client, sid)
    time.sleep(grace + 0.3)

    # Back after the grace period ran out, but before any pass ended it.
    host_cm, host, _ = connect(client, sid, "host")
    reap(client, grace)
    assert stored_session(client, sid).status == LiveSessionStatus.LOBBY

    # Leaving again starts a fresh clock, not the old one.
    host_cm.__exit__(None, None, None)
    wait_for_host_to_leave(client, sid)
    reap(client, grace)
    assert stored_session(client, sid).status == LiveSessionStatus.LOBBY

    time.sleep(grace + 0.3)
    reap(client, grace)
    assert stored_session(client, sid).status == LiveSessionStatus.CANCELLED


def test_background_reaper_ends_an_abandoned_session(monkeypatch) -> None:
    # The real loop started by the app's lifespan, with the shortest settings.
    with live_app(
        monkeypatch, live_abandon_after_seconds=1, live_abandon_check_seconds=1
    ) as (client, people):
        sid = make_session(client, people)["session_id"]
        host_cm, _, _ = connect(client, sid, "host")
        host_cm.__exit__(None, None, None)

        wait_until(
            lambda: stored_session(client, sid).status
            == LiveSessionStatus.CANCELLED,
            timeout=15,
        )
        assert_session_over(client, sid, "host")


def test_host_end_racing_the_reaper_writes_one_set_of_results(mysql_live) -> None:
    client, people = mysql_live
    session = make_session(client, people)
    sid = session["session_id"]
    for name in ("alice", "bob"):
        join(client, people[name], session["join_code"])
    host_cm, host, _ = connect(client, sid, "host")
    q1 = open_question(host, 1)
    host_cm.__exit__(None, None, None)
    wait_for_host_to_leave(client, sid)

    as_account(client, people["alice"])
    answered = client.post(
        f"/sessions/{sid}/questions/{q1['session_question_id']}/responses",
        json={"choice_id": q1["choices"][0]["choice_id"]},
    )
    assert answered.status_code == 201

    barrier = Barrier(2)

    def run(action):
        with client.app.state.database.session_factory() as db:
            barrier.wait()
            try:
                return action(db)
            except APIError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        host_end = executor.submit(run, lambda db: end_session(db, people["host"], sid))
        reaper = executor.submit(run, lambda db: abandon_session(db, sid))
        outcomes = [host_end.result(timeout=10), reaper.result(timeout=10)]

    # Exactly one of them ends the game; the other sees it already over:
    # the host's End is refused, and the reaper's pass is a no-op.
    host_won = not isinstance(outcomes[0], str)
    if host_won:
        assert outcomes[1] is None
    else:
        assert outcomes[0] == "session_already_ended"
        assert outcomes[1] is not None

    assert stored_session(client, sid).status == LiveSessionStatus.COMPLETED
    with client.app.state.database.session_factory() as db:
        result_count = db.scalar(
            select(func.count(Result.result_id))
            .join(
                SessionParticipant,
                SessionParticipant.session_participant_id
                == Result.session_participant_id,
            )
            .where(SessionParticipant.session_id == sid)
        )
    assert result_count == 2
    assert [row[0] for row in result_rows(client, sid)] == ["Alice", "Bob"]
