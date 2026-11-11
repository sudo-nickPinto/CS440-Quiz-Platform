from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import CurrentAccount, get_active_account
from tests.class_quiz_helpers import host_quiz, post_class_quiz


QUIZ_PAYLOAD = {
    "title": "MySQL Session Quiz",
    "questions": [
        {
            "question_text": "Can this quiz open a lobby?",
            "choices": [
                {"choice_text": "Yes", "is_correct": True},
                {"choice_text": "No", "is_correct": False},
            ],
        }
    ],
}


def test_session_create_and_join_use_migrated_schema(
    mysql_quiz_client: tuple[TestClient, CurrentAccount, CurrentAccount],
) -> None:
    client, author, reader = mysql_quiz_client
    quiz_response = post_class_quiz(client, QUIZ_PAYLOAD)
    assert quiz_response.status_code == 201
    quiz = quiz_response.json()

    session_response = host_quiz(client, quiz["quiz_id"])
    assert session_response.status_code == 201
    session = session_response.json()
    assert session["host_id"] == author.account_id
    assert session["status"] == "LOBBY"

    client.app.dependency_overrides[get_active_account] = lambda: reader
    join_response = client.post(
        "/sessions/join",
        json={"join_code": session["join_code"]},
    )
    assert join_response.status_code == 201
    participant = join_response.json()["participant"]
    assert participant["account_id"] == reader.account_id

    with client.app.state.database.engine.connect() as connection:
        stored_session = connection.execute(
            text(
                "SELECT quiz_version_id, host_id, group_id, class_id, status "
                "FROM live_session WHERE session_id = :session_id"
            ),
            {"session_id": session["session_id"]},
        ).mappings().one()
        stored_participant = connection.execute(
            text(
                "SELECT session_id, account_id FROM session_participant "
                "WHERE session_participant_id = :participant_id"
            ),
            {"participant_id": participant["session_participant_id"]},
        ).mappings().one()

    assert stored_session["quiz_version_id"] == quiz["version"]["quiz_version_id"]
    assert stored_session["host_id"] == author.account_id
    assert stored_session["group_id"] is None
    # Every new session belongs to the quiz's class.
    assert stored_session["class_id"] == quiz["class_id"]
    assert stored_session["status"] == "LOBBY"
    assert stored_participant["session_id"] == session["session_id"]
    assert stored_participant["account_id"] == reader.account_id
