"""Trash and semester changes racing each other, on real MySQL."""

import threading
import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import AccountRole, Class, LiveSession, Quiz, QuizVersion
from app.schemas.classes import ClassSemesterCreate
from app.services.classes import create_semester, lock_course
from app.services.sessions import _lock_hostable_quiz
from tests.integration.test_response_submission import (  # noqa: F401
    ResponseContext,
    response_context,
)

HOLD_SECONDS = 0.5


def _session(context: ResponseContext) -> LiveSession:
    context.db.expire_all()
    return context.db.get(LiveSession, context.scenario.session_id)


def _run_while_held(holder: Session, work) -> dict:
    """Start `work` in another thread, check it waits, then commit `holder`."""
    outcome: dict = {}

    def run() -> None:
        try:
            outcome["result"] = work()
        except APIError as exc:
            outcome["error"] = exc.code

    thread = threading.Thread(target=run)
    thread.start()
    time.sleep(HOLD_SECONDS)
    assert thread.is_alive(), "the second request did not wait for the first"
    holder.commit()
    thread.join(5)
    assert not thread.is_alive()
    return outcome


def test_hosting_waits_for_a_quiz_being_moved_to_the_trash(
    response_context: ResponseContext,
) -> None:
    session = _session(response_context)
    quiz_id = response_context.db.scalar(
        select(QuizVersion.quiz_id).where(
            QuizVersion.quiz_version_id == session.quiz_version_id
        )
    )
    engine = response_context.client.app.state.database.engine

    with Session(engine) as trashing:
        # Holds the quiz row the way trash_quiz does, mid-way through.
        quiz = trashing.scalar(
            select(Quiz).where(Quiz.quiz_id == quiz_id).with_for_update()
        )
        quiz.deleted_at = datetime.now(UTC).replace(tzinfo=None)
        trashing.flush()

        def host() -> int:
            with Session(engine) as hosting:
                return _lock_hostable_quiz(hosting, session.class_id, quiz_id).quiz_id

        outcome = _run_while_held(trashing, host)

    assert outcome == {"error": "quiz_not_found"}


def test_two_requests_cannot_add_the_same_semester(
    response_context: ResponseContext,
) -> None:
    session = _session(response_context)
    db = response_context.db
    course = db.get(Class, session.class_id)
    course.semester = "Fall 2026"
    db.commit()
    organizer = CurrentAccount(course.created_by_id, AccountRole.ADMIN, True)
    engine = response_context.client.app.state.database.engine

    with Session(engine) as first:
        # Another request is half-way through adding Spring 2027.
        lock_course(first, course.class_id)
        first.add(
            Class(
                name=course.name,
                semester="Spring 2027",
                parent_class_id=course.class_id,
                created_by_id=course.created_by_id,
            )
        )
        first.flush()

        def second() -> int:
            with Session(engine) as request:
                return create_semester(
                    request,
                    organizer,
                    course.class_id,
                    ClassSemesterCreate(semester="Spring 2027"),
                ).class_id

        outcome = _run_while_held(first, second)

    assert outcome == {"error": "semester_exists"}
    db.rollback()  # end this test's own snapshot, so it sees the commits

    labels = db.scalars(
        select(Class.semester).where(Class.parent_class_id == course.class_id)
    ).all()
    assert labels == ["Spring 2027"]
