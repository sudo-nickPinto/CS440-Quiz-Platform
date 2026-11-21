from contextlib import contextmanager

import pytest
from starlette.websockets import WebSocketDisconnect

from app.live.protocol import CloseCode


def create_session(course, actor: str, quiz: dict) -> dict:
    return course.request(
        actor, "POST", f"{course.path}/quizzes/{quiz['quiz_id']}/sessions", status=201
    ).json()


def join_session(course, actor: str, session: dict) -> dict:
    joined = course.request(
        actor, "POST", "/sessions/join", json={"join_code": session["join_code"]}, status=201
    ).json()
    assert joined["session"]["session_id"] == session["session_id"]
    return joined["participant"]


@contextmanager
def connected(course, actor: str, session: dict):
    session_id = session["session_id"]
    with course.client.websocket_connect(f"/ws/sessions/{session_id}") as socket:
        socket.send_json({"type": "auth", "token": course.tokens[actor]})
        state = socket.receive_json()
        assert state["type"] == "session_state", state
        assert state["session"]["session_id"] == session_id
        yield socket, state


def open_question(host, player, order: int) -> dict:
    host.send_json({"type": "open_question", "question_order": order})
    ack = host.receive_json()
    question = host.receive_json()
    assert question["type"] == "question_opened", question
    assert question["question_order"] == order
    assert ack["type"] == "ack", ack
    assert ack["session_question_id"] == question["session_question_id"]
    assert player.receive_json() == question
    return question


def answer_question(host, player, question: dict, *, choice_index: int) -> dict:
    question_id = question["session_question_id"]
    choice_id = question["choices"][choice_index]["choice_id"]
    player.send_json({
        "type": "submit_answer", "session_question_id": question_id, "choice_id": choice_id,
    })
    ack = player.receive_json()
    assert ack["type"] == "ack", ack
    assert ack["receipt"]["session_question_id"] == question_id
    assert ack["receipt"]["choice_id"] == choice_id
    assert host.receive_json() == {
        "type": "answer_progress", "session_question_id": question_id,
        "answered_count": 1, "eligible_count": 1,
    }
    closed = host.receive_json()
    assert closed["type"] == "question_closed", closed
    assert closed["session_id"] == question["session_id"]
    assert closed["session_question_id"] == question_id
    assert closed["reason"] == "ALL_ANSWERED"
    assert player.receive_json() == closed
    host_results = host.receive_json()
    assert host_results["type"] == "question_results", host_results
    assert host_results["session_question_id"] == question_id
    result = player.receive_json()
    assert result["type"] == "question_results", result
    assert result["session_question_id"] == question_id
    return result


def end_session(host, player, session_id: int) -> dict:
    host.send_json({"type": "end_session"})
    assert host.receive_json()["type"] == "ack"
    ended = host.receive_json()
    player_ended = player.receive_json()
    for event in (ended, player_ended):
        assert (event["type"], event["session_id"], event["reason"]) == (
            "session_ended", session_id, "COMPLETED",
        )
    for socket in (host, player):
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == CloseCode.NORMAL
    return ended
