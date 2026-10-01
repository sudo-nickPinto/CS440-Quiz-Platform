from fastapi.testclient import TestClient


def create_quiz(client: TestClient) -> int:
    response = client.post("/quizzes", json={"title": "Publish test"})
    assert response.status_code == 201
    return response.json()["quiz_id"]


def add_question(client: TestClient, quiz_id: int) -> None:
    response = client.post(
        f"/quizzes/{quiz_id}/questions",
        json={
            "question_text": "Ready?",
            "choices": [
                {"choice_text": "Yes", "is_correct": True},
                {"choice_text": "No", "is_correct": False},
            ],
        },
    )
    assert response.status_code == 201


def test_publish_complete_quiz_and_start_new_draft_on_edit(
    mysql_client: TestClient,
) -> None:
    quiz_id = create_quiz(mysql_client)
    add_question(mysql_client, quiz_id)

    published = mysql_client.post(f"/quizzes/{quiz_id}/publish")

    assert published.status_code == 200
    body = published.json()
    assert body["status"] == "PUBLISHED"
    assert body["current_version"]["published_at"] is not None

    edit = mysql_client.patch(
        f"/quizzes/{quiz_id}", json={"title": "Next version"}
    )
    assert edit.status_code == 200
    assert edit.json()["current_version"]["version_number"] == 2
    assert edit.json()["current_version"]["published_at"] is None


def test_incomplete_quiz_cannot_be_published(mysql_client: TestClient) -> None:
    quiz_id = create_quiz(mysql_client)

    response = mysql_client.post(f"/quizzes/{quiz_id}/publish")

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "quiz_not_publishable"
    assert "The quiz must contain at least one question." in body["details"]


def test_publishing_same_version_twice_returns_conflict(
    mysql_client: TestClient,
) -> None:
    quiz_id = create_quiz(mysql_client)
    add_question(mysql_client, quiz_id)
    mysql_client.post(f"/quizzes/{quiz_id}/publish")

    response = mysql_client.post(f"/quizzes/{quiz_id}/publish")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quiz_already_published"
