from fastapi.testclient import TestClient
from sqlalchemy import text

from app.auth import CurrentAccount, get_active_account


PAYLOAD = {
    "title": "Migrated MySQL Quiz",
    "questions": [
        {
            "question_text": "Which answer is correct?",
            "time_limit_seconds": 20,
            "base_points": 1000,
            "choices": [
                {"choice_text": "This one", "is_correct": True},
                {"choice_text": "Not this one", "is_correct": False},
            ],
        }
    ],
}


def test_mvp_quiz_round_trip_uses_migrated_schema(
    mysql_quiz_client: tuple[TestClient, CurrentAccount, CurrentAccount],
) -> None:
    client, author, reader = mysql_quiz_client

    created = client.post("/quizzes", json=PAYLOAD)
    assert created.status_code == 201
    body = created.json()
    assert body["author_id"] == author.account_id
    assert body["status"] == "PUBLISHED"
    assert body["visibility"] == "PUBLIC"
    assert body["version"]["version_number"] == 1

    with client.app.state.database.engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM quiz")).scalar_one() == 1
        assert (
            connection.execute(text("SELECT COUNT(*) FROM quiz_version")).scalar_one()
            == 1
        )
        assert connection.execute(text("SELECT COUNT(*) FROM question")).scalar_one() == 1
        assert (
            connection.execute(text("SELECT COUNT(*) FROM answer_choice")).scalar_one()
            == 2
        )

    client.app.dependency_overrides[get_active_account] = lambda: reader
    assert client.get("/quizzes").json()[0]["quiz_id"] == body["quiz_id"]
    assert client.get(f"/quizzes/{body['quiz_id']}").status_code == 200

    client.app.dependency_overrides[get_active_account] = lambda: author
    archived = client.patch(f"/quizzes/{body['quiz_id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
