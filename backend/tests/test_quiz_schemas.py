import pytest
from pydantic import ValidationError

from app.schemas.quiz import QuizCreate, QuizUpdate


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


def test_quiz_update_tracks_only_supplied_fields() -> None:
    payload = QuizUpdate(description=None)

    assert payload.model_fields_set == {"description"}
    assert payload.description is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"title": None},
        {"title": "   "},
        {"visibility": None},
        {"status": "PUBLISHED"},
    ],
)
def test_quiz_update_rejects_empty_invalid_or_server_owned_fields(
    payload: dict,
) -> None:
    with pytest.raises(ValidationError):
        QuizUpdate.model_validate(payload)
