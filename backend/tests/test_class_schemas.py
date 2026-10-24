import pytest
from pydantic import ValidationError

from app.schemas.classes import ClassCreate, ClassUpdate


@pytest.mark.parametrize(
    ("raw_name", "expected_name"),
    [
        ("CS 440", "CS 440"),
        ("  Operating Systems  ", "Operating Systems"),
        ("x" * 100, "x" * 100),
    ],
)
def test_class_create_accepts_and_normalizes_valid_names(
    raw_name: str,
    expected_name: str,
) -> None:
    assert ClassCreate(name=raw_name).name == expected_name


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_class_create_rejects_invalid_names(name: str) -> None:
    with pytest.raises(ValidationError):
        ClassCreate(name=name)


def test_class_create_forbids_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        ClassCreate.model_validate({"name": "CS 440", "owner_id": 7})


def test_class_update_accepts_only_supplied_valid_fields() -> None:
    update = ClassUpdate(name="  Historical Name  ")
    close_joining = ClassUpdate(joining_open=False)

    assert update.name == "Historical Name"
    assert update.model_fields_set == {"name"}
    assert close_joining.joining_open is False
    assert close_joining.model_fields_set == {"joining_open"}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 101},
        {"name": None},
        {"joining_open": None},
        {"unexpected": True},
    ],
)
def test_class_update_rejects_invalid_or_empty_payloads(payload: dict) -> None:
    with pytest.raises(ValidationError):
        ClassUpdate.model_validate(payload)
