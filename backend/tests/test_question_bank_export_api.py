"""Account-wide question bank: the admin dashboard's courses, quizzes and CSV export."""

from tests.test_class_quizzes_api import act_as, classes, create  # noqa: F401
from tests.test_question_bank_api import CSV_HEADER


def _publish(client, data, quiz) -> None:
    response = client.post(
        f"/classes/{data['main']}/quizzes/{quiz['quiz_id']}/publish",
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


def test_sources_list_each_course_and_quiz_with_question_counts(classes) -> None:
    client, _, data = classes
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


def test_sources_follow_bank_visibility(classes) -> None:
    client, identities, data = classes
    draft = create(client, data["main"], "Amy's draft")

    # An organizer doesn't see a member's draft, and a course with nothing
    # visible isn't listed.
    act_as(client, identities["prof"])
    assert client.get("/question-bank/sources").json() == {"courses": []}

    act_as(client, identities["amy"])
    _publish(client, data, draft)

    act_as(client, identities["prof"])
    courses = client.get("/question-bank/sources").json()["courses"]
    assert [course["class_id"] for course in courses] == [data["main"]]

    # Other members still see nothing of Amy's.
    act_as(client, identities["zoe"])
    assert client.get("/question-bank/sources").json() == {"courses": []}


def test_items_filter_by_course_quiz_and_search(classes) -> None:
    client, _, data = classes
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
    client, _, data = classes
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
    selected = _rows(
        _export(
            client,
            class_ids=[data["main"]],
            bank_question_ids=[item["bank_question_id"] for item in items],
        )
    )
    assert selected == ["Select a vowel.,,A,B,,,A"]


def test_export_rejects_courses_and_questions_outside_the_callers_reach(classes) -> None:
    client, identities, data = classes
    create(client, data["main"], "Amy's quiz")
    amy_ids = [
        item["bank_question_id"]
        for item in client.get(
            "/question-bank/items", params={"class_ids": [data["main"]]}
        ).json()["items"]
    ]

    # Prof isn't a member of "Other".
    act_as(client, identities["prof"])
    outside = _export(client, class_ids=[data["other"]])
    assert outside.status_code == 404
    assert outside.json()["error"]["code"] == "class_not_found"
    listing = client.get("/question-bank/items", params={"class_ids": [data["other"]]})
    assert listing.status_code == 404

    # Amy's draft questions aren't visible to the organizer.
    hidden = _export(client, class_ids=[data["main"]], bank_question_ids=amy_ids)
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "bank_question_not_found"

    # A question from another course than the one selected isn't exported.
    act_as(client, identities["amy"])
    create(client, data["other"], "Elsewhere")
    elsewhere = _export(client, class_ids=[data["other"]], bank_question_ids=amy_ids)
    assert elsewhere.status_code == 404

    for name in ("left", "outsider"):
        act_as(client, identities[name])
        assert _export(client, class_ids=[data["main"]]).status_code == 404


def test_export_request_is_validated(classes) -> None:
    client, _, data = classes

    for payload in (
        {"class_ids": []},
        {"class_ids": [data["main"], data["main"]]},
        {"class_ids": [data["main"]], "bank_question_ids": []},
        {"class_ids": [data["main"]], "bank_question_ids": [1, 1]},
    ):
        assert _export(client, **payload).status_code == 422, payload
