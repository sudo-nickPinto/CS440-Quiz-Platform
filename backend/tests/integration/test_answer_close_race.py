"""An answer in flight vs. the host's skip / end, on real MySQL.

Each test holds submit_response() open mid-transaction (after it has read the
question, before it commits) and fires the host command at it from another
connection. Whichever commits first, the stored responses and what the host
command reported must agree: no answer may land after it was counted.
"""

import threading
import time
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import Response, Result, SessionParticipant
from app.schemas.response import ResponseSubmit
from app.services import responses
from app.services.live_questions import close_question_now
from app.services.session_end import end_session
from tests.integration.test_response_submission import (  # noqa: F401
    ResponseContext,
    response_context,
)

HOLD_SECONDS = 0.5


@pytest.fixture
def host(
    mysql_quiz_client: tuple[TestClient, CurrentAccount, CurrentAccount],
) -> CurrentAccount:
    return mysql_quiz_client[1]


def _answer_held_open(context: ResponseContext, monkeypatch) -> tuple:
    """Start an answer in a thread that pauses after validating the question.

    Returns the thread and a dict that gets its receipt or error code.
    """
    validated = threading.Event()
    evaluate = responses._evaluate_response

    def slow_evaluate(*args):
        result = evaluate(*args)
        validated.set()
        time.sleep(HOLD_SECONDS)  # the race window: validated, not committed
        return result

    monkeypatch.setattr(responses, "_evaluate_response", slow_evaluate)
    outcome: dict = {}
    scenario = context.scenario

    def answer() -> None:
        with Session(context.client.app.state.database.engine) as db:
            try:
                outcome["receipt"] = responses.submit_response(
                    db,
                    context.participant,
                    scenario.session_id,
                    scenario.session_question_id,
                    ResponseSubmit(choice_id=scenario.correct_choice_id),
                )
            except APIError as exc:
                outcome["error"] = exc.code

    thread = threading.Thread(target=answer)
    thread.start()
    assert validated.wait(5), "the answer never reached validation"
    return thread, outcome


def _stored_points(context: ResponseContext) -> int:
    context.db.expire_all()
    return int(
        context.db.scalar(
            select(func.coalesce(func.sum(Response.points_awarded), 0)).where(
                Response.session_question_id == context.scenario.session_question_id
            )
        )
    )


def test_end_session_counts_an_answer_that_was_mid_commit(
    response_context: ResponseContext, host: CurrentAccount, monkeypatch
) -> None:
    thread, outcome = _answer_held_open(response_context, monkeypatch)
    with Session(response_context.client.app.state.database.engine) as db:
        ended = end_session(db, host, response_context.scenario.session_id)
    thread.join(5)

    assert "receipt" in outcome, outcome  # the answer was on time: it counts
    points = _stored_points(response_context)
    assert points > 0
    [standing] = ended.results.standings
    assert standing.total_score == points
    assert standing.correct_count == 1
    response_context.db.expire_all()
    stored = response_context.db.scalar(
        select(Result.total_score).where(
            Result.session_participant_id
            == response_context.scenario.participant_id
        )
    )
    assert stored == points


def test_skip_counts_an_answer_that_was_mid_commit(
    response_context: ResponseContext, host: CurrentAccount, monkeypatch
) -> None:
    scenario = response_context.scenario
    # The fixture joins the participant after the question opened; backdate
    # the join so they count toward answered/eligible.
    response_context.db.execute(
        update(SessionParticipant)
        .where(SessionParticipant.session_participant_id == scenario.participant_id)
        .values(joined_at=datetime(2000, 1, 1))
    )
    response_context.db.commit()

    thread, outcome = _answer_held_open(response_context, monkeypatch)
    with Session(response_context.client.app.state.database.engine) as db:
        closed = close_question_now(
            db, host, scenario.session_id, scenario.session_question_id
        )
    thread.join(5)

    assert "receipt" in outcome, outcome
    assert closed is not None
    assert closed.answered_count == 1
    assert closed.eligible_count == 1


def test_answer_after_end_is_rejected_not_stored(
    response_context: ResponseContext, host: CurrentAccount
) -> None:
    scenario = response_context.scenario
    with Session(response_context.client.app.state.database.engine) as db:
        end_session(db, host, scenario.session_id)

    with Session(response_context.client.app.state.database.engine) as db:
        with pytest.raises(APIError) as caught:
            responses.submit_response(
                db,
                response_context.participant,
                scenario.session_id,
                scenario.session_question_id,
                ResponseSubmit(choice_id=scenario.correct_choice_id),
            )
    assert caught.value.code in {"session_not_active", "question_not_open"}
    assert _stored_points(response_context) == 0
