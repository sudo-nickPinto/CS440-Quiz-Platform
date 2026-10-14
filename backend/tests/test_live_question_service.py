from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.database import Base, Database
from app.errors import APIError
from app.models import (
    Account,
    AccountRole,
    AnswerChoice,
    LiveSession,
    LiveSessionStatus,
    Question,
    QuestionType,
    Quiz,
    QuizStatus,
    QuizVersion,
    QuizVisibility,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.services import live_questions as live_question_service
from app.services.live_questions import open_question


OPENED_AT = datetime(2026, 10, 12, 14, 30, 0)


@dataclass(frozen=True)
class LiveQuestionSetup:
    db: Session
    session_id: int
    host: CurrentAccount
    other: CurrentAccount
    participant_id: int


@pytest.fixture
def live_question_setup() -> Iterator[LiveQuestionSetup]:
    database = Database("sqlite://")
    Base.metadata.create_all(database.engine)

    with database.session_factory() as db:
        host = Account(
            auth0_sub="test|host",
            email="host@test.invalid",
            display_name="Host",
        )
        other = Account(
            auth0_sub="test|other",
            email="other@test.invalid",
            display_name="Other",
            account_type="ADMINISTRATOR",
        )
        participant_account = Account(
            auth0_sub="test|participant",
            email="participant@test.invalid",
            display_name="Participant",
        )
        db.add_all([host, other, participant_account])
        db.flush()

        quiz = Quiz(
            author_id=host.account_id,
            status=QuizStatus.PUBLISHED,
            visibility=QuizVisibility.PUBLIC,
        )
        db.add(quiz)
        db.flush()
        version = QuizVersion(
            quiz_id=quiz.quiz_id,
            version_number=1,
            title="Live Quiz",
            published_at=OPENED_AT - timedelta(days=1),
        )
        db.add(version)
        db.flush()

        first = Question(
            quiz_version_id=version.quiz_version_id,
            question_order=1,
            question_type=QuestionType.MULTIPLE_CHOICE,
            question_text="First question?",
            time_limit_seconds=20,
            base_points=1000,
        )
        second = Question(
            quiz_version_id=version.quiz_version_id,
            question_order=2,
            question_type=QuestionType.MULTIPLE_CHOICE,
            question_text="Second question?",
            time_limit_seconds=45,
            base_points=1000,
        )
        db.add_all([first, second])
        db.flush()
        db.add_all(
            [
                AnswerChoice(
                    question_id=first.question_id,
                    choice_order=2,
                    choice_text="Second display choice",
                    is_correct=False,
                ),
                AnswerChoice(
                    question_id=first.question_id,
                    choice_order=1,
                    choice_text="First display choice",
                    is_correct=True,
                ),
                AnswerChoice(
                    question_id=second.question_id,
                    choice_order=1,
                    choice_text="Only second-question choice",
                    is_correct=True,
                ),
            ]
        )

        live_session = LiveSession(
            quiz_version_id=version.quiz_version_id,
            host_id=host.account_id,
            join_code="123456",
            status=LiveSessionStatus.LOBBY,
        )
        db.add(live_session)
        db.flush()
        participant = SessionParticipant(
            session_id=live_session.session_id,
            account_id=participant_account.account_id,
            joined_at=OPENED_AT - timedelta(minutes=1),
        )
        db.add(participant)
        db.commit()

        yield LiveQuestionSetup(
            db=db,
            session_id=live_session.session_id,
            host=CurrentAccount(host.account_id, AccountRole.USER, True),
            other=CurrentAccount(other.account_id, AccountRole.ADMIN, True),
            participant_id=participant.session_participant_id,
        )

    database.dispose()


def test_first_question_activates_session_with_server_timestamps(
    live_question_setup: LiveQuestionSetup,
) -> None:
    setup = live_question_setup

    event = open_question(
        setup.db,
        setup.host,
        setup.session_id,
        1,
        opened_at=OPENED_AT,
    )

    session = setup.db.get(LiveSession, setup.session_id)
    played = setup.db.scalar(select(SessionQuestion))
    assert session is not None
    assert played is not None
    assert session.status == LiveSessionStatus.ACTIVE
    assert session.started_at == OPENED_AT
    assert session.current_question_order == 1
    assert played.status == SessionQuestionStatus.OPEN
    assert played.opened_at == OPENED_AT
    assert played.closes_at == OPENED_AT + timedelta(seconds=20)
    assert event.session_question_id == played.session_question_id
    assert event.question_order == 1
    assert event.total_questions == 2
    assert event.opened_at == OPENED_AT
    assert event.closes_at == OPENED_AT + timedelta(seconds=20)
    assert [choice.choice_order for choice in event.choices] == [1, 2]


def test_open_time_defaults_to_naive_server_utc(
    live_question_setup: LiveQuestionSetup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = live_question_setup
    monkeypatch.setattr(live_question_service, "_utc_now", lambda: OPENED_AT)

    event = open_question(
        setup.db,
        setup.host,
        setup.session_id,
        1,
    )

    assert event.opened_at == OPENED_AT
    assert event.opened_at.tzinfo is None
    assert event.closes_at == OPENED_AT + timedelta(seconds=20)


def test_only_actual_host_can_open_question(
    live_question_setup: LiveQuestionSetup,
) -> None:
    setup = live_question_setup

    with pytest.raises(APIError) as caught:
        open_question(
            setup.db,
            setup.other,
            setup.session_id,
            1,
            opened_at=OPENED_AT,
        )

    assert caught.value.status_code == 403
    assert caught.value.code == "session_host_denied"


def test_first_question_requires_active_participant(
    live_question_setup: LiveQuestionSetup,
) -> None:
    setup = live_question_setup
    participant = setup.db.get(SessionParticipant, setup.participant_id)
    assert participant is not None
    participant.left_at = OPENED_AT
    setup.db.commit()

    with pytest.raises(APIError) as caught:
        open_question(
            setup.db,
            setup.host,
            setup.session_id,
            1,
            opened_at=OPENED_AT,
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "session_has_no_participants"


def test_next_question_opens_only_after_previous_question_closes(
    live_question_setup: LiveQuestionSetup,
) -> None:
    setup = live_question_setup
    first_event = open_question(
        setup.db,
        setup.host,
        setup.session_id,
        1,
        opened_at=OPENED_AT,
    )
    first_played = setup.db.get(SessionQuestion, first_event.session_question_id)
    assert first_played is not None
    first_played.status = SessionQuestionStatus.CLOSED
    first_played.closed_at = OPENED_AT + timedelta(seconds=20)
    setup.db.commit()

    second_opened_at = OPENED_AT + timedelta(seconds=25)
    event = open_question(
        setup.db,
        setup.host,
        setup.session_id,
        2,
        opened_at=second_opened_at,
    )

    session = setup.db.get(LiveSession, setup.session_id)
    assert session is not None
    assert session.current_question_order == 2
    assert session.started_at == OPENED_AT
    assert event.question_order == 2
    assert event.closes_at == second_opened_at + timedelta(seconds=45)


def test_another_question_cannot_open_while_one_is_open(
    live_question_setup: LiveQuestionSetup,
) -> None:
    setup = live_question_setup
    open_question(
        setup.db,
        setup.host,
        setup.session_id,
        1,
        opened_at=OPENED_AT,
    )

    with pytest.raises(APIError) as caught:
        open_question(
            setup.db,
            setup.host,
            setup.session_id,
            2,
            opened_at=OPENED_AT + timedelta(seconds=1),
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "question_already_open"


def test_repeated_open_returns_original_timer_without_duplicate_row(
    live_question_setup: LiveQuestionSetup,
) -> None:
    setup = live_question_setup
    first = open_question(
        setup.db,
        setup.host,
        setup.session_id,
        1,
        opened_at=OPENED_AT,
    )

    repeated = open_question(
        setup.db,
        setup.host,
        setup.session_id,
        1,
        opened_at=OPENED_AT + timedelta(minutes=5),
    )

    row_count = setup.db.scalar(
        select(func.count()).select_from(SessionQuestion)
    )
    assert repeated == first
    assert repeated.opened_at == OPENED_AT
    assert repeated.closes_at == OPENED_AT + timedelta(seconds=20)
    assert row_count == 1


def test_closed_question_cannot_reopen(
    live_question_setup: LiveQuestionSetup,
) -> None:
    setup = live_question_setup
    event = open_question(
        setup.db,
        setup.host,
        setup.session_id,
        1,
        opened_at=OPENED_AT,
    )
    played = setup.db.get(SessionQuestion, event.session_question_id)
    assert played is not None
    played.status = SessionQuestionStatus.CLOSED
    played.closed_at = event.closes_at
    setup.db.commit()

    with pytest.raises(APIError) as caught:
        open_question(
            setup.db,
            setup.host,
            setup.session_id,
            1,
            opened_at=OPENED_AT + timedelta(minutes=2),
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "question_already_closed"


def test_opened_event_never_reveals_choice_correctness(
    live_question_setup: LiveQuestionSetup,
) -> None:
    setup = live_question_setup

    event = open_question(
        setup.db,
        setup.host,
        setup.session_id,
        1,
        opened_at=OPENED_AT,
    )

    payload = event.model_dump(mode="json")
    assert payload["choices"] == [
        {
            "choice_id": event.choices[0].choice_id,
            "choice_order": 1,
            "choice_text": "First display choice",
        },
        {
            "choice_id": event.choices[1].choice_id,
            "choice_order": 2,
            "choice_text": "Second display choice",
        },
    ]
    assert all("is_correct" not in choice for choice in payload["choices"])


def test_question_order_cannot_be_skipped(
    live_question_setup: LiveQuestionSetup,
) -> None:
    setup = live_question_setup

    with pytest.raises(APIError) as caught:
        open_question(
            setup.db,
            setup.host,
            setup.session_id,
            2,
            opened_at=OPENED_AT,
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "question_order_invalid"


@pytest.mark.parametrize(
    "status",
    [LiveSessionStatus.COMPLETED, LiveSessionStatus.CANCELLED],
)
def test_finished_session_cannot_open_question(
    live_question_setup: LiveQuestionSetup,
    status: LiveSessionStatus,
) -> None:
    setup = live_question_setup
    session = setup.db.get(LiveSession, setup.session_id)
    assert session is not None
    session.status = status
    setup.db.commit()

    with pytest.raises(APIError) as caught:
        open_question(
            setup.db,
            setup.host,
            setup.session_id,
            1,
            opened_at=OPENED_AT,
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "session_not_openable"


def test_database_failure_rolls_back_activation_and_question_insert(
    live_question_setup: LiveQuestionSetup,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = live_question_setup
    original_commit = setup.db.commit

    def fail_commit() -> None:
        raise SQLAlchemyError("database write failed")

    monkeypatch.setattr(setup.db, "commit", fail_commit)
    with pytest.raises(APIError) as caught:
        open_question(
            setup.db,
            setup.host,
            setup.session_id,
            1,
            opened_at=OPENED_AT,
        )
    monkeypatch.setattr(setup.db, "commit", original_commit)

    setup.db.expire_all()
    session = setup.db.get(LiveSession, setup.session_id)
    row_count = setup.db.scalar(
        select(func.count()).select_from(SessionQuestion)
    )
    assert caught.value.status_code == 500
    assert caught.value.code == "question_open_failed"
    assert session is not None
    assert session.status == LiveSessionStatus.LOBBY
    assert session.started_at is None
    assert session.current_question_order is None
    assert row_count == 0
