from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import QuizVersion


def create_quiz(client: TestClient) -> dict:
    response = client.post(
        "/quizzes",
        json={"title": "Original", "description": "Remove me"},
    )
    assert response.status_code == 201
    return response.json()


def test_update_draft_metadata(mysql_client: TestClient) -> None:
    quiz = create_quiz(mysql_client)

    response = mysql_client.patch(
        f"/quizzes/{quiz['quiz_id']}",
        json={
            "title": "  Updated title  ",
            "description": None,
            "visibility": "PUBLIC",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["visibility"] == "PUBLIC"
    assert body["current_version"]["title"] == "Updated title"
    assert body["current_version"]["description"] is None
    assert body["current_version"]["version_number"] == 1


def test_archived_quiz_cannot_be_updated(mysql_client: TestClient) -> None:
    quiz = create_quiz(mysql_client)
    mysql_client.patch(f"/quizzes/{quiz['quiz_id']}/archive")

    response = mysql_client.patch(
        f"/quizzes/{quiz['quiz_id']}", json={"title": "Too late"}
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quiz_archived"


def test_editing_published_version_creates_new_draft(
    mysql_client: TestClient, mysql_session: Session
) -> None:
    quiz = create_quiz(mysql_client)
    version_id = quiz["current_version"]["quiz_version_id"]
    mysql_session.execute(
        update(QuizVersion)
        .where(QuizVersion.quiz_version_id == version_id)
        .values(published_at=datetime.now())
    )
    mysql_session.flush()

    response = mysql_client.patch(
        f"/quizzes/{quiz['quiz_id']}", json={"title": "New title"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["current_version"]["version_number"] == 2
    assert body["current_version"]["published_at"] is None
    assert body["current_version"]["title"] == "New title"

    versions = mysql_session.scalars(
        select(QuizVersion)
        .where(QuizVersion.quiz_id == quiz["quiz_id"])
        .order_by(QuizVersion.version_number)
    ).all()
    assert len(versions) == 2
    assert versions[0].title == "Original"
    assert versions[0].published_at is not None
