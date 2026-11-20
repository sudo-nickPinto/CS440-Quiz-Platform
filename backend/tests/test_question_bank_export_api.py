"""Account-wide question bank: the admin dashboard's courses, quizzes and CSV export.

Only faculty organizers use it, for the courses they organize.
"""

from sqlalchemy import select

from app.auth import CurrentAccount
from app.models import AccountRole, ClassMembership, ClassRole, QuestionBankItem
from tests.test_class_quizzes_api import act_as, classes, create  # noqa: F401
from tests.test_question_bank_api import CSV_HEADER


def _faculty(identities, name: str) -> CurrentAccount:
    return CurrentAccount(identities[name].account_id, AccountRole.ADMIN, True)


def _organize_other_too(client, identities, data) -> None:
    """Make prof an organizer of "Other" as well as CS 440."""
    with client.app.state.database.session_factory() as db:
        db.add(ClassMembership(
            class_id=data["other"],
            account_id=identities["prof"].account_id,
            role=ClassRole.ORGANIZER,
        ))
        db.commit()


def _publish(client, class_id, quiz) -> None:
    response = client.post(
        f"/classes/{class_id}/quizzes/{quiz['quiz_id']}/publish",
        json={"expected_revision": quiz["revision"]},
    )
    assert response.status_code == 200, response.json()


def _export(client, **payload):
    return client.post("/question-bank/export.csv", json=payload)


def _rows(response) -> list[str]:
    assert response.status_code == 200, response.text
    lines = response.text.strip().splitlines()
    assert lines[0] == CSV_HEADER
    return lines[1:]


