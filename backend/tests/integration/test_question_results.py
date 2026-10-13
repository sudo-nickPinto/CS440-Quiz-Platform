from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    Account,
    AnswerChoice,
    LiveSession,
    LiveSessionStatus,
    Question,
    Quiz,
    QuizStatus,
    QuizVersion,
    QuizVisibility,
    Response,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.services.results import get_closed_question_results


@dataclass
class QuestionResultsContext:
    db: Session
    session_id: int
    session_question_id: int
    correct_choice_id: int
    incorrect_choice_id: int
    zero_count_choice_id: int


@pytest.fixture
def question_results_context(
    mysql_quiz_client: tuple[TestClient, CurrentAccount, CurrentAccount],
) -> Iterator[QuestionResultsContext]:
    client, host_account, _ = mysql_quiz_client
    db = Session(client.app.state.database.engine)
    unique = uuid4().hex
    accounts = [
        Account(
            auth0_sub=f"test|question-results-{unique}-{index}",
            email=f"question-results-{unique}-{index}@test.invalid",
            display_name=display_name,
        )
        for index, display_name in enumerate(
            ["Zoe", "Alice", "Charlie", "Bob", "Dana", "Eve"],
            start=1,
        )
    ]
    db.add_all(accounts)
    db.flush()

    previous_choice = AnswerChoice(
        choice_order=1,
        choice_text="Previous answer",
        is_correct=True,
    )
    previous_question = Question(
        question_order=1,
        question_text="Previous question",
        time_limit_seconds=30,
        base_points=1000,
        choices=[previous_choice],
    )
    correct_choice = AnswerChoice(
        choice_order=1,
        choice_text="Correct",
        is_correct=True,
    )
    incorrect_choice = AnswerChoice(
        choice_order=2,
        choice_text="Incorrect",
        is_correct=False,
    )
    zero_count_choice = AnswerChoice(
        choice_order=3,
        choice_text="Also correct",
        is_correct=True,
    )
    current_question = Question(
        question_order=2,
        question_text="Current question",
        time_limit_seconds=30,
        base_points=1000,
        choices=[correct_choice, incorrect_choice, zero_count_choice],
    )
    open_choice = AnswerChoice(
        choice_order=1,
        choice_text="Open answer",
        is_correct=True,
    )
    open_question = Question(
        question_order=3,
        question_text="Still-open question",
        time_limit_seconds=30,
        base_points=1000,
        choices=[open_choice],
    )
    version = QuizVersion(
        version_number=1,
        title="Question results integration test",
        published_at=datetime.now(UTC).replace(tzinfo=None),
        questions=[previous_question, current_question, open_question],
    )
    quiz = Quiz(
        author_id=host_account.account_id,
        status=QuizStatus.PUBLISHED,
        visibility=QuizVisibility.PUBLIC,
        versions=[version],
    )
    db.add(quiz)
    db.flush()

    live_session = LiveSession(
        quiz_version_id=version.quiz_version_id,
        host_id=host_account.account_id,
        group_id=None,
        join_code=unique[:6].upper(),
        status=LiveSessionStatus.ACTIVE,
        current_question_order=2,
    )
    participants = [
        SessionParticipant(session=live_session, account_id=account.account_id)
        for account in accounts
    ]
    previous_session_question = SessionQuestion(
        session=live_session,
        question=previous_question,
        status=SessionQuestionStatus.CLOSED,
    )
    current_session_question = SessionQuestion(
        session=live_session,
        question=current_question,
        status=SessionQuestionStatus.OPEN,
    )
    open_session_question = SessionQuestion(
        session=live_session,
        question=open_question,
        status=SessionQuestionStatus.OPEN,
    )
    db.add_all(
        [
            live_session,
            *participants,
            previous_session_question,
            current_session_question,
            open_session_question,
        ]
    )
    db.flush()

    previous_points = [300, 300, 500, 500, 100]
    responses = [
        Response(
            session_participant_id=participant.session_participant_id,
            session_question_id=previous_session_question.session_question_id,
            choice_id=previous_choice.choice_id,
            response_time_ms=1000,
            is_correct=True,
            points_awarded=points,
        )
        for participant, points in zip(
            participants[:5], previous_points, strict=True
        )
    ]
    responses.extend(
        [
            Response(
                session_participant_id=participants[0].session_participant_id,
                session_question_id=current_session_question.session_question_id,
                choice_id=correct_choice.choice_id,
                response_time_ms=1000,
                is_correct=True,
                points_awarded=900,
            ),
            Response(
                session_participant_id=participants[1].session_participant_id,
                session_question_id=current_session_question.session_question_id,
                choice_id=correct_choice.choice_id,
                response_time_ms=2000,
                is_correct=True,
                points_awarded=700,
            ),
            Response(
                session_participant_id=participants[2].session_participant_id,
                session_question_id=current_session_question.session_question_id,
                choice_id=incorrect_choice.choice_id,
                response_time_ms=3000,
                is_correct=False,
                points_awarded=0,
            ),
            Response(
                session_participant_id=participants[4].session_participant_id,
                session_question_id=open_session_question.session_question_id,
                choice_id=open_choice.choice_id,
                response_time_ms=1000,
                is_correct=True,
                points_awarded=5000,
            ),
        ]
    )
    db.add_all(responses)
    db.commit()

    try:
        yield QuestionResultsContext(
            db=db,
            session_id=live_session.session_id,
            session_question_id=current_session_question.session_question_id,
            correct_choice_id=correct_choice.choice_id,
            incorrect_choice_id=incorrect_choice.choice_id,
            zero_count_choice_id=zero_count_choice.choice_id,
        )
    finally:
        db.close()


def test_open_question_keeps_results_hidden(
    question_results_context: QuestionResultsContext,
) -> None:
    context = question_results_context

    with pytest.raises(APIError) as caught:
        get_closed_question_results(
            context.db,
            context.session_id,
            context.session_question_id,
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "question_results_unavailable"


def test_closed_question_reveals_distribution_and_cumulative_leaderboard(
    question_results_context: QuestionResultsContext,
) -> None:
    context = question_results_context
    session_question = context.db.get(SessionQuestion, context.session_question_id)
    assert session_question is not None
    session_question.status = SessionQuestionStatus.CLOSED
    context.db.commit()

    result = get_closed_question_results(
        context.db,
        context.session_id,
        context.session_question_id,
    )

    assert result.correct_choice_ids == [
        context.correct_choice_id,
        context.zero_count_choice_id,
    ]
    assert [choice.model_dump() for choice in result.choices] == [
        {
            "choice_id": context.correct_choice_id,
            "response_count": 2,
            "is_correct": True,
        },
        {
            "choice_id": context.incorrect_choice_id,
            "response_count": 1,
            "is_correct": False,
        },
        {
            "choice_id": context.zero_count_choice_id,
            "response_count": 0,
            "is_correct": True,
        },
    ]
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
        ("Zoe", context.correct_choice_id, True, 900, 1200, 1),
        ("Alice", context.correct_choice_id, True, 700, 1000, 2),
        ("Bob", None, False, 0, 500, 3),
        ("Charlie", context.incorrect_choice_id, False, 0, 500, 3),
        ("Dana", None, False, 0, 100, 5),
        ("Eve", None, False, 0, 0, 6),
    ]
