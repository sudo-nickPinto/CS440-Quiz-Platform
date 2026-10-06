import pytest

from app.services.scoring import calculate_points


def score(
    response_time_ms: int,
    *,
    is_correct: bool = True,
    time_limit_seconds: int = 30,
    max_points: int = 1000,
) -> int:
    return calculate_points(
        is_correct=is_correct,
        response_time_ms=response_time_ms,
        time_limit_seconds=time_limit_seconds,
        max_points=max_points,
    )


def test_incorrect_answer_receives_zero_points() -> None:
    assert score(250, is_correct=False) == 0


@pytest.mark.parametrize("response_time_ms", [0, 1, 499])
def test_answer_faster_than_half_a_second_receives_maximum_points(
    response_time_ms: int,
) -> None:
    assert score(response_time_ms) == 1000


def test_half_second_answer_uses_speed_formula() -> None:
    assert score(500) == 992


def test_matches_kahoot_documented_example() -> None:
    assert score(2_000) == 967


def test_answer_at_deadline_receives_half_points() -> None:
    assert score(30_000) == 500


def test_exact_half_is_rounded_up() -> None:
    assert score(1_000, time_limit_seconds=1, max_points=1) == 1


def test_custom_question_point_value_uses_same_formula() -> None:
    assert score(2_000, max_points=2000) == 1933


def test_later_correct_answers_never_receive_more_points() -> None:
    times = [500, 1_000, 5_000, 15_000, 30_000]
    points = [score(response_time_ms) for response_time_ms in times]

    assert points == sorted(points, reverse=True)


def test_response_after_deadline_is_rejected() -> None:
    with pytest.raises(ValueError, match="late response"):
        score(30_001)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"response_time_ms": -1}, "Response time"),
        ({"time_limit_seconds": 0}, "Time limit"),
        ({"max_points": 0}, "Maximum points"),
    ],
)
def test_invalid_scoring_inputs_are_rejected(
    overrides: dict[str, int], message: str
) -> None:
    arguments = {
        "is_correct": True,
        "response_time_ms": 1_000,
        "time_limit_seconds": 30,
        "max_points": 1000,
    }
    arguments.update(overrides)

    with pytest.raises(ValueError, match=message):
        calculate_points(**arguments)
