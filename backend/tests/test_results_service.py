from collections.abc import Iterator

import pytest
from sqlalchemy.orm import Session

from app.database import Base, Database
from app.errors import APIError
from app.models import (
    Account,
    AnswerChoice,
    LiveSession,
    LiveSessionStatus,
    Question,
    Response,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.services.results import (
    get_closed_question_result_data,
    get_closed_question_results,
)


SESSION_ID = 20
SESSION_QUESTION_ID = 10
QUESTION_ID = 30
PREVIOUS_SESSION_QUESTION_ID = 9
OPEN_SESSION_QUESTION_ID = 11


@pytest.fixture
def results_db() -> Iterator[Session]:
    database = Database("sqlite://")
    Base.metadata.create_all(database.engine)
    with database.session_factory() as db:
        db.add_all(
            [
                *[
                    Account(
                        account_id=account_id,
                        auth0_sub=f"test|results-{account_id}",
                        email=f"results-{account_id}@test.invalid",
                        display_name=display_name,
                    )
                    for account_id, display_name in [
                        (2, "Zoe"),
                        (3, "Alice"),
                        (4, "Charlie"),
                        (5, "Bob"),
                        (6, "Dana"),
                        (7, "Eve"),
                    ]
                ],
                Question(
                    question_id=QUESTION_ID,
                    quiz_version_id=100,
                    question_order=1,
                    question_text="Choose every correct answer.",
                    time_limit_seconds=30,
                    base_points=1000,
                ),
                AnswerChoice(
                    choice_id=31,
                    question_id=QUESTION_ID,
                    choice_order=1,
                    choice_text="First",
                    is_correct=True,
                ),
                Question(
                    question_id=29,
                    quiz_version_id=100,
                    question_order=2,
                    question_text="Previous question",
                    time_limit_seconds=30,
                    base_points=1000,
                ),
                AnswerChoice(
                    choice_id=29,
                    question_id=29,
                    choice_order=1,
                    choice_text="Previous answer",
                    is_correct=True,
                ),
                Question(
                    question_id=34,
                    quiz_version_id=100,
                    question_order=3,
                    question_text="Open question",
                    time_limit_seconds=30,
                    base_points=1000,
                ),
                AnswerChoice(
                    choice_id=34,
                    question_id=34,
                    choice_order=1,
                    choice_text="Open answer",
                    is_correct=True,
                ),
                AnswerChoice(
                    choice_id=32,
                    question_id=QUESTION_ID,
                    choice_order=2,
                    choice_text="Second",
                    is_correct=False,
                ),
                AnswerChoice(
                    choice_id=33,
                    question_id=QUESTION_ID,
                    choice_order=3,
                    choice_text="Third",
                    is_correct=True,
                ),
                LiveSession(
                    session_id=SESSION_ID,
                    quiz_version_id=100,
                    host_id=1,
                    join_code="123456",
                    status=LiveSessionStatus.ACTIVE,
                ),
                SessionQuestion(
                    session_question_id=SESSION_QUESTION_ID,
                    session_id=SESSION_ID,
                    question_id=QUESTION_ID,
                    status=SessionQuestionStatus.CLOSED,
                ),
                SessionQuestion(
                    session_question_id=PREVIOUS_SESSION_QUESTION_ID,
                    session_id=SESSION_ID,
                    question_id=29,
                    status=SessionQuestionStatus.CLOSED,
                ),
                SessionQuestion(
                    session_question_id=OPEN_SESSION_QUESTION_ID,
                    session_id=SESSION_ID,
                    question_id=34,
                    status=SessionQuestionStatus.OPEN,
                ),
                SessionParticipant(
                    session_participant_id=41,
                    session_id=SESSION_ID,
                    account_id=2,
                ),
                SessionParticipant(
                    session_participant_id=42,
                    session_id=SESSION_ID,
                    account_id=3,
                ),
                SessionParticipant(
                    session_participant_id=43,
                    session_id=SESSION_ID,
                    account_id=4,
                ),
                SessionParticipant(
                    session_participant_id=44,
                    session_id=SESSION_ID,
                    account_id=5,
                ),
                SessionParticipant(
                    session_participant_id=45,
                    session_id=SESSION_ID,
                    account_id=6,
                ),
                SessionParticipant(
                    session_participant_id=46,
                    session_id=SESSION_ID,
                    account_id=7,
                ),
                Response(
                    response_id=51,
                    session_participant_id=41,
                    session_question_id=SESSION_QUESTION_ID,
                    choice_id=31,
                    response_time_ms=1000,
                    is_correct=True,
                    points_awarded=900,
                ),
                Response(
                    response_id=52,
                    session_participant_id=42,
                    session_question_id=SESSION_QUESTION_ID,
                    choice_id=31,
                    response_time_ms=2000,
                    is_correct=True,
                    points_awarded=700,
                ),
                Response(
                    response_id=53,
                    session_participant_id=43,
                    session_question_id=SESSION_QUESTION_ID,
                    choice_id=32,
                    response_time_ms=3000,
                    is_correct=False,
                    points_awarded=0,
                ),
                Response(
                    response_id=54,
                    session_participant_id=41,
                    session_question_id=PREVIOUS_SESSION_QUESTION_ID,
                    choice_id=29,
                    response_time_ms=1000,
                    is_correct=True,
                    points_awarded=300,
                ),
                Response(
                    response_id=55,
                    session_participant_id=42,
                    session_question_id=PREVIOUS_SESSION_QUESTION_ID,
                    choice_id=29,
                    response_time_ms=1000,
                    is_correct=True,
                    points_awarded=300,
                ),
                Response(
                    response_id=56,
                    session_participant_id=43,
                    session_question_id=PREVIOUS_SESSION_QUESTION_ID,
                    choice_id=29,
                    response_time_ms=1000,
                    is_correct=True,
                    points_awarded=500,
                ),
                Response(
                    response_id=57,
                    session_participant_id=44,
                    session_question_id=PREVIOUS_SESSION_QUESTION_ID,
                    choice_id=29,
                    response_time_ms=1000,
                    is_correct=True,
                    points_awarded=500,
                ),
                Response(
                    response_id=58,
                    session_participant_id=45,
                    session_question_id=PREVIOUS_SESSION_QUESTION_ID,
                    choice_id=29,
                    response_time_ms=1000,
                    is_correct=True,
                    points_awarded=100,
                ),
                Response(
                    response_id=59,
                    session_participant_id=45,
                    session_question_id=OPEN_SESSION_QUESTION_ID,
                    choice_id=34,
                    response_time_ms=1000,
                    is_correct=True,
                    points_awarded=5000,
                ),
            ]
        )
        db.commit()
        yield db
    database.dispose()


def test_closed_question_returns_complete_answer_distribution(
    results_db: Session,
) -> None:
    result = get_closed_question_result_data(
        results_db,
        SESSION_ID,
        SESSION_QUESTION_ID,
    )

    assert result.session_id == SESSION_ID
    assert result.session_question_id == SESSION_QUESTION_ID
    assert result.correct_choice_ids == [31, 33]
    assert [choice.model_dump() for choice in result.choices] == [
        {"choice_id": 31, "response_count": 2, "is_correct": True},
        {"choice_id": 32, "response_count": 1, "is_correct": False},
        {"choice_id": 33, "response_count": 0, "is_correct": True},
    ]


def test_closed_question_uses_stored_correctness_and_points(
    results_db: Session,
) -> None:
    result = get_closed_question_result_data(
        results_db,
        SESSION_ID,
        SESSION_QUESTION_ID,
    )

    assert [
        (response.is_correct, response.points_awarded)
        for response in result.responses
    ] == [(True, 900), (True, 700), (False, 0)]


def test_leaderboard_includes_every_participant_and_rank_style_ties(
    results_db: Session,
) -> None:
    result = get_closed_question_results(
        results_db,
        SESSION_ID,
        SESSION_QUESTION_ID,
    )

    assert [
        (
            participant.display_name,
            participant.selected_choice_id,
            participant.is_correct,
            participant.points_awarded,
            participant.cumulative_score,
            participant.rank,
        )
        for participant in result.participants
    ] == [
        ("Zoe", 31, True, 900, 1200, 1),
        ("Alice", 31, True, 700, 1000, 2),
        ("Bob", None, False, 0, 500, 3),
        ("Charlie", 32, False, 0, 500, 3),
        ("Dana", None, False, 0, 100, 5),
        ("Eve", None, False, 0, 0, 6),
    ]


def test_question_from_another_session_is_not_returned(results_db: Session) -> None:
    with pytest.raises(APIError) as caught:
        get_closed_question_result_data(
            results_db,
            session_id=999,
            session_question_id=SESSION_QUESTION_ID,
        )

    assert caught.value.status_code == 404
    assert caught.value.code == "session_question_not_found"


def test_missing_session_question_is_not_returned(results_db: Session) -> None:
    with pytest.raises(APIError) as caught:
        get_closed_question_result_data(
            results_db,
            SESSION_ID,
            session_question_id=999,
        )

    assert caught.value.status_code == 404
    assert caught.value.code == "session_question_not_found"


@pytest.mark.parametrize(
    "status",
    [SessionQuestionStatus.PENDING, SessionQuestionStatus.OPEN],
)
def test_results_are_hidden_until_question_is_closed(
    results_db: Session,
    status: SessionQuestionStatus,
) -> None:
    session_question = results_db.get(SessionQuestion, SESSION_QUESTION_ID)
    assert session_question is not None
    session_question.status = status
    results_db.commit()

    with pytest.raises(APIError) as caught:
        get_closed_question_result_data(
            results_db,
            SESSION_ID,
            SESSION_QUESTION_ID,
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "question_results_unavailable"
