from datetime import datetime

from fastapi.testclient import TestClient

from app.api.routes import responses as response_routes
from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import get_db
from app.main import create_app
from app.models import AccountRole
from app.schemas.response import ResponseReceipt


def test_response_route_passes_validated_identity_and_answer_to_service(
    monkeypatch,
) -> None:
    account = CurrentAccount(7, AccountRole.USER, True)
    database_marker = object()
    captured: dict[str, object] = {}

    def fake_submit(db, current_account, session_id, session_question_id, payload):
        captured.update(
            db=db,
            account=current_account,
            session_id=session_id,
            session_question_id=session_question_id,
            choice_id=payload.choice_id,
        )
        return ResponseReceipt(
            response_id=50,
            session_question_id=session_question_id,
            choice_id=payload.choice_id,
            submitted_at=datetime(2026, 10, 4, 12, 0, 2),
        )

    monkeypatch.setattr(response_routes, "submit_response", fake_submit)
    app = create_app(Settings(database_url="sqlite://"))
    app.dependency_overrides[get_db] = lambda: database_marker
    app.dependency_overrides[get_active_account] = lambda: account

    with TestClient(app) as client:
        response = client.post(
            "/sessions/20/questions/10/responses",
            json={"choice_id": 40},
        )

    assert response.status_code == 201
    assert response.json() == {
        "response_id": 50,
        "session_question_id": 10,
        "choice_id": 40,
        "submitted_at": "2026-10-04T12:00:02",
    }
    assert captured == {
        "db": database_marker,
        "account": account,
        "session_id": 20,
        "session_question_id": 10,
        "choice_id": 40,
    }


def test_response_route_rejects_client_supplied_scoring_fields() -> None:
    app = create_app(Settings(database_url="sqlite://"))
    app.dependency_overrides[get_db] = lambda: object()
    app.dependency_overrides[get_active_account] = lambda: CurrentAccount(
        7, AccountRole.USER, True
    )

    with TestClient(app) as client:
        response = client.post(
            "/sessions/20/questions/10/responses",
            json={"choice_id": 40, "points_awarded": 1000},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
