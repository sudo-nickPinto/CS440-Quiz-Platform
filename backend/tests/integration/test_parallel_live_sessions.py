from datetime import datetime, timedelta

import pytest

from app.api.routes import live
from tests.integration.approval_support import approval_class  # noqa: F401
from tests.integration.live_approval_support import (
    answer_question,
    connected,
    create_session,
    end_session,
    join_session,
    open_question,
)


def assert_quiet(socket):
    socket.send_json({"type": "ping"})
    assert socket.receive_json() == {"type": "pong"}


def assert_joined(host, participant):
    joined = host.receive_json()
    assert joined["type"] == "participant_joined", joined
    assert joined["session_participant_id"] == participant["session_participant_id"]
    assert joined["display_name"] == participant["display_name"]
    assert joined["participant_count"] == 1


def assert_deadline(host, player, question, seconds):
    closed = host.receive_json()
    assert closed["type"] == "question_closed", closed
    assert (closed["session_id"], closed["session_question_id"]) == (
        question["session_id"], question["session_question_id"],
    )
    assert closed["reason"] == "DEADLINE"
    assert (closed["answered_count"], closed["eligible_count"]) == (0, 1)
    assert closed["closes_at"] == question["closes_at"]
    opened_at = datetime.fromisoformat(question["opened_at"])
    closes_at = datetime.fromisoformat(question["closes_at"])
    assert closes_at - opened_at == timedelta(seconds=seconds)
    assert datetime.fromisoformat(closed["closed_at"]) >= closes_at
    assert player.receive_json() == closed
    for results in (host.receive_json(), player.receive_json()):
        assert results["type"] == "question_results"
        assert (results["session_id"], results["session_question_id"]) == (
            question["session_id"], question["session_question_id"],
        )
        assert sum(choice["response_count"] for choice in results["choices"]) == 0


@pytest.mark.parametrize(
    "second_host",
    [
        pytest.param("coorganizer", id="two-organizers"),
        pytest.param("organizer", id="one-organizer-twice"),
    ],
)
def test_two_live_sessions_for_one_approved_version_stay_isolated(
    approval_class, monkeypatch, second_host
) -> None:
    course = approval_class
    monkeypatch.setattr(live, "IDLE_TIMEOUT_SECONDS", 20)
    short, long = 4, 12
    quiz = course.approve_quiz("owner", {
        "title": "Parallel live quiz",
        "questions": [
            {
                "question_text": f"Question {order}?",
                "time_limit_seconds": seconds,
                "choices": [
                    {"choice_text": "Correct", "is_correct": True},
                    {"choice_text": "Incorrect", "is_correct": False},
                ],
            }
            for order, seconds in [(1, short), (2, long)]
        ],
    })
    first = create_session(course, "organizer", quiz)
    first_id = first["session_id"]
    active_sessions = f"{course.path}/active-sessions"

    with connected(course, "organizer", first) as (host_a, state):
        assert state["role"] == "host"
        assert state["participant_count"] == 0
        assert state["session"]["join_code"] == first["join_code"]
        participant_a = join_session(course, "submitter", first)
        assert_joined(host_a, participant_a)
        with connected(course, "submitter", first) as (player_a, state):
            assert state["role"] == "participant" and state["host_connected"]
            assert state["participant_count"] == 1
            first_q1 = open_question(host_a, player_a, 1)
            earned = answer_question(host_a, player_a, first_q1, choice_index=0)["me"]["points_awarded"]
            assert earned > 0

            # The first session is already ACTIVE when the second host opens a lobby.
            second = create_session(course, second_host, quiz)
            second_id = second["session_id"]
            assert second_id != first_id
            assert second["quiz_version_id"] == first["quiz_version_id"]
            assert second["join_code"] != first["join_code"]

            with connected(course, second_host, second) as (host_b, state):
                assert state["role"] == "host"
                assert state["participant_count"] == 0
                assert state["session"]["join_code"] == second["join_code"]
                participant_b = join_session(course, "editor", second)
                assert_joined(host_b, participant_b)
                assert participant_b["session_participant_id"] != participant_a["session_participant_id"]
                assert_quiet(host_a)
                assert_quiet(player_a)

                for actor, sid, participant in (
                    ("organizer", first_id, participant_a), (second_host, second_id, participant_b)
                ):
                    roster = course.request(actor, "GET", f"/sessions/{sid}/participants").json()
                    assert [row["account_id"] for row in roster] == [participant["account_id"]]

                with connected(course, "editor", second) as (player_b, state):
                    assert state["role"] == "participant" and state["host_connected"]
                    assert state["participant_count"] == 1
                    first_q2 = open_question(host_a, player_a, 2)
                    assert_quiet(host_b)
                    assert_quiet(player_b)
                    second_q1 = open_question(host_b, player_b, 1)
                    assert first_q1["session_question_id"] != second_q1["session_question_id"]
                    running = course.request("member", "GET", active_sessions).json()
                    assert {row["session_id"]: row["current_question_order"] for row in running} == {
                        first_id: 2, second_id: 1,
                    }
                    assert_deadline(host_b, player_b, second_q1, short)
                    assert_quiet(host_a)
                    assert_quiet(player_a)

                    second_q2 = open_question(host_b, player_b, 2)
                    assert first_q2["session_question_id"] != second_q2["session_question_id"]
                    assert first_q2["choices"] == second_q2["choices"]
                    player_b.send_json({
                        "type": "submit_answer",
                        "session_question_id": first_q2["session_question_id"],
                        "choice_id": first_q2["choices"][0]["choice_id"],
                    })
                    error = player_b.receive_json()
                    assert (error["type"], error["code"]) == ("error", "session_question_not_found")
                    result = answer_question(host_b, player_b, second_q2, choice_index=1)
                    assert result["me"]["points_awarded"] == 0
                    end_session(host_b, player_b, second_id)

            # Finishing the second game leaves the first game's sockets and timer running.
            [remaining] = course.request("member", "GET", active_sessions).json()
            assert (remaining["session_id"], remaining["status"], remaining["current_question_order"]) == (
                first_id, "ACTIVE", 2,
            )
            unfinished = course.request("organizer", "GET", f"/sessions/{first_id}/results", status=409)
            assert unfinished.json()["error"]["code"] == "results_not_ready"
            assert_quiet(host_a)
            assert_quiet(player_a)
            assert_deadline(host_a, player_a, first_q2, long)
            end_session(host_a, player_a, first_id)

    assert course.request("member", "GET", active_sessions).json() == []
    for sid, participant, points, states, questions in (
        (first_id, participant_a, earned, ("correct", "missed"), (first_q1, first_q2)),
        (second_id, participant_b, 0, ("missed", "wrong"), (second_q1, second_q2)),
    ):
        report = course.request("organizer", "GET", f"{course.path}/sessions/{sid}/results").json()
        assert (report["session_id"], report["status"], report["played_count"]) == (sid, "COMPLETED", 2)
        [player] = report["players"]
        assert (player["id"], player["name"], player["points"], player["rank"]) == (
            participant["session_participant_id"], participant["display_name"], points, 1,
        )
        assert tuple(answer["state"] for answer in player["answers"]) == states
        assert [row["session_question_id"] for row in report["questions"]] == [
            question["session_question_id"] for question in questions
        ]
