from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select

from app.errors import APIError
from app.models.quiz import QuizVersion
from app.schemas.quiz import QuizUpdate
from app.services.quizzes import update_quiz


PAYLOAD = {
    "title": "Concurrent editing",
    "description": "Original",
    "questions": [
        {
            "question_text": "Which answer?",
            "time_limit_seconds": 20,
            "base_points": 1000,
            "choices": [
                {"choice_text": "Correct", "is_correct": True},
                {"choice_text": "Incorrect", "is_correct": False},
            ],
        }
    ],
}


def test_competing_edits_publish_only_one_revision(mysql_quiz_client):
    client, author, _ = mysql_quiz_client

    created = client.post("/quizzes", json=PAYLOAD)
    assert created.status_code == 201
    quiz_id = created.json()["quiz_id"]

    barrier = Barrier(2)

    def save(title):
        payload = QuizUpdate(
            **{
                **PAYLOAD,
                "title": title,
                "base_version": 1,
            }
        )

        with client.app.state.database.session_factory() as db:
            barrier.wait(timeout=10)

            try:
                result = update_quiz(db, author, quiz_id, payload)
                return ("saved", result.version.title)
            except APIError as exc:
                return (exc.code, None)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(save, "First editor")
        second = executor.submit(save, "Second editor")
        outcomes = [first.result(timeout=30), second.result(timeout=30)]

    assert sorted(code for code, _ in outcomes) == [
        "quiz_version_conflict",
        "saved",
    ]

    saved_title = next(
        title for code, title in outcomes if code == "saved"
    )

    fetched = client.get(f"/quizzes/{quiz_id}")
    assert fetched.status_code == 200
    assert fetched.json()["version"]["version_number"] == 2
    assert fetched.json()["version"]["title"] == saved_title

    with client.app.state.database.session_factory() as db:
        count = db.scalar(
            select(func.count())
            .select_from(QuizVersion)
            .where(QuizVersion.quiz_id == quiz_id)
        )
        assert count == 2
        