from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_current_account
from app.models import Account, AccountType


def test_create_and_retrieve_quiz(
    mysql_client: TestClient, current_account: CurrentAccount
) -> None:
    created = mysql_client.post(
        "/quizzes",
        json={
            "title": "  Operating Systems  ",
            "description": "Processes and threads",
            "visibility": "PRIVATE",
        },
    )

    assert created.status_code == 201
    body = created.json()
    assert body["author_id"] == current_account.account_id
    assert body["status"] == "DRAFT"
    assert body["current_version"]["version_number"] == 1
    assert body["current_version"]["title"] == "Operating Systems"
    assert body["current_version"]["questions"] == []

    retrieved = mysql_client.get(f"/quizzes/{body['quiz_id']}")
    assert retrieved.status_code == 200
    assert retrieved.json() == body


def test_quiz_access_is_limited_to_its_author(
    mysql_client: TestClient, mysql_session: Session
) -> None:
    created = mysql_client.post("/quizzes", json={})
    quiz_id = created.json()["quiz_id"]

    unique = uuid4().hex
    other = Account(
        auth0_sub=f"test|{unique}",
        email=f"{unique}@example.test",
        display_name="Another account",
        account_type=AccountType.STUDENT,
    )
    mysql_session.add(other)
    mysql_session.flush()
    mysql_client.app.dependency_overrides[get_current_account] = lambda: CurrentAccount(
        other.account_id, AccountType.STUDENT
    )

    response = mysql_client.get(f"/quizzes/{quiz_id}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "quiz_access_denied"


def test_missing_quiz_returns_not_found(mysql_client: TestClient) -> None:
    response = mysql_client.get("/quizzes/4294967295")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "quiz_not_found", "message": "Quiz not found."}
    }
