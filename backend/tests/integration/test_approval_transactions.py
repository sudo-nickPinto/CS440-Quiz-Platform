from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy import event, select, text

from app.api.routes import notifications_live
from app.errors import APIError
from app.models import Quiz, QuizSubmission, QuizVersion, SubmissionStatus
from app.schemas.quiz import QuizUpdate
from app.schemas.quiz_submission import QuizSubmissionCreate, QuizSubmissionDecision
from app.services import quizzes
from app.services.quiz_submissions import create_quiz_submission, decide_quiz_submission
from tests.integration.approval_support import approval_class  # noqa: F401


QUIZ = {
    "title": "Original review title",
    "questions": [{
        "question_text": "Original question?",
        "choices": [
            {"choice_text": "Correct", "is_correct": True},
            {"choice_text": "Incorrect", "is_correct": False},
        ],
    }],
}
EDITED_TITLE = "Edited during review"


@pytest.mark.parametrize(
    ("operation", "conflict"),
    [
        ("submit", "quiz_version_stale"),
        ("approve", "invalid_submission_transition"),
        ("save", "quiz_edit_conflict"),
    ],
)
def test_a_waiting_review_or_save_observes_committed_edits(
    approval_class, monkeypatch, operation, conflict
) -> None:
    course = approval_class
    published = course.publish("owner", course.create_quiz("owner", QUIZ))
    quiz_id = published["quiz_id"]
    version_id = published["version"]["quiz_version_id"]
    pending = course.submit("owner", published) if operation != "submit" else None
    organizer = course.accounts["organizer"]
    owner = course.accounts["owner"]
    factory = course.client.app.state.database.session_factory
    original_lock = quizzes._lock_class_quiz_for_update
    waiting_for_lock = Event()

    def observe_lock(db, class_id, locked_quiz_id):
        if db.info.get("competing_request"):
            waiting_for_lock.set()
        return original_lock(db, class_id, locked_quiz_id)

    monkeypatch.setattr(quizzes, "_lock_class_quiz_for_update", observe_lock)

    def competing_request():
        with factory(info={"competing_request": True}) as db:
            connection = db.scalar(text("SELECT CONNECTION_ID()"))
            with pytest.raises(APIError) as error:
                if operation == "submit":
                    create_quiz_submission(
                        db, owner, course.class_id,
                        QuizSubmissionCreate(quiz_version_id=version_id),
                    )
                elif operation == "approve":
                    decide_quiz_submission(
                        db, organizer, course.class_id, pending["submission_id"],
                        QuizSubmissionDecision(status="APPROVED"),
                    )
                else:
                    update = QuizUpdate.model_validate({
                        **QUIZ, "title": "Losing save", "expected_revision": published["revision"],
                    })
                    quizzes.update_class_quiz(db, owner, course.class_id, quiz_id, update)
            return connection, error.value.status_code, error.value.code

    with ThreadPoolExecutor(max_workers=1) as pool, factory() as editor_db:
        original_lock(editor_db, course.class_id, quiz_id)
        editor_connection = editor_db.scalar(text("SELECT CONNECTION_ID()"))
        future = pool.submit(competing_request)
        assert waiting_for_lock.wait(8), "The competing request did not reach the quiz lock"
        update = QuizUpdate.model_validate({
            **QUIZ, "title": EDITED_TITLE, "expected_revision": published["revision"],
        })
        saved = quizzes.update_class_quiz(editor_db, organizer, course.class_id, quiz_id, update)
        competing_connection, status, code = future.result(timeout=12)
        assert competing_connection != editor_connection
        assert (status, code) == (409, conflict)

    with factory() as observer:
        quiz = observer.get(Quiz, quiz_id)
        assert quiz.revision == saved.revision == published["revision"] + 1
        assert [(v.version_number, v.title) for v in quiz.versions] == [
            (1, QUIZ["title"]), (2, EDITED_TITLE),
        ]
        assert quiz.versions[0].quiz_version_id == version_id
        assert quiz.versions[0].published_at is not None
        assert quiz.versions[1].published_at is None
        rows = observer.scalars(
            select(QuizSubmission).where(QuizSubmission.class_id == course.class_id)
        ).all()
        if pending:
            [withdrawn] = rows
            assert withdrawn.submission_id == pending["submission_id"]
            assert withdrawn.status == SubmissionStatus.WITHDRAWN
            assert withdrawn.decided_by_id == organizer.account_id
            assert withdrawn.decided_at is not None
        else:
            assert rows == []


