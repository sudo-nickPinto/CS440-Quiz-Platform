from datetime import datetime
import csv
from io import StringIO

import pytest

from app.auth import CurrentAccount
from app.database import Base, Database
from app.errors import APIError
from app.models import (
    Account,
    AccountRole,
    LiveSession,
    LiveSessionStatus,
    Quiz,
    QuizVersion,
    Question,
    AnswerChoice,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
    Response,
    Result,
)
from app.services.session_report import (
    get_session_report,
    export_session_report,
)

from app.services.session_history import (
    list_quiz_hosting_history,
    list_taken_sessions,
)

HOST = CurrentAccount(1, AccountRole.USER, True)
ALICE = CurrentAccount(2, AccountRole.USER, True)
OUTSIDER = CurrentAccount(4, AccountRole.USER, True)
ADMIN = CurrentAccount(5, AccountRole.ADMIN, True)
NOW = datetime(2026, 10, 18, 12)


@pytest.fixture
def db():
    database = Database("sqlite://")
    Base.metadata.create_all(database.engine)

    with database.session_factory() as session:
        for id_, name in enumerate(["Host", "Alice", "Bob", "Outsider", "Admin"], 1):
            session.add(
                Account(
                    account_id=id_,
                    auth0_sub=f"test|{id_}",
                    email=f"{id_}@test.invalid",
                    display_name=name,
                )
            )

        session.add(Quiz(quiz_id=1, author_id=1))
        session.add(
            QuizVersion(
                quiz_version_id=1,
                quiz_id=1,
                version_number=1,
                title="Report test",
            )
        )
        session.add(
            LiveSession(
                session_id=10,
                quiz_version_id=1,
                host_id=1,
                join_code="123456",
                status=LiveSessionStatus.COMPLETED,
                ended_at=NOW,
            )
        )

        for id_ in (1, 2, 3):
            session.add(
                Question(
                    question_id=id_,
                    quiz_version_id=1,
                    question_order=id_,
                    question_text=f"Question {id_}?",
                    explanation="Explanation",
                    time_limit_seconds=20,
                )
            )
            session.add_all(
                [
                    AnswerChoice(
                        choice_id=id_ * 10,
                        question_id=id_,
                        choice_order=1,
                        choice_text="Right",
                        is_correct=True,
                    ),
                    AnswerChoice(
                        choice_id=id_ * 10 + 1,
                        question_id=id_,
                        choice_order=2,
                        choice_text="Wrong",
                        is_correct=False,
                    ),
                ]
            )

        for pid, aid, score, correct, rank in [
            (20, 2, 875, 1, 1),
            (21, 3, 0, 0, 2),
        ]:
            session.add(
                SessionParticipant(
                    session_participant_id=pid,
                    session_id=10,
                    account_id=aid,
                    joined_at=NOW,
                    left_at=NOW,
                )
            )
            session.add(
                Result(
                    result_id=pid,
                    session_participant_id=pid,
                    total_score=score,
                    correct_count=correct,
                    final_rank=rank,
                    computed_at=NOW,
                )
            )

        for id_ in (1, 2):
            session.add(
                SessionQuestion(
                    session_question_id=100 + id_,
                    session_id=10,
                    question_id=id_,
                    status=SessionQuestionStatus.CLOSED,
                    opened_at=NOW,
                    closed_at=NOW,
                )
            )

        session.add(
            Response(
                response_id=1,
                session_participant_id=20,
                session_question_id=101,
                choice_id=10,
                submitted_at=NOW,
                response_time_ms=5000,
                is_correct=True,
                points_awarded=875,
            )
        )
        session.add(
            Response(
                response_id=2,
                session_participant_id=21,
                session_question_id=101,
                choice_id=11,
                submitted_at=NOW,
                response_time_ms=1000,
                is_correct=False,
                points_awarded=0,
            )
        )

        session.commit()
        yield session

    database.dispose()


def test_host_details_and_unplayed_question(db):
    report = get_session_report(db, HOST, 10)

    assert len(report["players"]) == 2
    assert report["played_count"] == 2

    alice = report["players"][0]
    assert alice["points"] == 875
    assert [a["state"] for a in alice["answers"]] == [
        "correct",
        "missed",
        "not_played",
    ]
    assert alice["answers"][0]["time_ms"] == 5000
    assert report["ended_at"].endswith("+00:00")


def test_participant_only_receives_own_answers_even_after_leaving(db):
    report = get_session_report(db, ALICE, 10)

    assert report["view"] == "participant"
    assert report["total_participants"] == 2
    assert [p["id"] for p in report["players"]] == [20]
    assert report["questions"][0]["choices"][0]["correct"] is True


def test_admin_can_read_full_report(db):
    assert get_session_report(db, ADMIN, 10)["view"] == "host"


