"""Question-bank, CSV, and quiz-duplication behavior."""

from datetime import UTC, datetime

from app.models import QuizCollaborator, QuizSubmission, SubmissionStatus
from tests.test_class_quizzes_api import act_as, classes, create  # noqa: F401


CSV_HEADER = (
    "question_text,explanation,choice_a,choice_b,choice_c,choice_d,"
    "correct_choices,time_limit_seconds,base_points"
)


def test_new_questions_are_automatically_banked_and_searchable(classes) -> None:
    client, _, data = classes
    create(client, data["main"], "Numbers")
    create(client, data["other"], "Letters")

    response = client.get(
        f"/classes/{data['main']}/question-bank",
        params={"scope": "mine", "search": "vowel"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["question_text"] for item in body["items"]] == [
        "Select a vowel.",
        "Select a vowel.",
    ]
    assert {item["source_class_id"] for item in body["items"]} == {
        data["main"],
        data["other"],
    }
    assert body["pagination"]["total_items"] == 2


def test_class_bank_hides_drafts_but_shows_approved_questions(classes) -> None:
    client, identities, data = classes
    quiz = create(client, data["main"], "Needs approval")

    act_as(client, identities["zoe"])
    before = client.get(f"/classes/{data['main']}/question-bank").json()
    assert before["items"] == []

    act_as(client, identities["amy"])
    published = client.post(
        f"/classes/{data['main']}/quizzes/{quiz['quiz_id']}/publish",
        json={"expected_revision": quiz["revision"]},
    )
    assert published.status_code == 200, published.json()
    version_id = published.json()["version"]["quiz_version_id"]
    with client.app.state.database.session_factory() as db:
        db.add(
            QuizSubmission(
                class_id=data["main"],
                quiz_version_id=version_id,
                submitted_by_id=identities["amy"].account_id,
                status=SubmissionStatus.APPROVED,
                decided_by_id=identities["prof"].account_id,
                decided_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        db.commit()

    act_as(client, identities["zoe"])
    after = client.get(f"/classes/{data['main']}/question-bank").json()
    assert {item["question_text"] for item in after["items"]} == {
        "Which number is even?",
        "Select a vowel.",
    }


def test_bank_selection_copies_an_independent_question_snapshot(classes) -> None:
    client, _, data = classes
    source = create(client, data["main"], "Source")
    target = create(client, data["main"], "Target")
    bank = client.get(
        f"/classes/{data['main']}/question-bank",
        params={"scope": "mine", "search": "even"},
    ).json()["items"]

    added = client.post(
        f"/classes/{data['main']}/quizzes/{target['quiz_id']}/questions/from-bank",
        json={"bank_question_ids": [bank[0]["bank_question_id"]]},
    )
    assert added.status_code == 200, added.json()
    assert added.json()["version"]["questions"][-1]["question_text"] == "Which number is even?"

    source_question = source["version"]["questions"][0]
    changed = client.patch(
        f"/classes/{data['main']}/quizzes/{source['quiz_id']}/questions/"
        f"{source_question['question_id']}",
        json={
            "expected_revision": source_question["revision"],
            "question_text": "Which number is divisible by two?",
            "time_limit_seconds": 15,
            "base_points": 500,
            "choices": [
                {"choice_text": "2", "is_correct": True},
                {"choice_text": "3", "is_correct": False},
            ],
        },
    )
    assert changed.status_code == 200, changed.json()
    unchanged = client.get(f"/quizzes/{target['quiz_id']}").json()
    assert unchanged["version"]["questions"][-1]["question_text"] == "Which number is even?"


def test_any_readable_quiz_can_be_duplicated_without_sharing_state(classes) -> None:
    client, identities, data = classes
    source = create(client, data["main"], "Shared source")
    with client.app.state.database.session_factory() as db:
        db.add(
            QuizCollaborator(
                quiz_id=source["quiz_id"],
                account_id=identities["zoe"].account_id,
                shared_by_id=identities["amy"].account_id,
            )
        )
        db.commit()

    act_as(client, identities["prof"])
    response = client.post(
        f"/classes/{data['main']}/quizzes/{source['quiz_id']}/duplicate"
    )

    assert response.status_code == 201, response.json()
    copied = response.json()["quiz"]
    assert copied["author_id"] == identities["prof"].account_id
    assert copied["class_id"] == data["main"]
    assert copied["status"] == "DRAFT"
    assert copied["version"]["title"] == "Copy of Shared source"
    assert [q["question_id"] for q in copied["version"]["questions"]] != [
        q["question_id"] for q in source["version"]["questions"]
    ]
    with client.app.state.database.session_factory() as db:
        assert db.query(QuizCollaborator).filter_by(quiz_id=copied["quiz_id"]).count() == 0


def test_duplicate_title_stays_within_database_limit(classes) -> None:
    client, _, data = classes
    source = create(client, data["main"], "x" * 200)

    response = client.post(
        f"/classes/{data['main']}/quizzes/{source['quiz_id']}/duplicate"
    )

    assert response.status_code == 201, response.json()
    assert len(response.json()["quiz"]["version"]["title"]) == 200
    assert response.json()["quiz"]["version"]["title"].startswith("Copy of ")


def test_csv_is_previewed_before_import_and_can_save_unselected_rows(classes) -> None:
    client, _, data = classes
    quiz = create(client, data["main"], "CSV target")
    csv_text = "\n".join(
        [
            CSV_HEADER,
            "Imported one,,Yes,No,,,A,30,750",
            "Saved only,,Red,Blue,,,B,20,1000",
            "Broken,,Only one,,,,A,20,1000",
        ]
    )
    preview = client.post(
        f"/classes/{data['main']}/question-bank/csv/preview",
        json={"csv_text": csv_text},
    )
    assert preview.status_code == 200, preview.json()
    rows = preview.json()["rows"]
    assert preview.json()["valid_count"] == 2
    assert preview.json()["invalid_count"] == 1

    imported = client.post(
        f"/classes/{data['main']}/quizzes/{quiz['quiz_id']}/questions/csv",
        json={
            "rows": [{"row_number": rows[0]["row_number"], "question": rows[0]["question"]}],
            "save_unselected_to_bank": True,
            "bank_only_rows": [
                {"row_number": rows[1]["row_number"], "question": rows[1]["question"]}
            ],
        },
    )
    assert imported.status_code == 200, imported.json()
    assert imported.json()["added_to_quiz"] == 1
    assert imported.json()["saved_to_bank_only"] == 1
    assert imported.json()["quiz"]["version"]["questions"][-1]["question_text"] == "Imported one"
    bank_texts = {
        item["question_text"]
        for item in client.get(
            f"/classes/{data['main']}/question-bank", params={"scope": "mine"}
        ).json()["items"]
    }
    assert {"Imported one", "Saved only"} <= bank_texts


def test_csv_export_neutralizes_spreadsheet_formulas(classes) -> None:
    client, _, data = classes
    preview = client.post(
        f"/classes/{data['main']}/question-bank/csv/preview",
        json={"csv_text": f"{CSV_HEADER}\n=2+2,,Yes,No,,,A,20,1000"},
    ).json()
    saved = client.post(
        f"/classes/{data['main']}/question-bank/csv",
        json={"rows": [{"row_number": 2, "question": preview["rows"][0]["question"]}]},
    )
    assert saved.status_code == 201, saved.json()

    exported = client.get(
        f"/classes/{data['main']}/question-bank/export.csv",
        params={"scope": "mine"},
    )
    assert exported.status_code == 200
    assert "'=2+2" in exported.text


def test_csv_preview_rejects_more_than_500_questions(classes) -> None:
    client, _, data = classes
    row = "Question,,Yes,No,,,A,20,1000"

    response = client.post(
        f"/classes/{data['main']}/question-bank/csv/preview",
        json={"csv_text": "\n".join([CSV_HEADER, *([row] * 501)])},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "csv_too_many_rows"


def test_nonmembers_cannot_use_question_bank_or_duplication(classes) -> None:
    client, identities, data = classes
    source = create(client, data["main"])
    act_as(client, identities["outsider"])

    assert client.get(f"/classes/{data['main']}/question-bank").status_code == 404
    assert client.post(
        f"/classes/{data['main']}/quizzes/{source['quiz_id']}/duplicate"
    ).status_code == 404
