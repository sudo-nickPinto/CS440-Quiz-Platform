import pytest
from pydantic import ValidationError

from app.schemas.results import ClosedQuestionResultsSnapshot


def results_snapshot() -> dict:
    return {
        "session_id": 10,
        "session_question_id": 20,
        "correct_choice_ids": [31],
        "choices": [
            {"choice_id": 31, "response_count": 3, "is_correct": True},
            {"choice_id": 32, "response_count": 1, "is_correct": False},
        ],
        "participants": [
            {
                "session_participant_id": participant_id,
                "display_name": f"Player {participant_id}",
                "selected_choice_id": 31,
                "is_correct": True,
                "points_awarded": points,
                "cumulative_score": score,
                "rank": rank,
            }
            for participant_id, points, score, rank in [
                (1, 900, 5000, 1),
                (2, 850, 4500, 2),
                (3, 800, 4000, 3),
                (4, 750, 4000, 3),
                (5, 700, 3500, 5),
            ]
        ],
    }


def test_snapshot_contains_choice_totals_and_rank_style_ties() -> None:
    snapshot = ClosedQuestionResultsSnapshot.model_validate(results_snapshot())

    assert set(snapshot.model_dump()) == {
        "session_id",
        "session_question_id",
        "correct_choice_ids",
        "choices",
        "participants",
    }
    assert snapshot.correct_choice_ids == [31]
    assert [choice.response_count for choice in snapshot.choices] == [3, 1]
    assert set(snapshot.choices[0].model_dump()) == {
        "choice_id",
        "response_count",
        "is_correct",
    }
    assert set(snapshot.participants[0].model_dump()) == {
        "session_participant_id",
        "display_name",
        "selected_choice_id",
        "is_correct",
        "points_awarded",
        "cumulative_score",
        "rank",
    }
    assert [participant.rank for participant in snapshot.participants] == [
        1,
        2,
        3,
        3,
        5,
    ]


def test_snapshot_represents_a_participant_who_did_not_answer() -> None:
    data = results_snapshot()
    data["participants"][0].update(
        selected_choice_id=None,
        is_correct=False,
        points_awarded=0,
    )

    participant = ClosedQuestionResultsSnapshot.model_validate(data).participants[0]

    assert participant.selected_choice_id is None
    assert participant.is_correct is False
    assert participant.points_awarded == 0


def test_snapshot_rejects_dense_ranking_after_a_tie() -> None:
    data = results_snapshot()
    data["participants"][-1]["rank"] = 4

    with pytest.raises(ValidationError, match="RANK behavior"):
        ClosedQuestionResultsSnapshot.model_validate(data)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("correct_choice_ids", 0), 0),
        (("choices", 0, "response_count"), -1),
        (("participants", 0, "points_awarded"), -1),
        (("participants", 0, "cumulative_score"), -1),
        (("participants", 0, "rank"), 0),
    ],
    ids=[
        "correct-choice-id",
        "response-count",
        "question-points",
        "cumulative-score",
        "rank",
    ],
)
def test_snapshot_rejects_impossible_numeric_values(
    path: tuple[str | int, ...], value: int
) -> None:
    data = results_snapshot()
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValidationError):
        ClosedQuestionResultsSnapshot.model_validate(data)
