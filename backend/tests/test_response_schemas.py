import pytest
from pydantic import ValidationError

from app.schemas.response import ResponseReceipt, ResponseSubmit


def test_response_submission_accepts_one_positive_choice_id() -> None:
    payload = ResponseSubmit(choice_id=17)

    assert payload.choice_id == 17


@pytest.mark.parametrize("choice_id", [0, -1])
def test_response_submission_rejects_nonpositive_choice_ids(choice_id: int) -> None:
    with pytest.raises(ValidationError):
        ResponseSubmit(choice_id=choice_id)


def test_response_submission_rejects_client_calculated_score_fields() -> None:
    with pytest.raises(ValidationError):
        ResponseSubmit(choice_id=17, is_correct=True, points_awarded=1000)


def test_response_receipt_does_not_reveal_score_fields() -> None:
    receipt = ResponseReceipt(
        response_id=1,
        session_question_id=2,
        choice_id=3,
        submitted_at="2026-10-05T12:00:00",
    )

    assert set(receipt.model_dump()) == {
        "response_id",
        "session_question_id",
        "choice_id",
        "submitted_at",
    }
