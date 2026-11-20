"""The class dashboard's question bank: an organizer downloads this class's
questions as CSV (quizzes, paged questions, download by id)."""

from sqlalchemy import select

from app.auth import CurrentAccount
from app.models import AccountRole, ClassMembership, ClassRole, QuestionBankItem
from tests.test_class_quizzes_api import act_as, classes, create  # noqa: F401
from tests.test_question_bank_api import CSV_HEADER


def _faculty(identities, name: str) -> CurrentAccount:
    return CurrentAccount(identities[name].account_id, AccountRole.ADMIN, True)


def _bank(data, class_key="main") -> str:
    return f"/classes/{data[class_key]}/question-bank"


def _publish(client, data, quiz) -> None:
    response = client.post(
        f"/classes/{data['main']}/quizzes/{quiz['quiz_id']}/publish",
        json={"expected_revision": quiz["revision"]},
    )
    assert response.status_code == 200, response.json()


def _ids(client, data) -> list[int]:
    items = client.get(f"{_bank(data)}/items", params={"page_size": 100}).json()["items"]
    return [item["bank_question_id"] for item in items]


def _download(client, data, ids, class_key="main"):
    return client.post(
        f"{_bank(data, class_key)}/download.csv", json={"bank_question_ids": ids}
    )


def _error(response) -> tuple[int, str]:
    return response.status_code, response.json()["error"]["code"]


def test_quizzes_and_items_cover_only_this_class(classes) -> None:
    client, identities, data = classes
    act_as(client, _faculty(identities, "prof"))
    numbers = create(client, data["main"], "Numbers")
    letters = create(client, data["main"], "Letters")
    with client.app.state.database.session_factory() as db:
        # Prof also organizes "Other"; its questions mustn't show up here.
        db.add(ClassMembership(
            class_id=data["other"], account_id=identities["prof"].account_id,
            role=ClassRole.ORGANIZER,
        ))
        db.commit()
    create(client, data["other"], "Elsewhere")

    quizzes = client.get(f"{_bank(data)}/quizzes")
    assert quizzes.status_code == 200
    assert quizzes.json() == {"quizzes": [
        {"quiz_id": letters["quiz_id"], "title": "Letters", "question_count": 2},
        {"quiz_id": numbers["quiz_id"], "title": "Numbers", "question_count": 2},
    ]}

    first = client.get(f"{_bank(data)}/items", params={"page_size": 3}).json()
    second = client.get(f"{_bank(data)}/items", params={"page_size": 3, "page": 2}).json()
    assert first["pagination"]["total_items"] == 4
    assert len(first["items"]) == 3 and len(second["items"]) == 1
    items = first["items"] + second["items"]
    assert {item["source_class_id"] for item in items} == {data["main"]}
    assert {item["source_quiz_id"] for item in items} == {
        numbers["quiz_id"], letters["quiz_id"],
    }


def test_organizers_see_published_quizzes_but_not_member_drafts(classes) -> None:
    client, identities, data = classes
    draft = create(client, data["main"], "Amy's quiz")  # Amy is a member.
    with client.app.state.database.session_factory() as db:
        amy_ids = list(db.scalars(select(QuestionBankItem.bank_question_id)))

    prof = _faculty(identities, "prof")
    act_as(client, prof)
    assert client.get(f"{_bank(data)}/quizzes").json() == {"quizzes": []}
    assert client.get(f"{_bank(data)}/items").json()["items"] == []
    assert _error(_download(client, data, amy_ids)) == (404, "bank_question_not_found")

    act_as(client, identities["amy"])
    _publish(client, data, draft)

    act_as(client, prof)
    assert [quiz["title"] for quiz in client.get(f"{_bank(data)}/quizzes").json()["quizzes"]] == [
        "Amy's quiz"
    ]
    assert sorted(_ids(client, data)) == sorted(amy_ids)


def test_download_returns_exactly_the_chosen_questions(classes) -> None:
    client, identities, data = classes
    act_as(client, _faculty(identities, "prof"))
    create(client, data["main"], "Numbers")
    items = client.get(f"{_bank(data)}/items").json()["items"]
    vowel = [item["bank_question_id"] for item in items if item["question_text"] == "Select a vowel."]

    everything = _download(client, data, [item["bank_question_id"] for item in items])
    assert everything.status_code == 200
    assert everything.headers["content-type"].startswith("text/csv")
    assert everything.text.strip().splitlines() == [
        CSV_HEADER,
        "Which number is even?,,2,3,,,A",
        "Select a vowel.,,A,B,,,A",
    ]
    assert _download(client, data, vowel).text.strip().splitlines() == [
        CSV_HEADER, "Select a vowel.,,A,B,,,A",
    ]


def test_only_organizers_of_the_class_can_use_it(classes) -> None:
    client, identities, data = classes
    create(client, data["main"], "Amy's quiz")

    # Members, and an organizer row without a faculty account, are refused.
    for identity in (identities["amy"], identities["prof"]):  # prof here isn't faculty
        act_as(client, identity)
        for response in (
            client.get(f"{_bank(data)}/quizzes"),
            client.get(f"{_bank(data)}/items"),
            _download(client, data, [1]),
        ):
            assert _error(response) == (403, "not_class_organizer")

    # Not in the class at all: the class doesn't exist for them.
    act_as(client, _faculty(identities, "prof"))
    assert _error(client.get(f"{_bank(data, 'other')}/items")) == (404, "class_not_found")
    for name in ("left", "outsider"):
        act_as(client, identities[name])
        assert client.get(f"{_bank(data)}/quizzes").status_code == 404


def test_download_request_is_validated(classes) -> None:
    client, identities, data = classes
    act_as(client, _faculty(identities, "prof"))

    for body in ({}, {"bank_question_ids": []}, {"bank_question_ids": [1, 1]}, {"bank_question_ids": [0]}):
        response = client.post(f"{_bank(data)}/download.csv", json=body)
        assert response.status_code == 422, body
