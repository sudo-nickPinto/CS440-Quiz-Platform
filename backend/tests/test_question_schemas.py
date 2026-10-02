import pytest
from pydantic import ValidationError

from app.schemas.quiz import QuestionOrderUpdate, QuestionWrite


def valid_question() -> dict:
    return {
        "question_text": "  What is 2 + 2?  ",
        "choices": [
            {"choice_text": "  Four  ", "is_correct": True},
            {"choice_text": "Five", "is_correct": False},
        ],
    }


def test_question_write_trims_text_and_uses_multiple_choice_defaults() -> None:
    question = QuestionWrite.model_validate(valid_question())

    assert question.question_text == "What is 2 + 2?"
    assert question.choices[0].choice_text == "Four"
    assert question.time_limit_seconds == 20
    assert question.base_points == 1000


@pytest.mark.parametrize(
    "change",
    [
        {"question_text": "   "},
        {"choices": [{"choice_text": "Only", "is_correct": True}]},
        {
            "choices": [
                {"choice_text": "A"},
                {"choice_text": "B", "is_correct": False},
            ]
        },
        {"question_type": "FILL_IN_BLANK"},
        {"time_limit_seconds": 0},
        {"base_points": 0},
    ],
)
def test_question_write_rejects_invalid_multiple_choice_data(change: dict) -> None:
    payload = valid_question()
    payload.update(change)

    with pytest.raises(ValidationError):
        QuestionWrite.model_validate(payload)


@pytest.mark.parametrize("question_ids", [[1, 1], [0, 1], []])
def test_question_order_requires_unique_positive_ids(question_ids: list[int]) -> None:
    with pytest.raises(ValidationError):
        QuestionOrderUpdate(question_ids=question_ids)
