from datetime import datetime

import pytest

from app.auth import CurrentAccount
from app.database import Base, Database
from app.errors import APIError
from app.models import (
    Account,
    AccountRole,
    AnswerChoice,
    Class,
    ClassMembership,
    ClassRole,
    LiveSession,
    LiveSessionStatus,
    Question,
    Quiz,
    QuizVersion,
    Response,
    Result,
    SessionAnswerCorrection,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.services.session_corrections import (
    correct_session_answer,
    preview_session_answer_correction,
)
from app.schemas.session_correction import CorrectSessionAnswerRequest
from app.services.session_report import build_session_report
from app.services.session_end import load_final_results


NOW = datetime(2026, 11, 11, 12)
ORGANIZER = CurrentAccount(1, AccountRole.ADMIN, True)
MEMBER = CurrentAccount(2, AccountRole.USER, True)
OUTSIDER_FACULTY = CurrentAccount(4, AccountRole.ADMIN, True)


@pytest.fixture
def db():
    database = Database("sqlite://")
    Base.metadata.create_all(database.engine)
    with database.session_factory() as session:
        session.add_all(
            [
                Account(account_id=1, auth0_sub="test|org", email="org@test", display_name="Organizer", account_type="ADMINISTRATOR"),
                Account(account_id=2, auth0_sub="test|alice", email="alice@test", display_name="Alice"),
                Account(account_id=3, auth0_sub="test|bob", email="bob@test", display_name="Bob"),
                Account(account_id=4, auth0_sub="test|other", email="other@test", display_name="Other faculty", account_type="ADMINISTRATOR"),
            ]
        )
        session.add(Class(class_id=1, name="CS 440", created_by_id=1, join_code="ABCDEFGH"))
        session.add_all(
            [
                ClassMembership(class_id=1, account_id=1, role=ClassRole.ORGANIZER),
                ClassMembership(class_id=1, account_id=2),
                ClassMembership(class_id=1, account_id=3),
            ]
        )
        session.add(Quiz(quiz_id=1, author_id=2, class_id=1))
        session.add(QuizVersion(quiz_version_id=1, quiz_id=1, version_number=1, title="Correction test"))
        session.add(Question(question_id=1, quiz_version_id=1, question_order=1, question_text="Two plus two?", time_limit_seconds=20, base_points=1000))
        session.add_all(
            [
                AnswerChoice(choice_id=10, question_id=1, choice_order=1, choice_text="Four", is_correct=True),
                AnswerChoice(choice_id=11, question_id=1, choice_order=2, choice_text="Five", is_correct=False),
            ]
        )
        session.add(LiveSession(session_id=1, quiz_version_id=1, host_id=1, class_id=1, join_code="123456", status=LiveSessionStatus.COMPLETED, ended_at=NOW))
        session.add(SessionQuestion(session_question_id=1, session_id=1, question_id=1, status=SessionQuestionStatus.CLOSED, opened_at=NOW, closed_at=NOW))
        session.add_all(
            [
                SessionParticipant(session_participant_id=1, session_id=1, account_id=2, joined_at=NOW),
                SessionParticipant(session_participant_id=2, session_id=1, account_id=3, joined_at=NOW),
            ]
        )
        session.add_all(
            [
                Response(response_id=1, session_participant_id=1, session_question_id=1, choice_id=10, submitted_at=NOW, response_time_ms=5000, is_correct=True, points_awarded=875),
                Response(response_id=2, session_participant_id=2, session_question_id=1, choice_id=11, submitted_at=NOW, response_time_ms=100, is_correct=False, points_awarded=0),
                Result(result_id=1, session_participant_id=1, total_score=875, correct_count=1, final_rank=1, computed_at=NOW),
                Result(result_id=2, session_participant_id=2, total_score=0, correct_count=0, final_rank=2, computed_at=NOW),
            ]
        )
        session.commit()
        yield session
    database.dispose()


def test_preview_then_correct_rescores_without_mutating_quiz(db):
    preview = preview_session_answer_correction(db, ORGANIZER, 1, 1, 11)

    assert preview.score_revision == 0
    assert preview.affected_response_count == 2
    assert [(p.display_name, p.new_total_score, p.new_rank) for p in preview.affected_participants] == [("Bob", 1000, 1), ("Alice", 0, 2)]
    assert db.get(Response, 1).points_awarded == 875

    result = correct_session_answer(db, ORGANIZER, 1, 1, 11, "The answer key was wrong.", 0)

    assert result.score_revision == 1
    assert db.get(LiveSession, 1).score_revision == 1
    assert db.get(SessionQuestion, 1).corrected_choice_id == 11
    assert (db.get(Response, 1).is_correct, db.get(Response, 1).points_awarded) == (False, 0)
    assert (db.get(Response, 2).is_correct, db.get(Response, 2).points_awarded) == (True, 1000)
    assert (db.get(Result, 1).total_score, db.get(Result, 1).final_rank) == (0, 2)
    assert (db.get(Result, 2).total_score, db.get(Result, 2).final_rank) == (1000, 1)
    assert db.get(AnswerChoice, 10).is_correct is True
    assert db.get(AnswerChoice, 11).is_correct is False
    audit = db.get(SessionAnswerCorrection, result.correction_id)
    assert (audit.previous_correct_choice_id, audit.corrected_choice_id, audit.reason) == (10, 11, "The answer key was wrong.")


def test_stale_preview_and_unauthorized_users_are_rejected(db):
    with pytest.raises(APIError) as member_error:
        preview_session_answer_correction(db, MEMBER, 1, 1, 11)
    assert member_error.value.code == "not_class_organizer"

    with pytest.raises(APIError) as outsider_error:
        preview_session_answer_correction(db, OUTSIDER_FACULTY, 1, 1, 11)
    assert outsider_error.value.code == "class_not_found"

    correct_session_answer(db, ORGANIZER, 1, 1, 11, "Correction", 0)
    with pytest.raises(APIError) as stale_error:
        correct_session_answer(db, ORGANIZER, 1, 1, 10, "Undo", 0)
    assert stale_error.value.code == "score_revision_conflict"
    assert stale_error.value.details == {"current_revision": 1}


def test_report_uses_session_override_and_exposes_audit(db):
    correct_session_answer(db, ORGANIZER, 1, 1, 11, "Correction", 0)
    session = db.get(LiveSession, 1)
    report = build_session_report(db, session, load_final_results(db, session), None)

    assert report["score_revision"] == 1
    assert report["questions"][0]["corrected"] is True
    assert [choice["id"] for choice in report["questions"][0]["choices"] if choice["correct"]] == [11]
    assert report["corrections"][0]["reason"] == "Correction"


def test_request_uses_an_auditable_default_reason():
    payload = CorrectSessionAnswerRequest(
        choice_id=11,
        expected_score_revision=0,
    )
    assert payload.reason == "Corrected by class organizer."

    blank = CorrectSessionAnswerRequest(
        choice_id=11,
        reason="   ",
        expected_score_revision=0,
    )
    assert blank.reason == "Corrected by class organizer."
