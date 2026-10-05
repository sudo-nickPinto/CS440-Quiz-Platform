import pytest
from pydantic import ValidationError

from app.schemas.quiz import QuizCreate


def test_quiz_create_trims_title_and_supplies_safe_defaults() -> None:
    payload = QuizCreate(title="  Quiz title  ")

    assert payload.title == "Quiz title"
    assert payload.visibility.value == "PRIVATE"


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "   "},
        {"title": "Valid", "author_id": 123},
        {"title": "Valid", "visibility": "EVERYONE"},
    ],
)
def test_quiz_create_rejects_invalid_or_server_owned_fields(payload: dict) -> None:
    with pytest.raises(ValidationError):
        QuizCreate.model_validate(payload)
