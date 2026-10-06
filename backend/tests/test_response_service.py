from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    AccountRole,
    AnswerChoice,
    LiveSession,
    LiveSessionStatus,
    Question,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.schemas.response import ResponseSubmit
from app.services.responses import _evaluate_response, submit_response


OPENED_AT = datetime(2026, 10, 4, 12, 0, 0)


def played_question(
    *,
    session_status: LiveSessionStatus = LiveSessionStatus.ACTIVE,
    question_status: SessionQuestionStatus = SessionQuestionStatus.OPEN,
) -> SessionQuestion:
    return SessionQuestion(
        session_question_id=10,
        session_id=20,
        question_id=30,
        status=question_status,
        opened_at=OPENED_AT,
        closes_at=OPENED_AT + timedelta(seconds=30),
        session=LiveSession(session_id=20, status=session_status),
        question=Question(
            question_id=30,
            time_limit_seconds=30,
            base_points=1000,
        ),
    )


def answer_choice(*, is_correct: bool, question_id: int = 30) -> AnswerChoice:
    return AnswerChoice(
        choice_id=40,
        question_id=question_id,
        is_correct=is_correct,
    )


def test_correct_response_is_timed_and_scored_by_the_server() -> None:
    result = _evaluate_response(
        played_question(),
        answer_choice(is_correct=True),
        OPENED_AT + timedelta(seconds=2),
    )

    assert result == (2_000, True, 967)


def test_incorrect_response_records_correctness_but_awards_zero() -> None:
    result = _evaluate_response(
        played_question(),
        answer_choice(is_correct=False),
        OPENED_AT + timedelta(seconds=2),
    )

    assert result == (2_000, False, 0)


def test_response_after_server_deadline_is_rejected() -> None:
    with pytest.raises(APIError) as caught:
        _evaluate_response(
            played_question(),
            answer_choice(is_correct=True),
            OPENED_AT + timedelta(seconds=30, milliseconds=1),
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "response_deadline_passed"


def test_response_to_closed_question_is_rejected() -> None:
    with pytest.raises(APIError) as caught:
        _evaluate_response(
            played_question(question_status=SessionQuestionStatus.CLOSED),
            answer_choice(is_correct=True),
            OPENED_AT + timedelta(seconds=2),
        )

    assert caught.value.status_code == 409
    assert caught.value.code == "question_not_open"


def test_choice_from_another_question_is_rejected() -> None:
    with pytest.raises(APIError) as caught:
        _evaluate_response(
            played_question(),
            answer_choice(is_correct=True, question_id=999),
            OPENED_AT + timedelta(seconds=2),
        )

    assert caught.value.status_code == 422
    assert caught.value.code == "choice_not_for_question"


class DuplicateRaceSession:
    """Small database double that reproduces a simultaneous second insert."""

    def __init__(self) -> None:
        self.results = iter(
            [
                SessionParticipant(
                    session_participant_id=60,
                    session_id=20,
                    account_id=7,
                ),
                played_question(),
                None,
                answer_choice(is_correct=True),
                99,
            ]
        )
        self.rolled_back = False

    def scalar(self, _statement):
        return next(self.results)

    def add(self, _response) -> None:
        return None

    def commit(self) -> None:
        raise IntegrityError("INSERT INTO response", {}, Exception("duplicate"))

    def rollback(self) -> None:
        self.rolled_back = True


def test_simultaneous_second_insert_becomes_first_response_error() -> None:
    database = DuplicateRaceSession()

    with pytest.raises(APIError) as caught:
        submit_response(
            database,
            CurrentAccount(7, AccountRole.USER, True),
            20,
            10,
            ResponseSubmit(choice_id=40),
            submitted_at=OPENED_AT + timedelta(seconds=2),
        )

    assert database.rolled_back is True
    assert caught.value.status_code == 409
    assert caught.value.code == "response_already_submitted"
