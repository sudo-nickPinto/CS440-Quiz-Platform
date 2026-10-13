from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.database import Base, Database
from app.models import (
    LiveSession,
    LiveSessionStatus,
    Response,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.services.live_questions import answer_progress


OPENED_AT = datetime(2026, 10, 12, 16, 0, 0)


@dataclass(frozen=True)
class ProgressSetup:
    db: Session
    session_id: int
    session_question_id: int
    empty_session_id: int
    empty_session_question_id: int
    other_session_question_id: int
    other_question_id: int
    active_participant_id: int
    later_departure_id: int
    early_departure_id: int
    other_session_participant_id: int


@pytest.fixture
def progress_setup() -> Iterator[ProgressSetup]:
    database = Database("sqlite://")
    Base.metadata.create_all(database.engine)

    with database.session_factory() as db:
        session = LiveSession(
            session_id=10,
            quiz_version_id=20,
            host_id=30,
            join_code="123456",
            status=LiveSessionStatus.ACTIVE,
            current_question_order=1,
            started_at=OPENED_AT,
        )
        other_session = LiveSession(
            session_id=11,
            quiz_version_id=21,
            host_id=31,
            join_code="654321",
            status=LiveSessionStatus.ACTIVE,
            current_question_order=1,
            started_at=OPENED_AT,
        )
        empty_session = LiveSession(
            session_id=12,
            quiz_version_id=22,
            host_id=32,
            join_code="000000",
            status=LiveSessionStatus.ACTIVE,
            current_question_order=1,
            started_at=OPENED_AT,
        )
        db.add_all([session, other_session, empty_session])

        played = SessionQuestion(
            session_question_id=100,
            session_id=session.session_id,
            question_id=200,
            status=SessionQuestionStatus.OPEN,
            opened_at=OPENED_AT,
            closes_at=OPENED_AT + timedelta(seconds=30),
        )
        other_question = SessionQuestion(
            session_question_id=101,
            session_id=session.session_id,
            question_id=201,
            status=SessionQuestionStatus.CLOSED,
            opened_at=OPENED_AT - timedelta(minutes=1),
            closes_at=OPENED_AT - timedelta(seconds=30),
            closed_at=OPENED_AT - timedelta(seconds=30),
        )
        other_played = SessionQuestion(
            session_question_id=102,
            session_id=other_session.session_id,
            question_id=202,
            status=SessionQuestionStatus.OPEN,
            opened_at=OPENED_AT,
            closes_at=OPENED_AT + timedelta(seconds=30),
        )
        empty_played = SessionQuestion(
            session_question_id=103,
            session_id=empty_session.session_id,
            question_id=203,
            status=SessionQuestionStatus.OPEN,
            opened_at=OPENED_AT,
            closes_at=OPENED_AT + timedelta(seconds=30),
        )
        db.add_all([played, other_question, other_played, empty_played])

        active = SessionParticipant(
            session_participant_id=300,
            session_id=session.session_id,
            account_id=400,
            joined_at=OPENED_AT - timedelta(minutes=1),
        )
        later_departure = SessionParticipant(
            session_participant_id=301,
            session_id=session.session_id,
            account_id=401,
            joined_at=OPENED_AT - timedelta(minutes=1),
            left_at=OPENED_AT + timedelta(seconds=5),
        )
        late_joiner = SessionParticipant(
            session_participant_id=302,
            session_id=session.session_id,
            account_id=402,
            joined_at=OPENED_AT + timedelta(milliseconds=1),
        )
        early_departure = SessionParticipant(
            session_participant_id=303,
            session_id=session.session_id,
            account_id=403,
            joined_at=OPENED_AT - timedelta(minutes=2),
            left_at=OPENED_AT - timedelta(milliseconds=1),
        )
        other_participant = SessionParticipant(
            session_participant_id=304,
            session_id=other_session.session_id,
            account_id=404,
            joined_at=OPENED_AT - timedelta(minutes=1),
        )
        db.add_all(
            [
                active,
                later_departure,
                late_joiner,
                early_departure,
                other_participant,
            ]
        )
        db.commit()

        yield ProgressSetup(
            db=db,
            session_id=session.session_id,
            session_question_id=played.session_question_id,
            empty_session_id=empty_session.session_id,
            empty_session_question_id=empty_played.session_question_id,
            other_session_question_id=other_played.session_question_id,
            other_question_id=other_question.session_question_id,
            active_participant_id=active.session_participant_id,
            later_departure_id=later_departure.session_participant_id,
            early_departure_id=early_departure.session_participant_id,
            other_session_participant_id=other_participant.session_participant_id,
        )

    database.dispose()


def add_response(
    setup: ProgressSetup,
    participant_id: int,
    session_question_id: int | None = None,
) -> None:
    setup.db.add(
        Response(
            session_participant_id=participant_id,
            session_question_id=(
                session_question_id or setup.session_question_id
            ),
            choice_id=500,
            submitted_at=OPENED_AT + timedelta(seconds=1),
            response_time_ms=1_000,
            is_correct=False,
            points_awarded=0,
        )
    )
    setup.db.commit()


def test_nobody_answered(progress_setup: ProgressSetup) -> None:
    progress = answer_progress(
        progress_setup.db,
        progress_setup.session_id,
        progress_setup.session_question_id,
    )

    assert progress.eligible_count == 2
    assert progress.answered_count == 0
    assert progress.everyone_answered is False


def test_some_participants_answered(progress_setup: ProgressSetup) -> None:
    add_response(progress_setup, progress_setup.active_participant_id)

    progress = answer_progress(
        progress_setup.db,
        progress_setup.session_id,
        progress_setup.session_question_id,
    )

    assert progress.eligible_count == 2
    assert progress.answered_count == 1
    assert progress.everyone_answered is False


def test_everybody_answered(progress_setup: ProgressSetup) -> None:
    add_response(progress_setup, progress_setup.active_participant_id)
    add_response(progress_setup, progress_setup.later_departure_id)

    progress = answer_progress(
        progress_setup.db,
        progress_setup.session_id,
        progress_setup.session_question_id,
    )

    assert progress.eligible_count == 2
    assert progress.answered_count == 2
    assert progress.everyone_answered is True


def test_zero_eligible_participants_is_not_everybody_answered(
    progress_setup: ProgressSetup,
) -> None:
    progress = answer_progress(
        progress_setup.db,
        progress_setup.empty_session_id,
        progress_setup.empty_session_question_id,
    )

    assert progress.eligible_count == 0
    assert progress.answered_count == 0
    assert progress.everyone_answered is False


def test_late_joiner_does_not_block_everybody_answered(
    progress_setup: ProgressSetup,
) -> None:
    add_response(progress_setup, progress_setup.active_participant_id)
    add_response(progress_setup, progress_setup.later_departure_id)

    progress = answer_progress(
        progress_setup.db,
        progress_setup.session_id,
        progress_setup.session_question_id,
    )

    assert progress.eligible_count == 2
    assert progress.answered_count == 2
    assert progress.everyone_answered is True
    played = progress_setup.db.get(
        SessionQuestion,
        progress_setup.session_question_id,
    )
    assert played is not None
    assert played.status == SessionQuestionStatus.OPEN


def test_participant_who_left_before_opening_is_excluded(
    progress_setup: ProgressSetup,
) -> None:
    add_response(progress_setup, progress_setup.early_departure_id)

    progress = answer_progress(
        progress_setup.db,
        progress_setup.session_id,
        progress_setup.session_question_id,
    )

    assert progress.eligible_count == 2
    assert progress.answered_count == 0
    assert progress.everyone_answered is False


def test_participant_active_at_opening_remains_on_frozen_roster(
    progress_setup: ProgressSetup,
) -> None:
    add_response(progress_setup, progress_setup.active_participant_id)

    progress = answer_progress(
        progress_setup.db,
        progress_setup.session_id,
        progress_setup.session_question_id,
    )

    assert progress.eligible_count == 2
    assert progress.answered_count == 1
    assert progress.everyone_answered is False


def test_other_session_and_question_data_do_not_affect_progress(
    progress_setup: ProgressSetup,
) -> None:
    add_response(
        progress_setup,
        progress_setup.active_participant_id,
        progress_setup.other_question_id,
    )
    add_response(
        progress_setup,
        progress_setup.other_session_participant_id,
        progress_setup.other_session_question_id,
    )

    progress = answer_progress(
        progress_setup.db,
        progress_setup.session_id,
        progress_setup.session_question_id,
    )

    assert progress.eligible_count == 2
    assert progress.answered_count == 0
    assert progress.everyone_answered is False
