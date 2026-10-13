from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.live_question import (
    QuestionClosedEvent,
    QuestionCloseReason,
    QuestionOpenedEvent,
)


def opened_event() -> dict:
    return {
        "type": "question_opened",
        "session_id": 10,
        "session_question_id": 20,
        "question_order": 2,
        "total_questions": 5,
        "question_text": "Which protocol secures web traffic?",
        "choices": [
            {"choice_id": 31, "choice_order": 1, "choice_text": "HTTPS"},
            {"choice_id": 32, "choice_order": 2, "choice_text": "FTP"},
        ],
        "opened_at": "2026-10-12T18:00:00Z",
        "closes_at": "2026-10-12T18:00:30Z",
    }


def closed_event() -> dict:
    return {
        "type": "question_closed",
        "session_id": 10,
        "session_question_id": 20,
        "question_order": 2,
        "reason": "ALL_ANSWERED",
        "answered_count": 3,
        "eligible_count": 3,
        "opened_at": "2026-10-12T18:00:00Z",
        "closes_at": "2026-10-12T18:00:30Z",
        "closed_at": "2026-10-12T18:00:12Z",
    }


def test_opened_event_serializes_without_correctness() -> None:
    event = QuestionOpenedEvent.model_validate(opened_event())

    assert event.model_dump(mode="json") == opened_event()
    assert "is_correct" not in event.model_dump(mode="json")["choices"][0]


def test_closed_event_serializes_with_reason_and_counts() -> None:
    event = QuestionClosedEvent.model_validate(closed_event())

    assert event.reason is QuestionCloseReason.ALL_ANSWERED
    assert event.model_dump(mode="json") == closed_event()


@pytest.mark.parametrize(
    ("payload_factory", "event_model", "wrong_type"),
    [
        (opened_event, QuestionOpenedEvent, "question_closed"),
        (closed_event, QuestionClosedEvent, "question_opened"),
    ],
)
def test_event_types_are_fixed(payload_factory, event_model, wrong_type: str) -> None:
    payload = payload_factory()
    payload["type"] = wrong_type

    with pytest.raises(ValidationError):
        event_model.model_validate(payload)


@pytest.mark.parametrize(
    ("payload_factory", "extra_field"),
    [
        (opened_event, {"host_id": 99}),
        (closed_event, {"response_count": 3}),
    ],
)
def test_events_reject_extra_fields(payload_factory, extra_field: dict) -> None:
    payload = payload_factory()
    payload.update(extra_field)

    with pytest.raises(ValidationError):
        if payload["type"] == "question_opened":
            QuestionOpenedEvent.model_validate(payload)
        else:
            QuestionClosedEvent.model_validate(payload)


def test_opened_event_rejects_choice_correctness() -> None:
    payload = opened_event()
    payload["choices"][0]["is_correct"] = True

    with pytest.raises(ValidationError):
        QuestionOpenedEvent.model_validate(payload)


@pytest.mark.parametrize(
    ("payload_factory", "changes"),
    [
        (opened_event, {"closes_at": "2026-10-12T18:00:00Z"}),
        (opened_event, {"closes_at": "2026-10-12T17:59:59Z"}),
        (closed_event, {"closes_at": "2026-10-12T18:00:00Z"}),
        (closed_event, {"closed_at": "2026-10-12T17:59:59Z"}),
    ],
    ids=[
        "opened-equal-deadline",
        "opened-deadline-before-opening",
        "closed-equal-deadline",
        "closed-before-opening",
    ],
)
def test_events_reject_invalid_timestamps(payload_factory, changes: dict) -> None:
    payload = payload_factory()
    payload.update(changes)

    with pytest.raises(ValidationError):
        if payload["type"] == "question_opened":
            QuestionOpenedEvent.model_validate(payload)
        else:
            QuestionClosedEvent.model_validate(payload)


@pytest.mark.parametrize(
    "changes",
    [
        {"answered_count": -1},
        {"eligible_count": -1},
        {"answered_count": 4, "eligible_count": 3},
    ],
)
def test_closed_event_rejects_invalid_counts(changes: dict) -> None:
    payload = closed_event()
    payload.update(changes)

    with pytest.raises(ValidationError):
        QuestionClosedEvent.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("session_id",), 0),
        (("session_question_id",), 0),
        (("question_order",), 0),
        (("total_questions",), 0),
        (("choices", 0, "choice_id"), 0),
        (("choices", 0, "choice_order"), 0),
    ],
)
def test_opened_event_rejects_nonpositive_ids_and_orders(
    path: tuple[str | int, ...],
    value: int,
) -> None:
    payload = deepcopy(opened_event())
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        QuestionOpenedEvent.model_validate(payload)
