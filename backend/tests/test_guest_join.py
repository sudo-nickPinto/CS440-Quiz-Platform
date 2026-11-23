"""Guest join for the capstone live demo (app/guest.py)."""

from tests.test_live_websocket import (  # noqa: F401  (pytest fixture)
    authenticate,
    live,
    make_session,
    receive_until,
    ws_url,
)


def guest_join(client, join_code: str, nickname: str):
    return client.post(
        "/guest/join", json={"join_code": join_code, "nickname": nickname}
    )


def test_check_code_finds_the_game_and_rejects_unknown_codes(live) -> None:
    client, people = live
    session = make_session(client, people)
    client.app.dependency_overrides.clear()

    found = client.post("/guest/check-code", json={"join_code": session["join_code"]})
    assert found.status_code == 200
    assert found.json()["session_id"] == session["session_id"]
    assert found.json()["quiz_title"]

    missing = "000000" if session["join_code"] != "000000" else "000001"
    unknown = client.post("/guest/check-code", json={"join_code": missing})
    assert unknown.status_code == 404
    assert unknown.json()["error"]["code"] == "join_code_not_found"


def test_guest_joins_with_nickname_and_reaches_the_lobby(live) -> None:
    client, people = live
    session = make_session(client, people)
    sid = session["session_id"]

    with client.websocket_connect(ws_url(sid)) as host:
        authenticate(host, "host")
        client.app.dependency_overrides.clear()

        joined = guest_join(client, session["join_code"], "  Quiz   Wizard ")
        assert joined.status_code == 201
        body = joined.json()
        assert body["session"]["session_id"] == sid
        assert body["participant"]["display_name"] == "Quiz Wizard"
        token = body["guest_token"]
        assert token.startswith("guest_")

        # The host's lobby hears about the guest like any other join.
        event = host.receive_json()
        assert event["type"] == "participant_joined"
        assert event["display_name"] == "Quiz Wizard"

        # The token works for REST...
        me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["display_name"] == "Quiz Wizard"

        # ...and for the live socket, where the guest plays a question.
        with client.websocket_connect(ws_url(sid)) as guest:
            guest.send_json({"type": "auth", "token": token})
            state = guest.receive_json()
            assert state["type"] == "session_state"
            assert state["role"] == "participant"

            host.send_json(
                {"type": "open_question", "question_order": 1, "request_id": "o1"}
            )
            opened = receive_until(host, "question_opened")[-1]
            assert guest.receive_json()["type"] == "question_opened"
            guest.send_json(
                {
                    "type": "submit_answer",
                    "session_question_id": opened["session_question_id"],
                    "choice_id": opened["choices"][0]["choice_id"],
                    "request_id": "a1",
                }
            )
            assert guest.receive_json()["type"] == "ack"


def test_guest_join_rejects_bad_codes_names_and_duplicates(live) -> None:
    client, people = live
    session = make_session(client, people)
    client.app.dependency_overrides.clear()
    code = session["join_code"]

    missing = "000000" if code != "000000" else "000001"
    assert guest_join(client, missing, "Sam").status_code == 404

    blank = guest_join(client, code, "   ")
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "invalid_nickname"

    too_long = guest_join(client, code, "x" * 31)
    assert too_long.status_code == 422

    assert guest_join(client, code, "Sam").status_code == 201
    taken = guest_join(client, code, "sam")
    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "nickname_taken"


def test_unknown_guest_token_is_rejected(live) -> None:
    client, _ = live
    client.app.dependency_overrides.clear()

    response = client.get("/me", headers={"Authorization": "Bearer guest_nope"})
    assert response.status_code == 401

    with client.websocket_connect(ws_url(1)) as ws:
        ws.send_json({"type": "auth", "token": "guest_nope"})
        try:
            ws.receive_json()
        except Exception as exc:  # WebSocketDisconnect
            assert getattr(exc, "code", None) == 4401
        else:
            raise AssertionError("socket stayed open")


def test_quick_host_lists_your_quizzes_and_hosts_without_approval(live) -> None:
    from tests.class_quiz_helpers import post_class_quiz
    from tests.test_live_websocket import QUIZ_PAYLOAD, as_account

    client, people = live
    as_account(client, people["host"])
    # Published but never submitted for class approval.
    quiz = post_class_quiz(client, QUIZ_PAYLOAD)
    assert quiz.status_code == 201
    quiz_id = quiz.json()["quiz_id"]

    listed = client.get("/guest/quick-host/quizzes")
    assert listed.status_code == 200
    assert [q["quiz_id"] for q in listed.json()] == [quiz_id]
    assert listed.json()[0]["question_count"] >= 1

    # Someone else can't see or host it.
    as_account(client, people["outsider"])
    assert client.get("/guest/quick-host/quizzes").json() == []
    assert client.post(f"/guest/quick-host/quizzes/{quiz_id}").status_code == 404

    as_account(client, people["host"])
    first = client.post(f"/guest/quick-host/quizzes/{quiz_id}")
    assert first.status_code == 201
    session = first.json()
    assert session["status"] == "LOBBY"

    # A second game reuses the same Live demo class.
    second = client.post(f"/guest/quick-host/quizzes/{quiz_id}").json()
    assert second["class_id"] == session["class_id"]
    assert second["join_code"] != session["join_code"]

    sid = session["session_id"]
    with client.websocket_connect(ws_url(sid)) as host:
        assert authenticate(host, "host")["role"] == "host"
        client.app.dependency_overrides.clear()
        joined = guest_join(client, session["join_code"], "Lobby Guest")
        assert joined.status_code == 201
        event = host.receive_json()
        assert event["type"] == "participant_joined"
        assert event["display_name"] == "Lobby Guest"
