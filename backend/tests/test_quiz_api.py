from collections.abc import Iterator

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


def test_saved_quiz_has_no_edit_or_publish_endpoint(
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