def _error(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def test_sources_list_organized_courses_and_quizzes_with_counts(classes) -> None:
    client, identities, data = classes
    _organize_other_too(client, identities, data)
    act_as(client, _faculty(identities, "prof"))
    numbers = create(client, data["main"], "Numbers")
    letters = create(client, data["other"], "Letters")

    response = client.get("/question-bank/sources")

    assert response.status_code == 200
    assert response.json() == {
        "courses": [
            {
                "class_id": data["main"],
                "name": "CS 440",
                "archived": False,
                "question_count": 2,
                "quizzes": [
                    {"quiz_id": numbers["quiz_id"], "title": "Numbers", "question_count": 2}
                ],
            },
            {
                "class_id": data["other"],
                "name": "Other",
                "archived": False,
                "question_count": 2,
                "quizzes": [
                    {"quiz_id": letters["quiz_id"], "title": "Letters", "question_count": 2}
                ],
            },
        ]
    }


def test_organizers_see_published_quizzes_but_not_member_drafts(classes) -> None:
    client, identities, data = classes
    draft = create(client, data["main"], "Amy's quiz")  # Amy is a member.
    prof = _faculty(identities, "prof")

    act_as(client, prof)
    assert client.get("/question-bank/sources").json() == {"courses": []}

    act_as(client, identities["amy"])
    _publish(client, data["main"], draft)

    act_as(client, prof)
    courses = client.get("/question-bank/sources").json()["courses"]
    assert [(course["class_id"], course["question_count"]) for course in courses] == [
        (data["main"], 2)
    ]


def test_members_and_non_faculty_cannot_use_it(classes) -> None:
    client, identities, data = classes
    create(client, data["main"], "Amy's quiz")

    # A member, even of courses where they wrote quizzes, gets nothing.
    for identity in (identities["amy"], identities["prof"]):  # prof here isn't faculty
        act_as(client, identity)
        assert client.get("/question-bank/sources").json() == {"courses": []}
        items = client.get("/question-bank/items", params={"class_ids": [data["main"]]})
        assert _error(items) == (403, "not_class_organizer")
        assert _error(_export(client, class_ids=[data["main"]])) == (
            403, "not_class_organizer"
        )

    # Not in the course at all: the course doesn't exist for them.
    act_as(client, _faculty(identities, "prof"))
    assert _error(_export(client, class_ids=[data["other"]])) == (404, "class_not_found")
    for name in ("left", "outsider"):
        act_as(client, identities[name])
        assert _export(client, class_ids=[data["main"]]).status_code == 404


def test_items_filter_by_course_quiz_and_search(classes) -> None:
    client, identities, data = classes
    _organize_other_too(client, identities, data)
    act_as(client, _faculty(identities, "prof"))
    numbers = create(client, data["main"], "Numbers")
    create(client, data["main"], "More numbers")
    create(client, data["other"], "Letters")

    both = client.get(
        "/question-bank/items",
        params={"class_ids": [data["main"], data["other"]], "page_size": 100},
    ).json()
    assert both["pagination"]["total_items"] == 6

    main_only = client.get(
        "/question-bank/items", params={"class_ids": [data["main"]]}
    ).json()
    assert {item["source_class_id"] for item in main_only["items"]} == {data["main"]}
    assert main_only["pagination"]["total_items"] == 4

    one_quiz = client.get(
        "/question-bank/items",
        params={"class_ids": [data["main"]], "quiz_id": numbers["quiz_id"]},
    ).json()
    assert {item["source_quiz_id"] for item in one_quiz["items"]} == {numbers["quiz_id"]}
    assert one_quiz["pagination"]["total_items"] == 2

    searched = client.get(
        "/question-bank/items",
        params={"class_ids": [data["main"]], "search": "vowel"},
    ).json()
    assert [item["question_text"] for item in searched["items"]] == [
        "Select a vowel.",
        "Select a vowel.",
    ]


def test_export_everything_one_quiz_or_selected_questions(classes) -> None:
    client, identities, data = classes
    _organize_other_too(client, identities, data)
    act_as(client, _faculty(identities, "prof"))
    numbers = create(client, data["main"], "Numbers")
    create(client, data["other"], "Letters")

    everything = _rows(_export(client, class_ids=[data["main"], data["other"]]))
    assert len(everything) == 4

    one_course = _rows(_export(client, class_ids=[data["other"]]))
    assert len(one_course) == 2

    one_quiz = _rows(
        _export(client, class_ids=[data["main"]], quiz_id=numbers["quiz_id"])
    )
    assert one_quiz == ["Which number is even?,,2,3,,,A", "Select a vowel.,,A,B,,,A"]

    searched = _rows(
        _export(client, class_ids=[data["main"], data["other"]], search="even")
    )
    assert len(searched) == 2

    items = client.get(
        "/question-bank/items",
        params={"class_ids": [data["main"]], "search": "vowel"},
    ).json()["items"]
    selected_ids = [item["bank_question_id"] for item in items]
    selected = _rows(
        _export(client, class_ids=[data["main"]], bank_question_ids=selected_ids)
    )
    assert selected == ["Select a vowel.,,A,B,,,A"]

    # Selected questions must come from the selected courses.
    elsewhere = _export(client, class_ids=[data["other"]], bank_question_ids=selected_ids)
    assert _error(elsewhere) == (404, "bank_question_not_found")


def test_hidden_member_drafts_cannot_be_exported_by_id(classes) -> None:
    client, identities, data = classes
    create(client, data["main"], "Amy's draft")
    with client.app.state.database.session_factory() as db:
        amy_ids = list(db.scalars(select(QuestionBankItem.bank_question_id)))

    act_as(client, _faculty(identities, "prof"))
    hidden = _export(client, class_ids=[data["main"]], bank_question_ids=amy_ids)
    assert _error(hidden) == (404, "bank_question_not_found")


def test_export_request_is_validated(classes) -> None:
    client, identities, data = classes
    act_as(client, _faculty(identities, "prof"))

    for payload in (
        {"class_ids": []},
        {"class_ids": [data["main"], data["main"]]},
        {"class_ids": [data["main"]], "bank_question_ids": []},
        {"class_ids": [data["main"]], "bank_question_ids": [1, 1]},
    ):
        assert _export(client, **payload).status_code == 422, payload
