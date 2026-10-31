from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select, text

from app.errors import APIError
from app.models.quiz import QuizVersion
from app.schemas.quiz import QuizUpdate
from app.services.quizzes import update_class_quiz, update_quiz


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
        "quiz_edit_conflict",
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


def test_owner_and_collaborator_cannot_commit_the_same_revision(
    mysql_quiz_client,
):
    client, owner, editor = mysql_quiz_client
    with client.app.state.database.engine.begin() as connection:
        class_id = connection.execute(
            text(
                "INSERT INTO class "
                "(name, created_by_id, join_code, joining_open) "
                "VALUES ('Concurrent Editing', :owner_id, 'EDITTEST', TRUE)"
            ),
            {"owner_id": owner.account_id},
        ).lastrowid
        connection.execute(
            text(
                "INSERT INTO class_membership "
                "(class_id, account_id, role, status, joined_via) VALUES "
                "(:class_id, :owner_id, 'ORGANIZER', 'ACTIVE', 'CREATOR'), "
                "(:class_id, :editor_id, 'MEMBER', 'ACTIVE', 'INVITE')"
            ),
            {
                "class_id": class_id,
                "owner_id": owner.account_id,
                "editor_id": editor.account_id,
            },
        )

    created = client.post(f"/classes/{class_id}/quizzes", json=PAYLOAD)
    assert created.status_code == 201
    quiz_id = created.json()["quiz_id"]
    shared = client.post(
        f"/classes/{class_id}/quizzes/{quiz_id}/collaborators",
        json={"email": "reader@test.invalid", "permission": "EDITOR"},
    )
    assert shared.status_code == 201

    barrier = Barrier(2)

    def save(account, title):
        payload = QuizUpdate(
            **{
                **PAYLOAD,
                "title": title,
                "expected_revision": 1,
            }
        )
        with client.app.state.database.session_factory() as db:
            barrier.wait(timeout=10)
            try:
                result = update_class_quiz(
                    db,
                    account,
                    class_id,
                    quiz_id,
                    payload,
                )
                return ("saved", result.version.title)
            except APIError as exc:
                return (exc.code, exc.details)

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner_save = executor.submit(save, owner, "Owner edit")
        editor_save = executor.submit(save, editor, "Collaborator edit")
        outcomes = [owner_save.result(timeout=30), editor_save.result(timeout=30)]

    assert sorted(code for code, _ in outcomes) == [
        "quiz_edit_conflict",
        "saved",
    ]
    conflict = next(details for code, details in outcomes if code != "saved")
    assert conflict == {"current_revision": 2}

    current = client.get(f"/classes/{class_id}/quizzes/{quiz_id}")
    assert current.status_code == 200
    assert current.json()["revision"] == 2

