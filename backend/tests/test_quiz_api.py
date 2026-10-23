from collections.abc import Iterator
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentAccount, get_active_account, get_current_account
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models.account import Account, AccountRole

QUIZ_PAYLOAD = {
    "title": "MVP Quiz",
    "description": "A complete saved quiz",
    "questions": [
        {
            "question_text": "Which number is even?",
            "time_limit_seconds": 15,
            "base_points": 500,
            "choices": [
                {"choice_text": "2", "is_correct": True},
                {"choice_text": "3", "is_correct": False},
            ],
        },
        {
            "question_text": "Select a vowel.",
            "choices": [
                {"choice_text": "A", "is_correct": True},
                {"choice_text": "B", "is_correct": False},
            ],
        },
    ],
}


@pytest.fixture
def quiz_client() -> Iterator[tuple[TestClient, CurrentAccount, CurrentAccount]]:
    app = create_app(
        Settings(
            database_url="sqlite://",
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
        )
    )
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.database.engine)
        with app.state.database.session_factory() as db:
            author_model = Account(
                auth0_sub="auth0|author",
                email="author@example.com",
                display_name="Author",
                account_type=None,
            )
            reader_model = Account(
                auth0_sub="auth0|reader",
                email="reader@example.com",
                display_name="Reader",
                account_type=None,
            )
            db.add_all([author_model, reader_model])
            db.commit()
            author = CurrentAccount(author_model.account_id, AccountRole.USER, True)
            reader = CurrentAccount(reader_model.account_id, AccountRole.USER, True)

        app.dependency_overrides[get_active_account] = lambda: author
        yield client, author, reader


def create_quiz(client: TestClient) -> dict:
    response = client.post("/quizzes", json=QUIZ_PAYLOAD)
    assert response.status_code == 201
    return response.json()


def test_save_quiz_creates_one_public_published_version(
    quiz_client: tuple[TestClient, CurrentAccount, CurrentAccount],
) -> None:
    client, author, _ = quiz_client

    body = create_quiz(client)

    assert body["author_id"] == author.account_id
    assert body["status"] == "PUBLISHED"
    assert body["visibility"] == "PUBLIC"
    assert body["version"]["version_number"] == 1
    assert body["version"]["published_at"] is not None
    assert [item["question_order"] for item in body["version"]["questions"]] == [
        1,
        2,
    ]
    assert [
        item["choice_order"] for item in body["version"]["questions"][0]["choices"]
    ] == [1, 2]


def test_all_active_users_can_list_and_retrieve_saved_quizzes(
    quiz_client: tuple[TestClient, CurrentAccount, CurrentAccount],
) -> None:
    client, _, reader = quiz_client
    quiz = create_quiz(client)
    client.app.dependency_overrides[get_active_account] = lambda: reader

    listing = client.get("/quizzes")
    detail = client.get(f"/quizzes/{quiz['quiz_id']}")

    assert listing.status_code == 200
    assert listing.json()[0]["title"] == "MVP Quiz"
    assert listing.json()[0]["question_count"] == 2
    assert detail.status_code == 200
    assert detail.json()["quiz_id"] == quiz["quiz_id"]