def test_outsider_denied(db):
    with pytest.raises(APIError) as error:
        get_session_report(db, OUTSIDER, 10)

    assert error.value.status_code == 403


def test_active_session_denied(db):
    db.get(LiveSession, 10).status = LiveSessionStatus.ACTIVE
    db.commit()

    with pytest.raises(APIError) as error:
        get_session_report(db, HOST, 10)

    assert error.value.status_code == 409


def test_cancelled_session_has_no_report_rows(db):
    db.get(LiveSession, 10).status = LiveSessionStatus.CANCELLED
    db.commit()

    report = get_session_report(db, ALICE, 10)

    assert report["players"] == []
    assert report["questions"] == []


def test_participant_cannot_export(db):
    with pytest.raises(APIError) as error:
        export_session_report(db, ALICE, 10)

    assert error.value.status_code == 403


def test_csv_contains_saved_scores_and_escapes_formulas(db):
    db.get(Account, 2).display_name = "=1+1"
    db.commit()

    rows = list(csv.reader(StringIO(export_session_report(db, HOST, 10))))

    assert ["1", "'=1+1", "875", "1"] in rows


def test_publishing_revision_preserves_historical_report(db):
    from app.schemas.quiz import QuizUpdate
    from app.services.quizzes import update_quiz

    # This existing report fixture creates version 1 without a
    # publication timestamp. Mark it published for this edit test.
    original_version = db.get(QuizVersion, 1)
    original_version.published_at = NOW
    db.commit()

    before = get_session_report(db, HOST, 10)

    payload = QuizUpdate(
        base_version=1,
        title="Changed title for future sessions",
        description="New description",
        questions=[
            {
                "question_text": "A completely different question?",
                "explanation": "A new explanation.",
                "time_limit_seconds": 30,
                "base_points": 2000,
                "choices": [
                    {"choice_text": "New correct answer", "is_correct": True},
                    {"choice_text": "New wrong answer", "is_correct": False},
                ],
            }
        ],
    )

    result = update_quiz(db, HOST, 1, payload)
    assert result.version.version_number == 2

    db.expire_all()
    after = get_session_report(db, HOST, 10)

    assert after == before

def test_taken_history_is_scoped_to_the_current_account(db):
    alice_history = list_taken_sessions(db, ALICE)
    outsider_history = list_taken_sessions(db, OUTSIDER)
    host_history = list_taken_sessions(db, HOST)

    assert [
        row["session_id"] for row in alice_history["items"]
    ] == [10]

    assert outsider_history["items"] == []
    assert host_history["items"] == []


def test_quiz_history_is_restricted_to_author_or_admin(db):
    history = list_quiz_hosting_history(db, HOST, 1)

    assert [row["session_id"] for row in history["items"]] == [10]

    with pytest.raises(APIError):
        list_quiz_hosting_history(db, OUTSIDER, 1)


def test_history_preserves_the_version_used_by_the_session(db):
    db.add(
        QuizVersion(
            quiz_version_id=2,
            quiz_id=1,
            version_number=2,
            title="Edited quiz title",
        )
    )
    db.commit()

    history = list_taken_sessions(db, ALICE)
    row = history["items"][0]

    assert row["quiz_title"] == "Report test"
    assert row["version_number"] == 1


def test_cancelled_session_is_only_in_host_history(db):
    session = db.get(LiveSession, 10)
    session.status = LiveSessionStatus.CANCELLED
    db.commit()

    assert list_taken_sessions(db, ALICE)["items"] == []

    history = list_quiz_hosting_history(db, HOST, 1)
    assert history["items"][0]["status"] == "CANCELLED"


def test_history_pagination(db):
    db.add(
        LiveSession(
            session_id=11,
            quiz_version_id=1,
            host_id=HOST.account_id,
            join_code="654321",
            status=LiveSessionStatus.COMPLETED,
            ended_at=NOW,
        )
    )
    db.commit()

    first = list_quiz_hosting_history(db, HOST, 1, limit=1, offset=0)
    second = list_quiz_hosting_history(db, HOST, 1, limit=1, offset=1)

    assert first["items"][0]["session_id"] == 11
    assert first["has_more"] is True
    assert second["items"][0]["session_id"] == 10
    assert second["has_more"] is False


def test_admin_who_participated_can_request_personal_report(db):
    admin_participant = CurrentAccount(
        ALICE.account_id,
        AccountRole.ADMIN,
        True,
    )

    report = get_session_report(
        db,
        admin_participant,
        10,
        personal=True,
    )

    assert report["view"] == "participant"
    assert len(report["players"]) == 1
    assert report["players"][0]["id"] == 20


def test_personal_report_requires_actual_participation(db):
    with pytest.raises(APIError):
        get_session_report(db, HOST, 10, personal=True)