def test_withdrawal_event_is_visible_only_after_the_edit_and_review_commit(
    approval_class, monkeypatch
) -> None:
    course = approval_class
    published = course.publish("owner", course.create_quiz("owner", QUIZ))
    submission = course.submit("owner", published)
    submission_id = submission["submission_id"]
    quiz_id = published["quiz_id"]
    version_id = published["version"]["quiz_version_id"]
    factory = course.client.app.state.database.session_factory
    engine = course.client.app.state.database.engine
    path = f"{course.path}/quizzes/{quiz_id}"
    original = {**QUIZ, "expected_revision": published["revision"]}
    edit = {**original, "title": EDITED_TITLE}

    def assert_pending_version():
        with factory() as db:
            assert db.get(Quiz, quiz_id).revision == published["revision"]
            assert db.get(QuizSubmission, submission_id).status == SubmissionStatus.PENDING
            assert list(db.scalars(
                select(QuizVersion.quiz_version_id).where(QuizVersion.quiz_id == quiz_id)
            )) == [version_id]

    monkeypatch.setattr(notifications_live, "IDLE_TIMEOUT_SECONDS", 15)
    with course.client.websocket_connect("/ws/notifications") as socket:
        socket.send_json({"type": "auth", "token": course.tokens["owner"]})
        assert socket.receive_json() == {"type": "notifications_ready"}

        unchanged = course.request("organizer", "PUT", path, json=original).json()
        assert unchanged["revision"] == published["revision"]
        assert unchanged["version"]["quiz_version_id"] == version_id
        assert_pending_version()
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}

        # Fail after the draft has been written, when the withdrawal is flushed.
        with engine.begin() as conn:
            conn.execute(text(
                "CREATE TRIGGER quiz_test_block_approval_withdrawal "
                "BEFORE UPDATE ON quiz_submission FOR EACH ROW "
                "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'test rollback'"
            ))
        try:
            failed = course.request("organizer", "PUT", path, status=500, json=edit)
            assert failed.json()["error"]["code"] == "quiz_update_failed"
        finally:
            with engine.begin() as conn:
                conn.execute(text("DROP TRIGGER quiz_test_block_approval_withdrawal"))
        assert_pending_version()
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}

        flushed = Event()
        allow_commit = Event()

        def hold_withdrawal_commit(db):
            if any(
                isinstance(row, QuizSubmission)
                and row.submission_id == submission_id
                and row.status == SubmissionStatus.WITHDRAWN
                for row in db.dirty
            ):
                db.flush()
                flushed.set()
                assert allow_commit.wait(8), "Test did not release the withdrawal transaction"

        event.listen(factory, "before_commit", hold_withdrawal_commit)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(course.request, "organizer", "PUT", path, json=edit)
                try:
                    assert flushed.wait(8), "The edit did not reach the commit boundary"
                    assert_pending_version()
                    socket.send_json({"type": "ping"})
                    assert socket.receive_json() == {"type": "pong"}
                finally:
                    allow_commit.set()
                saved = future.result(timeout=12).json()
        finally:
            event.remove(factory, "before_commit", hold_withdrawal_commit)

        message = socket.receive_json()
        assert (message["type"], message["action"], message["status"]) == (
            "submission_changed", "withdrawn", "WITHDRAWN",
        )
        assert (message["submission_id"], message["quiz_id"], message["actor_account_id"]) == (
            submission_id, quiz_id, course.accounts["organizer"].account_id,
        )
        assert saved["version"]["title"] == EDITED_TITLE
        with factory() as db:
            assert db.get(QuizVersion, saved["version"]["quiz_version_id"]).title == EDITED_TITLE
            request = db.get(QuizSubmission, submission_id)
            assert request.status == SubmissionStatus.WITHDRAWN
            assert request.decided_at is not None
        socket.send_json({"type": "ping"})
        assert socket.receive_json() == {"type": "pong"}
