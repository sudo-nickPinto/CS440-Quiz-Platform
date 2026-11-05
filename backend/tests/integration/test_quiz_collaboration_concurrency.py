from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

from sqlalchemy import select, text

from app.errors import APIError
from app.models.quiz import Question, Quiz, QuizStatus, QuizVersion
from app.schemas.quiz import QuestionCreate, QuestionUpdate, QuizPublish
from app.services import quizzes as quiz_service
from app.services.quizzes import (
    add_class_quiz_question,
    archive_quiz,
    publish_class_quiz,
    revoke_quiz_collaborator,
    update_class_quiz_question,
)


QUIZ_PAYLOAD = {
    "title": "Concurrent questions",
    "description": "MySQL race coverage",
    "questions": [
        {
            "question_text": "First question?",
            "time_limit_seconds": 20,
            "base_points": 1000,
            "choices": [
                {"choice_text": "First yes", "is_correct": True},
                {"choice_text": "First no", "is_correct": False},
            ],
        },
        {
            "question_text": "Second question?",
            "time_limit_seconds": 20,
            "base_points": 1000,
            "choices": [
                {"choice_text": "Second yes", "is_correct": True},
                {"choice_text": "Second no", "is_correct": False},
            ],
        },
    ],
}


def _question_update(revision: int, text_value: str) -> QuestionUpdate:
    return QuestionUpdate(
        expected_revision=revision,
        question_text=text_value,
        time_limit_seconds=30,
        base_points=750,
        choices=[
            {"choice_text": "Yes", "is_correct": True},
            {"choice_text": "No", "is_correct": False},
        ],
    )


def _new_question(text_value: str) -> QuestionCreate:
    return QuestionCreate(
        question_text=text_value,
        time_limit_seconds=30,
        base_points=750,
        choices=[
            {"choice_text": "Yes", "is_correct": True},
            {"choice_text": "No", "is_correct": False},
        ],
    )


