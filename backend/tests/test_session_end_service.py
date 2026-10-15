"""Unit tests for the host controls: skip, end, cancel, leave, final results."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
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
    Response,
    Result,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.schemas.live_question import QuestionCloseReason
from app.schemas.results import participant_final_view
from app.services.live_questions import close_question_now
from app.services.session_end import (
    cancel_session,
    end_session,
    get_final_results,
    leave_session,
)

T0 = datetime(2026, 10, 15, 18, 0, 0)
SESSION_ID = 10
Q1, Q2 = 100, 101
HOST = CurrentAccount(1, AccountRole.USER, True)
ALICE = CurrentAccount(2, AccountRole.USER, True)
BOB = CurrentAccount(3, AccountRole.USER, True)
CAROL = CurrentAccount(4, AccountRole.USER, True)
OUTSIDER = CurrentAccount(5, AccountRole.USER, True)
ADMIN = CurrentAccount(6, AccountRole.ADMIN, True)
PARTICIPANT_IDS = {"alice": 20, "bob": 21, "carol": 22}


@dataclass(frozen=True)
class Setup:
    database: Database
    db: Session


@pytest.fixture
def setup(tmp_path) -> Iterator[Setup]:
    """An ACTIVE session: Q1 closed (Alice and Bob scored 900), Q2 open."""
    database = Database(f"sqlite:///{tmp_path / 'session-end.db'}")
    Base.metadata.create_all(database.engine)

    with database.session_factory() as db:
        for account_id, name in enumerate(
            ["Host", "Alice", "Bob", "Carol", "Outsider", "Admin"], start=1
        ):
            db.add(
                Account(
                    account_id=account_id,
                    auth0_sub=f"test|{name.lower()}",
                    email=f"{name.lower()}@test.invalid",
                    display_name=name,
                )
            )
        for question_id, order in ((200, 1), (201, 2)):
            db.add(
                Question(
                    question_id=question_id,
                    quiz_version_id=30,
                    question_order=order,
                    question_text=f"Question {order}?",
                    time_limit_seconds=30,
                    base_points=1000,
                )
            )
            db.add_all(
                [
                    AnswerChoice(
                        choice_id=question_id * 10 + 1,
                        question_id=question_id,
                        choice_order=1,
                        choice_text="Right",
                        is_correct=True,
                    ),
                    AnswerChoice(
                        choice_id=question_id * 10 + 2,
                        question_id=question_id,
                        choice_order=2,
                        choice_text="Wrong",
                        is_correct=False,
                    ),
                ]
            )
        db.add(
            LiveSession(
                session_id=SESSION_ID,
                quiz_version_id=30,
                host_id=HOST.account_id,
                join_code="123456",
                status=LiveSessionStatus.ACTIVE,
                current_question_order=2,
                started_at=T0,
            )
        )
        for name, account in (("alice", ALICE), ("bob", BOB), ("carol", CAROL)):
            db.add(
                SessionParticipant(
                    session_participant_id=PARTICIPANT_IDS[name],
                    session_id=SESSION_ID,
                    account_id=account.account_id,
                    joined_at=T0 - timedelta(minutes=1),
                )
            )
        db.add_all(
            [
                SessionQuestion(
                    session_question_id=Q1,
                    session_id=SESSION_ID,
                    question_id=200,
                    status=SessionQuestionStatus.CLOSED,
                    opened_at=T0,
                    closes_at=T0 + timedelta(seconds=30),
                    closed_at=T0 + timedelta(seconds=10),
                ),
                SessionQuestion(
                    session_question_id=Q2,
                    session_id=SESSION_ID,
                    question_id=201,
                    status=SessionQuestionStatus.OPEN,
                    opened_at=T0 + timedelta(minutes=1),
                    closes_at=T0 + timedelta(minutes=1, seconds=30),
                ),
            ]
        )
        db.flush()
        add_response(db, "alice", Q1, 2001, correct=True, points=900)
        add_response(db, "bob", Q1, 2001, correct=True, points=900)
        add_response(db, "carol", Q1, 2002, correct=False, points=0)
        db.commit()
        yield Setup(database=database, db=db)

    database.dispose()


def add_response(
    db: Session, name: str, sqid: int, choice_id: int, *, correct: bool, points: int
) -> None:
    db.add(
        Response(
            session_participant_id=PARTICIPANT_IDS[name],
            session_question_id=sqid,
            choice_id=choice_id,
            submitted_at=T0,
            response_time_ms=1_000,
            is_correct=correct,
            points_awarded=points,
        )
    )


def close_q2(db: Session) -> None:
    played = db.get(SessionQuestion, Q2)
    played.status = SessionQuestionStatus.CLOSED
    played.closed_at = T0 + timedelta(minutes=1, seconds=5)
    db.commit()


# end_session ---------------------------------------------------------------


def test_end_session_closes_open_question_and_writes_results(setup: Setup) -> None:
    add_response(setup.db, "alice", Q2, 2011, correct=True, points=500)
    setup.db.commit()
    ended_at = T0 + timedelta(minutes=1, seconds=10)

    ended = end_session(setup.db, HOST, SESSION_ID, ended_at=ended_at)

    # The open question closes with reason HOST, inside the same transaction.
    assert ended.closed_question is not None
    assert ended.closed_question.session_question_id == Q2
    assert ended.closed_question.reason == QuestionCloseReason.HOST
    assert ended.closed_question.answered_count == 1
    assert ended.closed_question.eligible_count == 3

    standings = [
        (row.display_name, row.total_score, row.correct_count, row.final_rank)
        for row in ended.results.standings
    ]
    assert standings == [("Alice", 1400, 2, 1), ("Bob", 900, 1, 2), ("Carol", 0, 0, 3)]
    assert ended.results.status == "COMPLETED"

    setup.db.expire_all()
    session = setup.db.get(LiveSession, SESSION_ID)
    assert session.status == LiveSessionStatus.COMPLETED
    assert session.ended_at == ended_at
    assert setup.db.get(SessionQuestion, Q2).status == SessionQuestionStatus.CLOSED
    stored = {
        row.session_participant_id: (row.total_score, row.correct_count, row.final_rank)
        for row in setup.db.scalars(select(Result)).all()
    }
    assert stored == {20: (1400, 2, 1), 21: (900, 1, 2), 22: (0, 0, 3)}


def test_end_session_ties_share_a_rank_like_sql_rank(setup: Setup) -> None:
    close_q2(setup.db)

    ended = end_session(setup.db, HOST, SESSION_ID, ended_at=T0 + timedelta(minutes=2))

    assert ended.closed_question is None
    assert [(r.display_name, r.final_rank) for r in ended.results.standings] == [
        ("Alice", 1),
        ("Bob", 1),
        ("Carol", 3),
    ]


def test_end_session_counts_participants_who_left(setup: Setup) -> None:
    close_q2(setup.db)
    setup.db.get(SessionParticipant, PARTICIPANT_IDS["bob"]).left_at = T0
    setup.db.commit()

    ended = end_session(setup.db, HOST, SESSION_ID)

    assert {r.display_name for r in ended.results.standings} == {"Alice", "Bob", "Carol"}


@pytest.mark.parametrize(
    "account, status, code",
    [
        (ALICE, LiveSessionStatus.ACTIVE, "session_host_denied"),
        (HOST, LiveSessionStatus.LOBBY, "session_not_started"),
        (HOST, LiveSessionStatus.COMPLETED, "session_already_ended"),
        (HOST, LiveSessionStatus.CANCELLED, "session_already_ended"),
    ],
)
def test_end_session_rejections_change_nothing(
    setup: Setup, account, status, code
) -> None:
    setup.db.get(LiveSession, SESSION_ID).status = status
    setup.db.commit()

    with pytest.raises(APIError) as error:
        end_session(setup.db, account, SESSION_ID)

    assert error.value.code == code
    setup.db.expire_all()
    assert setup.db.get(SessionQuestion, Q2).status == SessionQuestionStatus.OPEN
    assert setup.db.scalars(select(Result)).all() == []


def test_end_session_unknown_session_is_404(setup: Setup) -> None:
    with pytest.raises(APIError) as error:
        end_session(setup.db, HOST, 999)
    assert error.value.status_code == 404


# close_question_now (host skip) --------------------------------------------


def test_close_question_now_uses_reason_host(setup: Setup) -> None:
    closed_at = T0 + timedelta(minutes=1, seconds=3)

    event = close_question_now(setup.db, HOST, SESSION_ID, Q2, closed_at=closed_at)

    assert event is not None
    assert event.reason == QuestionCloseReason.HOST
    assert event.closed_at == closed_at
    assert event.question_order == 2
    setup.db.expire_all()
    assert setup.db.get(SessionQuestion, Q2).status == SessionQuestionStatus.CLOSED


def test_close_question_now_after_deadline_reports_deadline(setup: Setup) -> None:
    event = close_question_now(
        setup.db, HOST, SESSION_ID, Q2, closed_at=T0 + timedelta(minutes=5)
    )
    assert event.reason == QuestionCloseReason.DEADLINE


def test_close_question_now_on_closed_question_returns_none(setup: Setup) -> None:
    """Exactly once: a skip that loses to an automatic close broadcasts nothing."""
    assert close_question_now(setup.db, HOST, SESSION_ID, Q1) is None
    first = close_question_now(setup.db, HOST, SESSION_ID, Q2)
    assert first is not None
    assert close_question_now(setup.db, HOST, SESSION_ID, Q2) is None


@pytest.mark.parametrize(
    "account, sqid, code",
    [
        (ALICE, Q2, "session_host_denied"),
        (HOST, 999, "session_question_not_found"),
    ],
)
def test_close_question_now_rejections(setup: Setup, account, sqid, code) -> None:
    with pytest.raises(APIError) as error:
        close_question_now(setup.db, account, SESSION_ID, sqid)
    assert error.value.code == code
    setup.db.expire_all()
    assert setup.db.get(SessionQuestion, Q2).status == SessionQuestionStatus.OPEN


# cancel_session --------------------------------------------------------------


def test_cancel_session_in_lobby(setup: Setup) -> None:
    setup.db.get(LiveSession, SESSION_ID).status = LiveSessionStatus.LOBBY
    setup.db.commit()

    results = cancel_session(setup.db, HOST, SESSION_ID, ended_at=T0)

    assert results.status == "CANCELLED"
    assert results.standings == []
    setup.db.expire_all()
    session = setup.db.get(LiveSession, SESSION_ID)
    assert session.status == LiveSessionStatus.CANCELLED
    assert session.ended_at == T0


@pytest.mark.parametrize(
    "account, code",
    [(HOST, "session_not_cancellable"), (ALICE, "session_host_denied")],
)
def test_cancel_session_rejections(setup: Setup, account, code) -> None:
    with pytest.raises(APIError) as error:
        cancel_session(setup.db, account, SESSION_ID)
    assert error.value.code == code
    setup.db.expire_all()
    assert setup.db.get(LiveSession, SESSION_ID).status == LiveSessionStatus.ACTIVE


# leave_session ---------------------------------------------------------------


def test_leave_session_sets_left_at_and_counts_the_rest(setup: Setup) -> None:
    left = leave_session(setup.db, BOB, SESSION_ID, left_at=T0 + timedelta(minutes=3))

    assert left.session_participant_id == PARTICIPANT_IDS["bob"]
    assert left.display_name == "Bob"
    assert left.participant_count == 2
    setup.db.expire_all()
    assert setup.db.get(SessionParticipant, PARTICIPANT_IDS["bob"]).left_at == (
        T0 + timedelta(minutes=3)
    )


def test_leave_twice_or_as_outsider_is_denied(setup: Setup) -> None:
    leave_session(setup.db, BOB, SESSION_ID)
    for account in (BOB, OUTSIDER, HOST):
        with pytest.raises(APIError) as error:
            leave_session(setup.db, account, SESSION_ID)
        assert error.value.code == "session_access_denied"


def test_leave_after_session_ended_is_rejected(setup: Setup) -> None:
    end_session(setup.db, HOST, SESSION_ID)
    with pytest.raises(APIError) as error:
        leave_session(setup.db, BOB, SESSION_ID)
    assert error.value.code == "session_already_ended"


# get_final_results -----------------------------------------------------------


def test_final_results_need_an_ended_session(setup: Setup) -> None:
    with pytest.raises(APIError) as error:
        get_final_results(setup.db, HOST, SESSION_ID)
    assert error.value.code == "results_not_ready"


def test_final_results_access_and_views(setup: Setup) -> None:
    end_session(setup.db, HOST, SESSION_ID)
    # Bob left before the end, but he played, so he can still see results.
    setup.db.get(SessionParticipant, PARTICIPANT_IDS["bob"]).left_at = T0
    setup.db.commit()

    for account in (HOST, ADMIN):
        results, viewer = get_final_results(setup.db, account, SESSION_ID)
        assert viewer is None
        assert [r.display_name for r in results.standings] == ["Alice", "Bob", "Carol"]

    results, viewer = get_final_results(setup.db, BOB, SESSION_ID)
    assert viewer == PARTICIPANT_IDS["bob"]
    view = participant_final_view(results, viewer)
    assert view.me.display_name == "Bob"
    assert view.me.final_rank == 1
    assert [entry.display_name for entry in view.leaderboard] == ["Alice", "Bob", "Carol"]
    assert not hasattr(view.leaderboard[0], "session_participant_id")

    with pytest.raises(APIError) as error:
        get_final_results(setup.db, OUTSIDER, SESSION_ID)
    assert error.value.code == "session_access_denied"


def test_participant_view_caps_leaderboard_at_five() -> None:
    from app.schemas.results import FinalResults, FinalStanding

    standings = [
        FinalStanding(
            session_participant_id=100 + i,
            display_name=f"P{i}",
            total_score=1000 - i,
            correct_count=1,
            final_rank=i + 1,
        )
        for i in range(8)
    ]
    results = FinalResults(
        session_id=1, status="COMPLETED", ended_at=T0, standings=standings
    )

    view = participant_final_view(results, 107)

    assert len(view.leaderboard) == 5
    assert view.me.display_name == "P7"
    assert view.me.final_rank == 8
