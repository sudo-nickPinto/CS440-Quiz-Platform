from fastapi.testclient import TestClient


def create_quiz(client: TestClient, title: str = "Question test") -> int:
    response = client.post("/quizzes", json={"title": title})
    assert response.status_code == 201
    return response.json()["quiz_id"]


def question_payload(text: str, correct: str = "Correct") -> dict:
    return {
        "question_text": text,
        "time_limit_seconds": 30,
        "base_points": 500,
        "choices": [
            {"choice_text": correct, "is_correct": True},
            {"choice_text": "Incorrect", "is_correct": False},
        ],
    }


def test_question_create_update_reorder_and_delete(mysql_client: TestClient) -> None:
    quiz_id = create_quiz(mysql_client)
    first = mysql_client.post(
        f"/quizzes/{quiz_id}/questions", json=question_payload("First")
    )
    second = mysql_client.post(
        f"/quizzes/{quiz_id}/questions", json=question_payload("Second")
    )
    assert first.status_code == second.status_code == 201
    first_id = first.json()["question_id"]
    second_id = second.json()["question_id"]
    assert first.json()["question_order"] == 1
    assert second.json()["question_order"] == 2

    updated = mysql_client.put(
        f"/quizzes/{quiz_id}/questions/{first_id}",
        json=question_payload("Updated first", correct="New answer"),
    )
    assert updated.status_code == 200
    assert updated.json()["question_text"] == "Updated first"
    assert updated.json()["choices"][0]["choice_text"] == "New answer"

    reordered = mysql_client.patch(
        f"/quizzes/{quiz_id}/questions/order",
        json={"question_ids": [second_id, first_id]},
    )
    assert reordered.status_code == 200
    assert [item["question_id"] for item in reordered.json()] == [second_id, first_id]
    assert [item["question_order"] for item in reordered.json()] == [1, 2]

    deleted = mysql_client.delete(f"/quizzes/{quiz_id}/questions/{second_id}")
    assert deleted.status_code == 204

    quiz = mysql_client.get(f"/quizzes/{quiz_id}").json()
    remaining = quiz["current_version"]["questions"]
    assert len(remaining) == 1
    assert remaining[0]["question_id"] == first_id
    assert remaining[0]["question_order"] == 1


def test_reorder_requires_every_question_once(mysql_client: TestClient) -> None:
    quiz_id = create_quiz(mysql_client)
    question = mysql_client.post(
        f"/quizzes/{quiz_id}/questions", json=question_payload("Question")
    ).json()

    response = mysql_client.patch(
        f"/quizzes/{quiz_id}/questions/order",
        json={"question_ids": [question["question_id"], 4_294_967_295]},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_question_order"


def test_archived_quiz_questions_are_immutable(mysql_client: TestClient) -> None:
    quiz_id = create_quiz(mysql_client)
    mysql_client.patch(f"/quizzes/{quiz_id}/archive")

    response = mysql_client.post(
        f"/quizzes/{quiz_id}/questions", json=question_payload("Too late")
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quiz_archived"


def test_question_must_belong_to_quiz_in_path(mysql_client: TestClient) -> None:
    first_quiz_id = create_quiz(mysql_client, "First quiz")
    second_quiz_id = create_quiz(mysql_client, "Second quiz")
    question = mysql_client.post(
        f"/quizzes/{first_quiz_id}/questions", json=question_payload("Question")
    ).json()

    response = mysql_client.put(
        f"/quizzes/{second_quiz_id}/questions/{question['question_id']}",
        json=question_payload("Moved question"),
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "question_not_found"