def _setup_shared_quiz(mysql_quiz_client):
    client, owner, editor = mysql_quiz_client
    with client.app.state.database.engine.begin() as connection:
        class_id = connection.execute(
            text(
                "INSERT INTO class "
                "(name, created_by_id, join_code, joining_open) "
                "VALUES ('Question races', :owner_id, 'QRACE123', TRUE)"
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

    created_response = client.post(
        f"/classes/{class_id}/quizzes",
        json=QUIZ_PAYLOAD,
    )
    assert created_response.status_code == 201
    created = created_response.json()
    shared = client.post(
        f"/classes/{class_id}/quizzes/{created['quiz_id']}/collaborators",
        json={"email": "reader@test.invalid", "permission": "EDITOR"},
    )
    assert shared.status_code == 201
    return client, owner, editor, class_id, created


def _pause_first_question_save_before_quiz_lock(monkeypatch):
    lock_requested = Event()
    allow_lock = Event()
    original_lock = quiz_service._lock_class_quiz_for_update

    def pause_once(db, class_id, quiz_id):
        if not lock_requested.is_set():
            lock_requested.set()
            assert allow_lock.wait(timeout=10)
        return original_lock(db, class_id, quiz_id)

    monkeypatch.setattr(
        quiz_service,
        "_lock_class_quiz_for_update",
        pause_once,
    )
    return lock_requested, allow_lock


def test_different_questions_commit_concurrently_on_mysql(
    mysql_quiz_client,
) -> None:
    client, owner, editor, class_id, quiz = _setup_shared_quiz(
        mysql_quiz_client
    )
    first, second = quiz["version"]["questions"]
    barrier = Barrier(2)

    def save(account, question: dict, text_value: str):
        with client.app.state.database.session_factory() as db:
            barrier.wait(timeout=10)
            return update_class_quiz_question(
                db,
                account,
                class_id,
                quiz["quiz_id"],
                question["question_id"],
                _question_update(question["revision"], text_value),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        owner_save = executor.submit(save, owner, first, "Owner changed first")
        editor_save = executor.submit(save, editor, second, "Editor changed second")
        results = [owner_save.result(timeout=30), editor_save.result(timeout=30)]

    assert sorted(result.question.question_text for result in results) == [
        "Editor changed second",
        "Owner changed first",
    ]
    assert sorted(result.question.revision for result in results) == [2, 2]
    with client.app.state.database.session_factory() as db:
        stored = db.scalars(
            select(Question)
            .where(Question.quiz_version_id == quiz["version"]["quiz_version_id"])
            .order_by(Question.question_order)
        ).all()
        assert [question.question_text for question in stored] == [
            "Owner changed first",
            "Editor changed second",
        ]


def test_append_and_existing_question_edit_commit_concurrently_on_mysql(
    mysql_quiz_client,
) -> None:
    client, owner, editor, class_id, quiz = _setup_shared_quiz(
        mysql_quiz_client
    )
    second = quiz["version"]["questions"][1]
    barrier = Barrier(2)

    def append():
        with client.app.state.database.session_factory() as db:
            barrier.wait(timeout=10)
            return add_class_quiz_question(
                db,
                owner,
                class_id,
                quiz["quiz_id"],
                _new_question("Owner appended third"),
            )

    def edit():
        with client.app.state.database.session_factory() as db:
            barrier.wait(timeout=10)
            return update_class_quiz_question(
                db,
                editor,
                class_id,
                quiz["quiz_id"],
                second["question_id"],
                _question_update(second["revision"], "Editor changed second"),
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        appended = executor.submit(append)
        edited = executor.submit(edit)
        assert appended.result(timeout=30).question.question_order == 3
        assert edited.result(timeout=30).question.question_text == (
            "Editor changed second"
        )

    with client.app.state.database.session_factory() as db:
        version = db.get(QuizVersion, quiz["version"]["quiz_version_id"])
        assert [
            question.question_text
            for question in sorted(
                version.questions,
                key=lambda question: question.question_order,
            )
        ] == [
            "First question?",
            "Editor changed second",
            "Owner appended third",
        ]


def test_edit_waiting_before_publish_updates_new_draft_not_published_version(
    mysql_quiz_client,
    monkeypatch,
) -> None:
    client, owner, _, class_id, quiz = _setup_shared_quiz(mysql_quiz_client)
    first = quiz["version"]["questions"][0]
    lock_requested, allow_lock = (
        _pause_first_question_save_before_quiz_lock(monkeypatch)
    )

    def save_question():
        with client.app.state.database.session_factory() as db:
            try:
                update_class_quiz_question(
                    db,
                    owner,
                    class_id,
                    quiz["quiz_id"],
                    first["question_id"],
                    _question_update(first["revision"], "Must not reach published"),
                )
                return "saved"
            except APIError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending_save = executor.submit(save_question)
        try:
            assert lock_requested.wait(timeout=10)
            with client.app.state.database.session_factory() as db:
                published = publish_class_quiz(
                    db,
                    owner,
                    class_id,
                    quiz["quiz_id"],
                    QuizPublish(expected_revision=quiz["revision"]),
                )
        finally:
            allow_lock.set()
        outcome = pending_save.result(timeout=30)

    assert published.status == QuizStatus.PUBLISHED
    assert outcome == "saved"
    with client.app.state.database.session_factory() as db:
        versions = db.scalars(
            select(QuizVersion)
            .where(QuizVersion.quiz_id == quiz["quiz_id"])
            .order_by(QuizVersion.version_number)
        ).all()
        assert len(versions) == 2
        assert versions[0].published_at is not None
        assert versions[0].questions[0].question_text == "First question?"
        assert versions[1].published_at is None
        assert versions[1].questions[0].question_text == "Must not reach published"


def test_archive_wins_before_question_lock_without_being_undone(
    mysql_quiz_client,
    monkeypatch,
) -> None:
    client, owner, _, class_id, quiz = _setup_shared_quiz(mysql_quiz_client)
    first = quiz["version"]["questions"][0]
    lock_requested, allow_lock = (
        _pause_first_question_save_before_quiz_lock(monkeypatch)
    )

    def save_question():
        with client.app.state.database.session_factory() as db:
            try:
                update_class_quiz_question(
                    db,
                    owner,
                    class_id,
                    quiz["quiz_id"],
                    first["question_id"],
                    _question_update(first["revision"], "Must not restore draft"),
                )
                return "saved"
            except APIError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending_save = executor.submit(save_question)
        try:
            assert lock_requested.wait(timeout=10)
            with client.app.state.database.session_factory() as db:
                archived = archive_quiz(db, owner, quiz["quiz_id"])
        finally:
            allow_lock.set()
        outcome = pending_save.result(timeout=30)

    assert archived.status == QuizStatus.ARCHIVED
    assert outcome == "quiz_not_editable"
    with client.app.state.database.session_factory() as db:
        stored_quiz = db.get(Quiz, quiz["quiz_id"])
        stored = db.get(Question, first["question_id"])
        assert stored_quiz.status == QuizStatus.ARCHIVED
        assert stored.question_text == "First question?"


def test_stale_v1_question_is_mapped_to_current_v2_draft(
    mysql_quiz_client,
    monkeypatch,
) -> None:
    client, owner, editor, class_id, quiz = _setup_shared_quiz(
        mysql_quiz_client
    )
    first, second = quiz["version"]["questions"]
    lock_requested, allow_lock = (
        _pause_first_question_save_before_quiz_lock(monkeypatch)
    )

    def save_first():
        with client.app.state.database.session_factory() as db:
            return update_class_quiz_question(
                db,
                editor,
                class_id,
                quiz["quiz_id"],
                first["question_id"],
                _question_update(first["revision"], "Editor changed V2 first"),
            )

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending_save = executor.submit(save_first)
        try:
            assert lock_requested.wait(timeout=10)
            with client.app.state.database.session_factory() as db:
                publish_class_quiz(
                    db,
                    owner,
                    class_id,
                    quiz["quiz_id"],
                    QuizPublish(expected_revision=quiz["revision"]),
                )
            with client.app.state.database.session_factory() as db:
                update_class_quiz_question(
                    db,
                    owner,
                    class_id,
                    quiz["quiz_id"],
                    second["question_id"],
                    _question_update(second["revision"], "Owner changed V2 second"),
                )
        finally:
            allow_lock.set()
        result = pending_save.result(timeout=30)

    assert result.question.question_text == "Editor changed V2 first"
    with client.app.state.database.session_factory() as db:
        versions = db.scalars(
            select(QuizVersion)
            .where(QuizVersion.quiz_id == quiz["quiz_id"])
            .order_by(QuizVersion.version_number)
        ).all()
        assert len(versions) == 2
        assert [question.question_text for question in versions[0].questions] == [
            "First question?",
            "Second question?",
        ]
        assert [question.question_text for question in versions[1].questions] == [
            "Editor changed V2 first",
            "Owner changed V2 second",
        ]


def test_revocation_wins_controlled_race_without_committing_late_edit(
    mysql_quiz_client,
    monkeypatch,
) -> None:
    client, owner, editor, class_id, quiz = _setup_shared_quiz(
        mysql_quiz_client
    )
    first = quiz["version"]["questions"][0]
    lock_requested, allow_lock = (
        _pause_first_question_save_before_quiz_lock(monkeypatch)
    )

    def save_question():
        with client.app.state.database.session_factory() as db:
            try:
                update_class_quiz_question(
                    db,
                    editor,
                    class_id,
                    quiz["quiz_id"],
                    first["question_id"],
                    _question_update(first["revision"], "Revoked edit"),
                )
                return "saved"
            except APIError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending_save = executor.submit(save_question)
        try:
            assert lock_requested.wait(timeout=10)
            with client.app.state.database.session_factory() as db:
                revoke_quiz_collaborator(
                    db,
                    owner,
                    class_id,
                    quiz["quiz_id"],
                    editor.account_id,
                )
        finally:
            allow_lock.set()
        outcome = pending_save.result(timeout=30)

    assert outcome == "quiz_edit_denied"
    with client.app.state.database.session_factory() as db:
        stored = db.get(Question, first["question_id"])
        assert stored.question_text == "First question?"

