import pytest
from pydantic import ValidationError

from app.schemas.quiz import QuizCreate


def valid_quiz() -> dict:
    return {
        "title": "  Intro Quiz  ",
        "description": "  Week one  ",
        "questions": [
            {
                "question_text": "  What is 2 + 2?  ",
                "choices": [
                    {"choice_text": " 4 ", "is_correct": True},
                    {"choice_text": " 5 ", "is_correct": False},
                ],
            }
        ],
    }


def test_quiz_payload_normalizes_text() -> None:
    payload = QuizCreate.model_validate(valid_quiz())

    assert payload.title == "Intro Quiz"
    assert payload.description == "Week one"
    assert payload.questions[0].question_text == "What is 2 + 2?"
    assert payload.questions[0].choices[0].choice_text == "4"


@pytest.mark.parametrize(
    "change",
    [
        {"title": "   "},
        {"questions": []},
        {
            "questions": [
                {
                    "question_text": "Question",
                    "choices": [
                        {"choice_text": "A", "is_correct": False},
                        {"choice_text": "B", "is_correct": False},
                    ],
                }
            ]
        },
    ],
    ids=["blank-title", "no-questions", "no-correct-choice"],
)
def test_quiz_payload_rejects_incomplete_quizzes(change: dict) -> None:
    data = valid_quiz()
    data.update(change)

    with pytest.raises(ValidationError):
        QuizCreate.model_validate(data)


def test_quiz_payload_rejects_deferred_visibility_field() -> None:
    data = valid_quiz()
    data["visibility"] = "PRIVATE"

    with pytest.raises(ValidationError):
        QuizCreate.model_validate(data)
