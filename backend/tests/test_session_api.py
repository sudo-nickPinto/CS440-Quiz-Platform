from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models import Account, AccountRole, LiveSession, LiveSessionStatus
from app.services import sessions as session_service


QUIZ_PAYLOAD = {
    "title": "Session Quiz",
    "questions": [
        {
            "question_text": "Ready?",
            "choices": [
                {"choice_text": "Yes", "is_correct": True},
                {"choice_text": "No", "is_correct": False},
            ],
        }
    ],
}


@pytest.fixture
def session_client() -> Iterator[tuple[TestClient, dict[str, CurrentAccount]]]:
    app = create_app(
        Settings(
            database_url="sqlite://",
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
        )
    )
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.database.engine)
        accounts: dict[str, CurrentAccount] = {}
        with app.state.database.session_factory() as db:
            for name, role in [
                ("author", AccountRole.USER),
                ("participant", AccountRole.USER),
                ("other", AccountRole.USER),
                ("admin", AccountRole.ADMIN),
            ]:
                model = Account(
                    auth0_sub=f"test|{name}",
                    email=f"{name}@test.invalid",
                    display_name=name.title(),
                    account_type="ADMINISTRATOR" if role == AccountRole.ADMIN else None,
                )
                db.add(model)
                db.flush()
                accounts[name] = CurrentAccount(model.account_id, role, True)
            db.commit()

        app.dependency_overrides[get_active_account] = lambda: accounts["author"]
        yield client, accounts


