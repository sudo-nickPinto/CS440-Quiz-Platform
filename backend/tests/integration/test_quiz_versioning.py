from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Question, QuizVersion


def question_payload(text: str, answer: str) -> dict:
    return {
        "question_text": text,
        "choices": [
            {"choice_text": answer, "is_correct": True},
            {"choice_text": "Wrong", "is_correct": False},
        ],
    }


def test_editing_published_question_deep_copies_version(
    mysql_client: TestClient, mysql_session: Session
) -> None:
    quiz = mysql_client.post("/quizzes", json={"title": "Versioned"}).json()
    quiz_id = quiz["quiz_id"]
    original_question = mysql_client.post(
        f"/quizzes/{quiz_id}/questions",
        json=question_payload("Original question", "Original answer"),
    ).json()
    mysql_client.post(f"/quizzes/{quiz_id}/publish")

    updated = mysql_client.put(
        f"/quizzes/{quiz_id}/questions/{original_question['question_id']}",
        json=question_payload("Updated question", "Updated answer"),
    )

    assert updated.status_code == 200
    assert updated.json()["question_id"] != original_question["question_id"]
    assert updated.json()["question_text"] == "Updated question"

    metadata_edit = mysql_client.patch(
        f"/quizzes/{quiz_id}", json={"description": "Same working draft"}
    )
    assert metadata_edit.status_code == 200
    assert metadata_edit.json()["current_version"]["version_number"] == 2

    versions = mysql_session.scalars(
        select(QuizVersion)
        .where(QuizVersion.quiz_id == quiz_id)
        .options(selectinload(QuizVersion.questions).selectinload(Question.choices))
        .order_by(QuizVersion.version_number)
    ).all()
    assert len(versions) == 2

    published, draft = versions
    assert published.published_at is not None
    assert published.questions[0].question_text == "Original question"
    assert published.questions[0].choices[0].choice_text == "Original answer"
    assert draft.published_at is None
    assert draft.questions[0].question_text == "Updated question"
    assert draft.questions[0].choices[0].choice_text == "Updated answer"


def test_visibility_change_does_not_create_content_version(
    mysql_client: TestClient, mysql_session: Session
) -> None:
    quiz = mysql_client.post("/quizzes", json={"title": "Visibility"}).json()
    quiz_id = quiz["quiz_id"]
    mysql_client.post(
        f"/quizzes/{quiz_id}/questions",
        json=question_payload("Question", "Answer"),
    )
    mysql_client.post(f"/quizzes/{quiz_id}/publish")

    response = mysql_client.patch(
        f"/quizzes/{quiz_id}", json={"visibility": "PUBLIC"}
    )

    assert response.status_code == 200
    assert response.json()["visibility"] == "PUBLIC"
    assert response.json()["current_version"]["version_number"] == 1
    assert response.json()["current_version"]["published_at"] is not None
    versions = mysql_session.scalars(
        select(QuizVersion).where(QuizVersion.quiz_id == quiz_id)
    ).all()
    assert len(versions) == 1
