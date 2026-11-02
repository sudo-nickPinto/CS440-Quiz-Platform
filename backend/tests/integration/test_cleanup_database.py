from sqlalchemy import text

from app.auth import CurrentAccount, get_active_account
from app.models import Account, AccountRole

from tests.integration.conftest import cleanup_database
from tests.test_session_api import QUIZ_PAYLOAD


def test_cleanup_handles_a_class_scoped_live_session(mysql_quiz_client) -> None:
    client, author, _ = mysql_quiz_client
    with client.app.state.database.session_factory() as db:
        db.get(Account, author.account_id).account_type = "ADMINISTRATOR"
        db.commit()
    faculty = CurrentAccount(author.account_id, AccountRole.ADMIN, True)
    client.app.dependency_overrides[get_active_account] = lambda: faculty
    created_class = client.post("/classes", json={"name": "Cleanup class"})
    assert created_class.status_code == 201
    quiz = client.post("/quizzes", json=QUIZ_PAYLOAD)
    assert quiz.status_code == 201
    session = client.post(
        f"/quizzes/{quiz.json()['quiz_id']}/sessions",
        json={"class_id": created_class.json()["class_id"]},
    )
    assert session.status_code == 201

    cleanup_database(client.app)

    with client.app.state.database.engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM live_session")) == 0
        assert connection.scalar(text("SELECT COUNT(*) FROM class")) == 0
