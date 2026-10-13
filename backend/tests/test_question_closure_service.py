from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base, Database
from app.errors import APIError
from app.models import (
    LiveSession,
    LiveSessionStatus,
    Question,
    Response,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.schemas.live_question import QuestionCloseReason
from app.services import live_questions as live_question_service
from app.services.live_questions import close_question_if_ready


OPENED_AT = datetime(2026, 10, 12, 18, 0, 0)
CLOSES_AT = OPENED_AT + timedelta(seconds=30)


@dataclass(frozen=True)
class ClosureSetup:
    database: Database
    db: Session
    session_id: int
    session_question_id: int
    participant_ids: tuple[int, int]


@pytest.fixture
def closure_setup(tmp_path) -> Iterator[ClosureSetup]:
    database = Database(f"sqlite:///{tmp_path / 'question-close.db'}")
    Base.metadata.create_all(database.engine)

    with database.session_factory() as db:
        question = Question(
            question_id=200,
            quiz_version_id=20,
            question_order=1,
            question_text="Close me once?",
            time_limit_seconds=30,
            base_points=1000,
        )
        session = LiveSession(
            session_id=10,
            quiz_version_id=20,
            host_id=30,
            join_code="123456",
            status=LiveSessionStatus.ACTIVE,
            current_question_order=1,
            started_at=OPENED_AT,
        )
        played = SessionQuestion(
            session_question_id=100,
            session_id=session.session_id,
            question_id=question.question_id,
            status=SessionQuestionStatus.OPEN,
            opened_at=OPENED_AT,
            closes_at=CLOSES_AT,
        )
        first = SessionParticipant(
            session_participant_id=300,
            session_id=session.session_id,
            account_id=400,
            joined_at=OPENED_AT - timedelta(minutes=1),
        )
        second = SessionParticipant(
            session_participant_id=301,
            session_id=session.session_id,
            account_id=401,
            joined_at=OPENED_AT - timedelta(seconds=1),
        )
        db.add_all([question, session, played, first, second])
        db.commit()

        yield ClosureSetup(
            database=database,
            db=db,
            session_id=session.session_id,
            session_question_id=played.session_question_id,
            participant_ids=(
                first.session_participant_id,
                second.session_participant_id,
            ),
        )

    database.dispose()


def add_answers(setup: ClosureSetup, *participant_ids: int) -> None:
    for offset, participant_id in enumerate(participant_ids, start=1):
        setup.db.add(
            Response(
                session_participant_id=participant_id,
                session_question_id=setup.session_question_id,
                choice_id=500,
                submitted_at=OPENED_AT + timedelta(seconds=offset),
                response_time_ms=offset * 1_000,
                is_correct=False,
                points_awarded=0,
            )
        )
    setup.db.commit()


def test_question_stays_open_when_not_ready(
    closure_setup: ClosureSetup,
) -> None:
    result = close_question_if_ready(
        closure_setup.db,
        closure_setup.session_id,
        closure_setup.session_question_id,
        checked_at=OPENED_AT + timedelta(seconds=10),
    )

    closure_setup.db.expire_all()
    played = closure_setup.db.get(
        SessionQuestion,
        closure_setup.session_question_id,
    )
    assert result is None
    assert played is not None
    assert played.status == SessionQuestionStatus.OPEN
    assert played.closed_at is None


def test_everyone_answering_closes_question_early(
    closure_setup: ClosureSetup,
) -> None:
    add_answers(closure_setup, *closure_setup.participant_ids)
    checked_at = OPENED_AT + timedelta(seconds=10)

    event = close_question_if_ready(
        closure_setup.db,
        closure_setup.session_id,
        closure_setup.session_question_id,
        checked_at=checked_at,
    )

    assert event is not None
    assert event.reason == QuestionCloseReason.ALL_ANSWERED
    assert event.eligible_count == 2
    assert event.answered_count == 2
    assert event.closed_at == checked_at


def test_deadline_closes_question_without_all_answers(
    closure_setup: ClosureSetup,
) -> None:
    checked_at = CLOSES_AT + timedelta(milliseconds=1)

    event = close_question_if_ready(
        closure_setup.db,
        closure_setup.session_id,
        closure_setup.session_question_id,
        checked_at=checked_at,
    )

    assert event is not None
    assert event.reason == QuestionCloseReason.DEADLINE
    assert event.eligible_count == 2
    assert event.answered_count == 0
    assert event.closed_at == checked_at


def test_close_time_defaults_to_naive_server_utc(
    closure_setup: ClosureSetup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(live_question_service, "_utc_now", lambda: CLOSES_AT)

    event = close_question_if_ready(
        closure_setup.db,
        closure_setup.session_id,
        closure_setup.session_question_id,
    )

    assert event is not None
    assert event.reason == QuestionCloseReason.DEADLINE
    assert event.closed_at == CLOSES_AT
    assert event.closed_at.tzinfo is None


def test_exact_deadline_uses_deadline_reason_even_when_everyone_answered(
    closure_setup: ClosureSetup,
) -> None:
    add_answers(closure_setup, *closure_setup.participant_ids)

    event = close_question_if_ready(
        closure_setup.db,
        closure_setup.session_id,
        closure_setup.session_question_id,
        checked_at=CLOSES_AT,
    )

    assert event is not None
    assert event.reason == QuestionCloseReason.DEADLINE
    assert event.answered_count == event.eligible_count == 2


def test_repeated_close_returns_none_and_keeps_original_closed_at(
    closure_setup: ClosureSetup,
) -> None:
    first_checked_at = CLOSES_AT + timedelta(seconds=1)
    first = close_question_if_ready(
        closure_setup.db,
        closure_setup.session_id,
        closure_setup.session_question_id,
        checked_at=first_checked_at,
    )
    repeated = close_question_if_ready(
        closure_setup.db,
        closure_setup.session_id,
        closure_setup.session_question_id,
        checked_at=CLOSES_AT + timedelta(seconds=5),
    )

    closure_setup.db.expire_all()
    played = closure_setup.db.get(
        SessionQuestion,
        closure_setup.session_question_id,
    )
    assert first is not None
    assert repeated is None
    assert played is not None
    assert played.closed_at == first_checked_at


def test_competing_stale_caller_cannot_close_twice(
    closure_setup: ClosureSetup,
) -> None:
    competing_db = closure_setup.database.session_factory()
    try:
        stale = competing_db.get(
            SessionQuestion,
            closure_setup.session_question_id,
        )
        assert stale is not None
        assert stale.status == SessionQuestionStatus.OPEN

        winner = close_question_if_ready(
            closure_setup.db,
            closure_setup.session_id,
            closure_setup.session_question_id,
            checked_at=CLOSES_AT,
        )
        loser = close_question_if_ready(
            competing_db,
            closure_setup.session_id,
            closure_setup.session_question_id,
            checked_at=CLOSES_AT,
        )

        assert winner is not None
        assert loser is None
    finally:
        competing_db.close()


@pytest.mark.parametrize(
    ("session_id", "session_question_id"),
    [(999, 100), (10, 999)],
)
def test_wrong_session_or_question_is_rejected(
    closure_setup: ClosureSetup,
    session_id: int,
    session_question_id: int,
) -> None:
    with pytest.raises(APIError) as caught:
        close_question_if_ready(
            closure_setup.db,
            session_id,
            session_question_id,
            checked_at=CLOSES_AT,
        )

    assert caught.value.status_code == 404
    assert caught.value.code == "session_question_not_found"


@pytest.mark.parametrize(
    ("opened_at", "closes_at"),
    [
        (None, CLOSES_AT),
        (OPENED_AT, None),
        (OPENED_AT, OPENED_AT),
        (OPENED_AT, OPENED_AT - timedelta(milliseconds=1)),
    ],
)
def test_invalid_or_missing_stored_timestamps_are_rejected(
    closure_setup: ClosureSetup,
    opened_at: datetime | None,
    closes_at: datetime | None,
) -> None:
    played = closure_setup.db.get(
        SessionQuestion,
        closure_setup.session_question_id,
    )
    assert played is not None
    played.opened_at = opened_at
    played.closes_at = closes_at
    closure_setup.db.commit()

    with pytest.raises(APIError) as caught:
        close_question_if_ready(
            closure_setup.db,
            closure_setup.session_id,
            closure_setup.session_question_id,
            checked_at=CLOSES_AT,
        )

    assert caught.value.status_code == 500
    assert caught.value.code == "invalid_question_timing"


def test_closing_persists_status_and_actual_time_without_changing_deadline(
    closure_setup: ClosureSetup,
) -> None:
    checked_at = CLOSES_AT + timedelta(seconds=2)

    event = close_question_if_ready(
        closure_setup.db,
        closure_setup.session_id,
        closure_setup.session_question_id,
        checked_at=checked_at,
    )

    closure_setup.db.expire_all()
    played = closure_setup.db.scalar(
        select(SessionQuestion).where(
            SessionQuestion.session_question_id
            == closure_setup.session_question_id
        )
    )
    assert event is not None
    assert played is not None
    assert played.status == SessionQuestionStatus.CLOSED
    assert played.opened_at == OPENED_AT
    assert played.closes_at == CLOSES_AT
    assert played.closed_at == checked_at
