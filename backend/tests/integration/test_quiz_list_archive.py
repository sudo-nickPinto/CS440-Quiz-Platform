from fastapi.testclient import TestClient


def create_quiz(client: TestClient, title: str) -> dict:
    response = client.post("/quizzes", json={"title": title})
    assert response.status_code == 201
    return response.json()


def test_list_excludes_archived_quizzes_by_default(mysql_client: TestClient) -> None:
    active = create_quiz(mysql_client, "Active quiz")
    archived = create_quiz(mysql_client, "Archived quiz")

    archive_response = mysql_client.patch(f"/quizzes/{archived['quiz_id']}/archive")
    assert archive_response.status_code == 200
    assert archive_response.json()["status"] == "ARCHIVED"

    response = mysql_client.get("/quizzes")

    assert response.status_code == 200
    assert [quiz["quiz_id"] for quiz in response.json()] == [active["quiz_id"]]


def test_list_can_filter_by_status(mysql_client: TestClient) -> None:
    create_quiz(mysql_client, "Draft quiz")
    archived = create_quiz(mysql_client, "Archived quiz")
    mysql_client.patch(f"/quizzes/{archived['quiz_id']}/archive")

    response = mysql_client.get("/quizzes", params={"status": "ARCHIVED"})

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["title"] == "Archived quiz"
    assert response.json()[0]["status"] == "ARCHIVED"


def test_archiving_is_idempotent(mysql_client: TestClient) -> None:
    quiz = create_quiz(mysql_client, "Archive once")
    path = f"/quizzes/{quiz['quiz_id']}/archive"

    first = mysql_client.patch(path)
    second = mysql_client.patch(path)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == second.json()["status"] == "ARCHIVED"


def test_invalid_status_filter_is_rejected(mysql_client: TestClient) -> None:
    response = mysql_client.get("/quizzes", params={"status": "DELETED"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
