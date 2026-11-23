"""Question-bank, CSV, and quiz-duplication behavior."""

from datetime import UTC, datetime

from app.models import (
    Class,
    ClassMembership,
    MembershipStatus,
    QuestionBankItem,
    QuizCollaborator,
)
from tests.test_class_quizzes_api import act_as, classes, create  # noqa: F401


CSV_HEADER = (
    "question_text,explanation,choice_a,choice_b,choice_c,choice_d,"
    "correct_choices"
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
    assert "time_limit_seconds" not in body["items"][0]
    assert "base_points" not in body["items"][0]


def test_bank_visibility_is_limited_to_owner_collaborator_and_organizer(classes) -> None:
    client, identities, data = classes
    quiz = create(client, data["main"], "Shared only when allowed")

    act_as(client, identities["zoe"])
    assert client.get(
        f"/classes/{data['main']}/question-bank"
    ).json()["items"] == []

    act_as(client, identities["prof"])
    assert client.get(
        f"/classes/{data['main']}/question-bank"
    ).json()["items"] == []

    with client.app.state.database.session_factory() as db:
        db.add(
            QuizCollaborator(
                quiz_id=quiz["quiz_id"],
                account_id=identities["zoe"].account_id,
                shared_by_id=identities["amy"].account_id,
            )
        )
        db.commit()

    act_as(client, identities["zoe"])
    shared = client.get(
        f"/classes/{data['main']}/question-bank",
        params={"scope": "mine"},
    ).json()
    assert {item["question_text"] for item in shared["items"]} == {
        "Which number is even?",
        "Select a vowel.",
    }

    act_as(client, identities["amy"])
    published = client.post(
        f"/classes/{data['main']}/quizzes/{quiz['quiz_id']}/publish",
        json={"expected_revision": quiz["revision"]},
    )
    assert published.status_code == 200, published.json()

    act_as(client, identities["prof"])
    organizer_view = client.get(
        f"/classes/{data['main']}/question-bank"
    ).json()
    assert {item["question_text"] for item in organizer_view["items"]} == {
        "Which number is even?",
        "Select a vowel.",
    }
    shared_bank_id = organizer_view["items"][0]["bank_question_id"]

    with client.app.state.database.session_factory() as db:
        collaborator = db.get(
            QuizCollaborator,
            (quiz["quiz_id"], identities["zoe"].account_id),
        )
        collaborator.revoked_at = datetime.now(UTC).replace(tzinfo=None)
        collaborator.revoked_by_id = identities["amy"].account_id
        db.commit()

    act_as(client, identities["zoe"])
    ordinary_member_view = client.get(
        f"/classes/{data['main']}/question-bank"
    ).json()
    assert ordinary_member_view["items"] == []

    target = create(client, data["main"], "Cannot copy hidden questions")
    unavailable = client.post(
        f"/classes/{data['main']}/quizzes/{target['quiz_id']}/questions/from-bank",
        json={"bank_question_ids": [shared_bank_id]},
    )
    assert unavailable.status_code == 404
    assert unavailable.json()["error"]["code"] == "bank_question_not_found"


def test_removed_collaborator_cannot_see_source_class_questions_elsewhere(classes) -> None:
    client, identities, data = classes
    source = create(client, data["main"], "Removed collaborator source")
    with client.app.state.database.session_factory() as db:
        db.add_all([
            QuizCollaborator(
                quiz_id=source["quiz_id"],
                account_id=identities["zoe"].account_id,
                shared_by_id=identities["amy"].account_id,
            ),
            ClassMembership(
                class_id=data["other"],
                account_id=identities["zoe"].account_id,
            ),
        ])
        membership = db.query(ClassMembership).filter_by(
            class_id=data["main"], account_id=identities["zoe"].account_id
        ).one()
        membership.status = MembershipStatus.REMOVED
        db.commit()

    act_as(client, identities["zoe"])
    response = client.get(
        f"/classes/{data['other']}/question-bank", params={"scope": "mine"}
    )

    assert response.status_code == 200
    assert response.json()["items"] == []


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
            "Imported one,,Yes,No,,,A",
            "Saved only,,Red,Blue,,,B",
            "Broken,,Only one,,,,A",
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
        json={"csv_text": f"{CSV_HEADER}\n=2+2,,Yes,No,,,A"},
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
    row = "Question,,Yes,No,,,A"

    response = client.post(
        f"/classes/{data['main']}/question-bank/csv/preview",
        json={"csv_text": "\n".join([CSV_HEADER, *([row] * 501)])},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "csv_too_many_rows"


def test_csv_and_bank_imports_enforce_editor_text_limits(classes) -> None:
    client, _, data = classes
    target = create(client, data["main"], "Text limit target")
    too_long = "x" * 201
    preview = client.post(
        f"/classes/{data['main']}/question-bank/csv/preview",
        json={"csv_text": f"{CSV_HEADER}\n{too_long},,Yes,No,,,A"},
    )
    assert preview.status_code == 200
    assert preview.json()["valid_count"] == 0
    assert "200 characters" in preview.json()["rows"][0]["errors"][0]

    direct_import = client.post(
        f"/classes/{data['main']}/quizzes/{target['quiz_id']}/questions/csv",
        json={
            "rows": [{
                "row_number": 2,
                "question": {
                    "question_text": too_long,
                    "choices": [
                        {"choice_text": "Yes", "is_correct": True},
                        {"choice_text": "No", "is_correct": False},
                    ],
                },
            }],
        },
    )
    assert direct_import.status_code == 422
    assert direct_import.json()["error"]["code"] == "question_text_too_long"

    with client.app.state.database.session_factory() as db:
        item = QuestionBankItem(
            owner_id=target["author_id"],
            source_class_id=data["main"],
            is_current=True,
            question_text=too_long,
            choices_json=[
                {"choice_text": "Yes", "is_correct": True},
                {"choice_text": "No", "is_correct": False},
            ],
        )
        db.add(item)
        db.commit()
        bank_question_id = item.bank_question_id
    from_bank = client.post(
        f"/classes/{data['main']}/quizzes/{target['quiz_id']}/questions/from-bank",
        json={"bank_question_ids": [bank_question_id]},
    )
    assert from_bank.status_code == 422
    assert from_bank.json()["error"]["code"] == "question_text_too_long"


def test_csv_export_rejects_questions_with_more_than_four_choices(classes) -> None:
    client, _, data = classes
    response = client.post(
        f"/classes/{data['main']}/quizzes",
        json={
            "title": "Five choices",
            "questions": [{
                "question_text": "Pick E",
                "choices": [
                    {"choice_text": letter, "is_correct": letter == "E"}
                    for letter in "ABCDE"
                ],
            }],
        },
    )
    assert response.status_code == 201, response.json()

    exported = client.get(
        f"/classes/{data['main']}/question-bank/export.csv",
        params={"scope": "mine"},
    )

    assert exported.status_code == 422
    assert exported.json()["error"]["code"] == "csv_choice_limit_exceeded"
    assert exported.json()["error"]["details"]["choice_limit"] == 4


def test_nonmembers_cannot_use_question_bank_or_duplication(classes) -> None:
    client, identities, data = classes
    source = create(client, data["main"])
    act_as(client, identities["outsider"])

    assert client.get(f"/classes/{data['main']}/question-bank").status_code == 404
    assert client.post(
        f"/classes/{data['main']}/quizzes/{source['quiz_id']}/duplicate"
    ).status_code == 404


def test_trashed_quiz_questions_leave_collaborator_and_organizer_bank_views(classes) -> None:
    client, identities, data = classes
    quiz = create(client, data["main"], "Trash leaves the bank")
    published = client.post(
        f"/classes/{data['main']}/quizzes/{quiz['quiz_id']}/publish",
        json={"expected_revision": quiz["revision"]},
    )
    assert published.status_code == 200, published.json()

    with client.app.state.database.session_factory() as db:
        db.add(
            QuizCollaborator(
                quiz_id=quiz["quiz_id"],
                account_id=identities["zoe"].account_id,
                shared_by_id=identities["amy"].account_id,
            )
        )
        db.commit()

    act_as(client, identities["zoe"])
    before_collab = client.get(
        f"/classes/{data['main']}/question-bank", params={"scope": "mine"}
    ).json()
    assert {item["question_text"] for item in before_collab["items"]} == {
        "Which number is even?",
        "Select a vowel.",
    }

    act_as(client, identities["prof"])
    before_org = client.get(f"/classes/{data['main']}/question-bank").json()
    assert {item["question_text"] for item in before_org["items"]} == {
        "Which number is even?",
        "Select a vowel.",
    }

    act_as(client, identities["amy"])
    assert client.post(f"/quizzes/{quiz['quiz_id']}/trash").status_code == 204
    owner_view = client.get(
        f"/classes/{data['main']}/question-bank", params={"scope": "mine"}
    ).json()
    assert {item["question_text"] for item in owner_view["items"]} == {
        "Which number is even?",
        "Select a vowel.",
    }

    act_as(client, identities["zoe"])
    after_collab = client.get(
        f"/classes/{data['main']}/question-bank", params={"scope": "mine"}
    ).json()
    assert after_collab["items"] == []

    act_as(client, identities["prof"])
    after_org = client.get(f"/classes/{data['main']}/question-bank").json()
    assert after_org["items"] == []



def test_trashed_class_source_quiz_leaves_collaborator_bank_elsewhere(classes) -> None:
    """A shared quiz in a trashed class must not stay visible in another class bank."""
    client, identities, data = classes
    quiz = create(client, data["main"], "Shared then class trashed")
    with client.app.state.database.session_factory() as db:
        db.add_all(
            [
                QuizCollaborator(
                    quiz_id=quiz["quiz_id"],
                    account_id=identities["zoe"].account_id,
                    shared_by_id=identities["amy"].account_id,
                ),
                ClassMembership(
                    class_id=data["other"],
                    account_id=identities["zoe"].account_id,
                ),
            ]
        )
        db.commit()

    act_as(client, identities["zoe"])
    visible = client.get(
        f"/classes/{data['other']}/question-bank", params={"scope": "mine"}
    ).json()
    assert {item["question_text"] for item in visible["items"]} == {
        "Which number is even?",
        "Select a vowel.",
    }

    with client.app.state.database.session_factory() as db:
        db.get(Class, data["main"]).deleted_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()

    act_as(client, identities["zoe"])
    hidden = client.get(
        f"/classes/{data['other']}/question-bank", params={"scope": "mine"}
    ).json()
    assert hidden["items"] == []