def use_account(client: TestClient, account: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: account


def create_quiz(client: TestClient) -> dict:
    response = client.post("/quizzes", json=QUIZ_PAYLOAD)
    assert response.status_code == 201
    return response.json()


def create_session(client: TestClient, quiz_id: int) -> dict:
    response = client.post(f"/quizzes/{quiz_id}/sessions")
    assert response.status_code == 201
    return response.json()


def test_creator_can_open_lobby_for_saved_quiz(
    session_client: tuple[TestClient, dict[str, CurrentAccount]],
) -> None:
    client, accounts = session_client
    quiz = create_quiz(client)

    body = create_session(client, quiz["quiz_id"])

    assert body["quiz_id"] == quiz["quiz_id"]
    assert body["quiz_version_id"] == quiz["version"]["quiz_version_id"]
    assert body["host_id"] == accounts["author"].account_id
    assert body["status"] == "LOBBY"
    assert len(body["join_code"]) == 6
    assert body["join_code"].isdigit()
    assert body["current_question_order"] is None


def test_only_creator_can_host_even_when_requester_is_admin(
    session_client: tuple[TestClient, dict[str, CurrentAccount]],
) -> None:
    client, accounts = session_client
    quiz = create_quiz(client)
    use_account(client, accounts["admin"])

    response = client.post(f"/quizzes/{quiz['quiz_id']}/sessions")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "session_host_denied"


def test_archived_quiz_cannot_be_hosted(
    session_client: tuple[TestClient, dict[str, CurrentAccount]],
) -> None:
    client, _ = session_client
    quiz = create_quiz(client)
    assert client.patch(f"/quizzes/{quiz['quiz_id']}/archive").status_code == 200

    response = client.post(f"/quizzes/{quiz['quiz_id']}/sessions")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quiz_not_hostable"


def test_active_lobbies_never_share_a_join_code(
    session_client: tuple[TestClient, dict[str, CurrentAccount]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = session_client
    quiz = create_quiz(client)
    generated_codes = iter(["123456", "123456", "654321"])
    monkeypatch.setattr(
        session_service,
        "_generate_join_code",
        lambda: next(generated_codes),
    )

    first = create_session(client, quiz["quiz_id"])
    second = create_session(client, quiz["quiz_id"])

    assert first["join_code"] == "123456"
    assert second["join_code"] == "654321"


def test_user_can_join_with_trimmed_code_and_host_cannot_join(
    session_client: tuple[TestClient, dict[str, CurrentAccount]],
) -> None:
    client, accounts = session_client
    quiz = create_quiz(client)
    session = create_session(client, quiz["quiz_id"])

    host_attempt = client.post(
        "/sessions/join", json={"join_code": session["join_code"]}
    )
    assert host_attempt.status_code == 409
    assert host_attempt.json()["error"]["code"] == "host_cannot_join"

    use_account(client, accounts["participant"])
    joined = client.post(
        "/sessions/join",
        json={"join_code": f" {session['join_code']} "},
    )

    assert joined.status_code == 201
    assert joined.json()["session"]["session_id"] == session["session_id"]
    assert joined.json()["participant"]["display_name"] == "Participant"


def test_duplicate_and_invalid_joins_are_rejected(
    session_client: tuple[TestClient, dict[str, CurrentAccount]],
) -> None:
    client, accounts = session_client
    quiz = create_quiz(client)
    session = create_session(client, quiz["quiz_id"])
    use_account(client, accounts["participant"])
    payload = {"join_code": session["join_code"]}
    assert client.post("/sessions/join", json=payload).status_code == 201

    duplicate = client.post("/sessions/join", json=payload)
    missing_code = "000000" if session["join_code"] != "000000" else "000001"
    missing = client.post("/sessions/join", json={"join_code": missing_code})
    non_numeric = client.post("/sessions/join", json={"join_code": "ABC123"})

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "session_already_joined"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "join_code_not_found"
    assert non_numeric.status_code == 422


def test_late_join_is_allowed_but_completed_session_is_not_joinable(
    session_client: tuple[TestClient, dict[str, CurrentAccount]],
) -> None:
    client, accounts = session_client
    quiz = create_quiz(client)
    session = create_session(client, quiz["quiz_id"])
    with client.app.state.database.session_factory() as db:
        model = db.get(LiveSession, session["session_id"])
        model.status = LiveSessionStatus.ACTIVE
        db.commit()

    use_account(client, accounts["participant"])
    payload = {"join_code": session["join_code"]}
    assert client.post("/sessions/join", json=payload).status_code == 201

    with client.app.state.database.session_factory() as db:
        model = db.get(LiveSession, session["session_id"])
        model.status = LiveSessionStatus.COMPLETED
        db.commit()
    use_account(client, accounts["other"])

    response = client.post("/sessions/join", json=payload)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "join_code_not_found"


def test_host_and_admin_can_view_lobby_participants(
    session_client: tuple[TestClient, dict[str, CurrentAccount]],
) -> None:
    client, accounts = session_client
    quiz = create_quiz(client)
    session = create_session(client, quiz["quiz_id"])
    use_account(client, accounts["participant"])
    assert client.post(
        "/sessions/join", json={"join_code": session["join_code"]}
    ).status_code == 201

    denied = client.get(f"/sessions/{session['session_id']}/participants")
    assert denied.status_code == 403

    use_account(client, accounts["author"])
    host_view = client.get(f"/sessions/{session['session_id']}/participants")
    assert host_view.status_code == 200
    assert host_view.json()[0]["display_name"] == "Participant"

    use_account(client, accounts["admin"])
    admin_view = client.get(f"/sessions/{session['session_id']}/participants")
    assert admin_view.status_code == 200
    assert len(admin_view.json()) == 1


def test_session_detail_is_limited_to_host_participants_and_admin(
    session_client: tuple[TestClient, dict[str, CurrentAccount]],
) -> None:
    client, accounts = session_client
    quiz = create_quiz(client)
    session = create_session(client, quiz["quiz_id"])

    use_account(client, accounts["other"])
    assert client.get(f"/sessions/{session['session_id']}").status_code == 403

    use_account(client, accounts["participant"])
    assert client.post(
        "/sessions/join", json={"join_code": session["join_code"]}
    ).status_code == 201
    assert client.get(f"/sessions/{session['session_id']}").status_code == 200

    use_account(client, accounts["admin"])
    assert client.get(f"/sessions/{session['session_id']}").status_code == 200