def test_non_author_cannot_archive_and_archived_quiz_is_not_public(
    quiz_client: tuple[TestClient, CurrentAccount, CurrentAccount],
) -> None:
    client, author, reader = quiz_client
    quiz = create_quiz(client)
    quiz_id = quiz["quiz_id"]
    client.app.dependency_overrides[get_active_account] = lambda: reader

    denied = client.patch(f"/quizzes/{quiz_id}/archive")
    assert denied.status_code == 403

    client.app.dependency_overrides[get_active_account] = lambda: author
    archived = client.patch(f"/quizzes/{quiz_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"

    client.app.dependency_overrides[get_active_account] = lambda: reader
    assert client.get("/quizzes").json() == []
    assert client.get(f"/quizzes/{quiz_id}").status_code == 404


def test_admin_can_control_and_access_every_quiz(
    quiz_client: tuple[TestClient, CurrentAccount, CurrentAccount],
) -> None:
    client, _, _ = quiz_client
    quiz = create_quiz(client)
    admin = CurrentAccount(999, AccountRole.ADMIN, True)
    client.app.dependency_overrides[get_active_account] = lambda: admin

    archived = client.patch(f"/quizzes/{quiz['quiz_id']}/archive")
    listing = client.get("/quizzes")
    detail = client.get(f"/quizzes/{quiz['quiz_id']}")

    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
    assert listing.status_code == 200
    assert listing.json()[0]["status"] == "ARCHIVED"
    assert detail.status_code == 200


def test_partial_patch_and_separate_publish_are_not_supported(
    quiz_client: tuple[TestClient, CurrentAccount, CurrentAccount],
) -> None:
    client, _, _ = quiz_client
    quiz_id = create_quiz(client)["quiz_id"]

    edit = client.patch(f"/quizzes/{quiz_id}", json={"title": "Changed"})
    assert edit.status_code == 405
    assert client.post(f"/quizzes/{quiz_id}/publish").status_code == 404


def test_inactive_account_cannot_use_quiz_endpoints(
    quiz_client: tuple[TestClient, CurrentAccount, CurrentAccount],
) -> None:
    client, author, _ = quiz_client
    client.app.dependency_overrides.pop(get_active_account)
    client.app.dependency_overrides[get_current_account] = lambda: CurrentAccount(
        author.account_id, AccountRole.USER, False
    )

    response = client.get("/quizzes")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "inactive_account"


@pytest.mark.parametrize(
    ("explanation", "expected"),
    [
        (
            "  Two is even.\nIt is divisible by two.  ",
            "Two is even.\nIt is divisible by two.",
        ),
        ("", None),
        ("   \n  ", None),
        (None, None),
        ("x" * 5000, "x" * 5000),
    ],
)
def test_explanation_is_saved_and_returned(
    quiz_client,
    explanation,
    expected,
) -> None:
    client, _, _ = quiz_client
    payload = deepcopy(QUIZ_PAYLOAD)
    payload["questions"][0]["explanation"] = explanation

    created = client.post("/quizzes", json=payload)

    assert created.status_code == 201
    body = created.json()
    assert body["version"]["questions"][0]["explanation"] == expected

    # The second question omits explanation entirely.
    assert body["version"]["questions"][1]["explanation"] is None

    # A separate GET must return the saved value.
    fetched = client.get(f"/quizzes/{body['quiz_id']}")

    assert fetched.status_code == 200
    assert fetched.json()["version"]["questions"][0]["explanation"] == expected


def test_explanation_over_limit_is_rejected(quiz_client) -> None:
    client, _, _ = quiz_client
    payload = deepcopy(QUIZ_PAYLOAD)
    payload["questions"][0]["explanation"] = "x" * 5001

    response = client.post("/quizzes", json=payload)

    assert response.status_code == 422


def revision_payload(base_version: int = 1) -> dict:
    payload = deepcopy(QUIZ_PAYLOAD)
    payload["base_version"] = base_version
    payload["title"] = "Revised Quiz"
    payload["description"] = "Updated description"

    payload["questions"][0]["question_text"] = "Updated question?"
    payload["questions"][0]["explanation"] = "Updated explanation."
    payload["questions"][0]["base_points"] = 750

    return payload


def test_edit_creates_new_version_without_changing_original(quiz_client):
    from app.models.quiz import QuizVersion
    from app.schemas.quiz import QuizVersionResponse

    client, _, _ = quiz_client
    original = create_quiz(client)

    response = client.put(
        f"/quizzes/{original['quiz_id']}",
        json=revision_payload(),
    )

    assert response.status_code == 200
    revised = response.json()

    assert revised["quiz_id"] == original["quiz_id"]
    assert revised["author_id"] == original["author_id"]
    assert revised["version"]["version_number"] == 2
    assert revised["version"]["title"] == "Revised Quiz"
    assert revised["version"]["description"] == "Updated description"

    new_question = revised["version"]["questions"][0]
    old_question = original["version"]["questions"][0]

    assert new_question["explanation"] == "Updated explanation."
    assert new_question["base_points"] == 750
    assert new_question["question_id"] != old_question["question_id"]

    old_choices = {choice["choice_id"] for choice in old_question["choices"]}
    new_choices = {choice["choice_id"] for choice in new_question["choices"]}
    assert old_choices.isdisjoint(new_choices)

    with client.app.state.database.session_factory() as db:
        stored_original = db.get(
            QuizVersion,
            original["version"]["quiz_version_id"],
        )

        assert (
            QuizVersionResponse.model_validate(stored_original).model_dump(mode="json")
            == original["version"]
        )

    fetched = client.get(f"/quizzes/{original['quiz_id']}").json()
    assert fetched["version"]["version_number"] == 2

    listing = client.get("/quizzes").json()
    assert listing[0]["title"] == "Revised Quiz"


def test_stale_edit_is_rejected_without_overwriting_newer_version(quiz_client):
    client, _, _ = quiz_client
    original = create_quiz(client)
    path = f"/quizzes/{original['quiz_id']}"

    assert client.put(path, json=revision_payload()).status_code == 200

    stale = revision_payload()
    stale["title"] = "Must not overwrite the saved title"

    response = client.put(path, json=stale)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quiz_version_conflict"

    current = client.get(path).json()
    assert current["version"]["version_number"] == 2
    assert current["version"]["title"] == "Revised Quiz"


@pytest.mark.parametrize("role", [AccountRole.USER, AccountRole.ADMIN])
def test_only_creator_can_edit_even_if_other_user_is_admin(quiz_client, role):
    client, _, reader = quiz_client
    original = create_quiz(client)

    other = CurrentAccount(reader.account_id, role, True)
    client.app.dependency_overrides[get_active_account] = lambda: other

    response = client.put(
        f"/quizzes/{original['quiz_id']}",
        json=revision_payload(),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "quiz_edit_denied"


def test_archived_quiz_cannot_be_edited(quiz_client):
    client, _, _ = quiz_client
    original = create_quiz(client)
    path = f"/quizzes/{original['quiz_id']}"

    assert client.patch(f"{path}/archive").status_code == 200

    response = client.put(path, json=revision_payload())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quiz_not_editable"


def test_invalid_edit_does_not_publish_a_version(quiz_client):
    client, _, _ = quiz_client
    original = create_quiz(client)
    path = f"/quizzes/{original['quiz_id']}"

    invalid = revision_payload()
    invalid["questions"][0]["choices"] = []

    assert client.put(path, json=invalid).status_code == 422

    current = client.get(path).json()
    assert current["version"]["version_number"] == 1


@pytest.mark.parametrize("session_status", ["LOBBY", "ACTIVE", "COMPLETED"])
def test_old_sessions_keep_version_and_new_sessions_use_revision(
    quiz_client,
    session_status,
):
    from app.models.session import LiveSession, LiveSessionStatus

    client, _, _ = quiz_client
    original = create_quiz(client)
    quiz_id = original["quiz_id"]

    response = client.post(f"/quizzes/{quiz_id}/sessions")
    assert response.status_code == 201
    old_session = response.json()

    with client.app.state.database.session_factory() as db:
        session = db.get(LiveSession, old_session["session_id"])
        session.status = LiveSessionStatus(session_status)
        db.commit()

    updated = client.put(
        f"/quizzes/{quiz_id}",
        json=revision_payload(),
    )
    assert updated.status_code == 200

    response = client.post(f"/quizzes/{quiz_id}/sessions")
    assert response.status_code == 201
    new_session = response.json()

    assert (
        new_session["quiz_version_id"] == updated.json()["version"]["quiz_version_id"]
    )

    with client.app.state.database.session_factory() as db:
        stored_old = db.get(LiveSession, old_session["session_id"])
        assert stored_old.quiz_version_id == original["version"]["quiz_version_id"]
