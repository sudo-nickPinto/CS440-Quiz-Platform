from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models import SubmissionStatus
from app.schemas import (
    ApprovedQuizResponse,
    QuizSubmissionCreate,
    QuizSubmissionDecision,
    QuizSubmissionResponse,
)


def test_submission_create_accepts_only_a_strict_positive_version_id() -> None:
    assert QuizSubmissionCreate(quiz_version_id=7).quiz_version_id == 7

    for payload in (
        {"quiz_version_id": 0},
        {"quiz_version_id": "7"},
        {"quiz_version_id": True},
        {"quiz_version_id": 7, "class_id": 2},
    ):
        with pytest.raises(ValidationError):
            QuizSubmissionCreate.model_validate(payload)


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED"])
def test_submission_decision_accepts_only_decision_statuses(status: str) -> None:
    decision = QuizSubmissionDecision.model_validate({"status": status})

    assert decision.status.value == status


@pytest.mark.parametrize("status", ["PENDING", "WITHDRAWN", "ARCHIVED"])
def test_submission_decision_rejects_other_statuses(status: str) -> None:
    with pytest.raises(ValidationError):
        QuizSubmissionDecision.model_validate({"status": status})


def test_submission_decision_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        QuizSubmissionDecision.model_validate(
            {"status": "APPROVED", "decided_by_id": 4}
        )


def test_submission_response_has_only_the_eight_public_task_fields() -> None:
    now = datetime(2026, 11, 3, 20, 0, 0)
    response = QuizSubmissionResponse.model_validate(
        SimpleNamespace(
            submission_id=1,
            class_id=2,
            quiz_version_id=3,
            submitted_by_id=4,
            status=SubmissionStatus.PENDING,
            decided_by_id=None,
            submitted_at=now,
            decided_at=None,
            _active_version_id=3,
        )
    )

    assert response.model_dump() == {
        "submission_id": 1,
        "class_id": 2,
        "quiz_version_id": 3,
        "submitted_by_id": 4,
        "status": SubmissionStatus.PENDING,
        "decided_by_id": None,
        "submitted_at": now,
        "decided_at": None,
    }

    with pytest.raises(ValidationError):
        QuizSubmissionResponse.model_validate(
            {**response.model_dump(), "active_version_id": 3}
        )


def test_approved_quiz_response_contract() -> None:
    approved_at = datetime(2026, 11, 3, 20, 0, 0)
    response = ApprovedQuizResponse(
        submission_id=1,
        quiz_id=2,
        quiz_version_id=3,
        version_number=4,
        title="Concurrency",
        author_id=5,
        approved_at=approved_at,
        approved_by_id=6,
    )

    assert list(response.model_dump()) == [
        "submission_id",
        "quiz_id",
        "quiz_version_id",
        "version_number",
        "title",
        "author_id",
        "approved_at",
        "approved_by_id",
    ]
