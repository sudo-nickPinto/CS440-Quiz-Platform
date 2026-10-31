from sqlalchemy import text

from tests.integration.conftest import cleanup_database
from tests.class_quiz_helpers import publish_quiz
from tests.test_session_api import QUIZ_PAYLOAD


def test_cleanup_handles_a_class_scoped_live_session(mysql_quiz_client) -> None:
    client, _, _ = mysql_quiz_client
    created_class = client.post("/classes", json={"name": "Cleanup class"})
    assert created_class.status_code == 201
    quiz = client.post(
        f"/classes/{created_class.json()['class_id']}/quizzes", json=QUIZ_PAYLOAD
    )
    assert quiz.status_code == 201
    publish_quiz(client, quiz.json()["quiz_id"])
    session = client.post(
        f"/quizzes/{quiz.json()['quiz_id']}/sessions",
        json={"class_id": created_class.json()["class_id"]},
    )
    assert session.status_code == 201

    cleanup_database(client.app)

    with client.app.state.database.engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM live_session")) == 0
        assert connection.scalar(text("SELECT COUNT(*) FROM class")) == 0
