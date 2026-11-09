from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models import (
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    Quiz,
    QuizStatus,
    QuizSubmission,
    QuizVersion,
    SubmissionStatus,
)


@pytest.fixture
def submission_context(mysql_quiz_client) -> dict:
    client, author, _ = mysql_quiz_client
    engine = client.app.state.database.engine
    with Session(engine, expire_on_commit=False) as db:
        class_ = Class(
            name="Task 4 concurrency",
            created_by_id=author.account_id,
            join_code="TASK4TST",
            memberships=[
                ClassMembership(
                    account_id=author.account_id,
                    role=ClassRole.ORGANIZER,
                    joined_via=JoinedVia.CREATOR,
                )
            ],
        )
        quiz = Quiz(
            author_id=author.account_id,
            class_id=None,
            status=QuizStatus.PUBLISHED,
        )
        db.add_all([class_, quiz])
        db.flush()
        quiz.class_id = class_.class_id
        version = QuizVersion(
            quiz_id=quiz.quiz_id,
            version_number=1,
            title="Concurrent submission",
            published_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(version)
        db.commit()
        return {
            "engine": engine,
            "account_id": author.account_id,
            "class_id": class_.class_id,
            "quiz_version_id": version.quiz_version_id,
        }


def test_concurrent_active_duplicates_have_one_winner(submission_context) -> None:
    barrier = Barrier(2)

    def insert_submission() -> str:
        with Session(submission_context["engine"]) as db:
            db.add(
                QuizSubmission(
                    class_id=submission_context["class_id"],
                    quiz_version_id=submission_context["quiz_version_id"],
                    submitted_by_id=submission_context["account_id"],
                )
            )
            barrier.wait()
            try:
                db.commit()
                return "created"
            except IntegrityError:
                db.rollback()
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: insert_submission(), range(2)))

    assert sorted(outcomes) == ["conflict", "created"]
    with Session(submission_context["engine"]) as db:
        rows = db.scalars(
            select(QuizSubmission).where(
                QuizSubmission.class_id == submission_context["class_id"],
                QuizSubmission.quiz_version_id
                == submission_context["quiz_version_id"],
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].status == SubmissionStatus.PENDING


def test_database_rejects_inconsistent_decision_fields(submission_context) -> None:
    invalid_states = [
        (
            SubmissionStatus.PENDING,
            submission_context["account_id"],
            datetime.now(UTC).replace(tzinfo=None),
        ),
        (SubmissionStatus.REJECTED, None, None),
    ]

    for status, decided_by_id, decided_at in invalid_states:
        with Session(submission_context["engine"]) as db:
            db.add(
                QuizSubmission(
                    class_id=submission_context["class_id"],
                    quiz_version_id=submission_context["quiz_version_id"],
                    submitted_by_id=submission_context["account_id"],
                    status=status,
                    decided_by_id=decided_by_id,
                    decided_at=decided_at,
                )
            )
            with pytest.raises(OperationalError):
                db.commit()
            db.rollback()


def test_competing_approve_reject_withdraw_have_one_winner(
    submission_context,
) -> None:
    with Session(submission_context["engine"], expire_on_commit=False) as db:
        submission = QuizSubmission(
            class_id=submission_context["class_id"],
            quiz_version_id=submission_context["quiz_version_id"],
            submitted_by_id=submission_context["account_id"],
        )
        db.add(submission)
        db.commit()
        submission_id = submission.submission_id

    barrier = Barrier(3)

    def transition(status: SubmissionStatus) -> tuple[SubmissionStatus, int]:
        with Session(submission_context["engine"]) as db:
            barrier.wait()
            result = db.execute(
                update(QuizSubmission)
                .where(
                    QuizSubmission.submission_id == submission_id,
                    QuizSubmission.status == SubmissionStatus.PENDING,
                )
                .values(
                    status=status,
                    decided_by_id=submission_context["account_id"],
                    decided_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            db.commit()
            return status, result.rowcount

    statuses = [
        SubmissionStatus.APPROVED,
        SubmissionStatus.REJECTED,
        SubmissionStatus.WITHDRAWN,
    ]
    with ThreadPoolExecutor(max_workers=3) as pool:
        outcomes = list(pool.map(transition, statuses))

    assert sorted(rowcount for _, rowcount in outcomes) == [0, 0, 1]
    winner = next(status for status, rowcount in outcomes if rowcount == 1)
    with Session(submission_context["engine"]) as db:
        stored = db.get(QuizSubmission, submission_id)
        assert stored.status == winner
        assert stored.decided_by_id == submission_context["account_id"]
        assert stored.decided_at is not None
