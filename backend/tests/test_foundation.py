from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_client() -> TestClient:
    return TestClient(
        create_app(
            Settings(
                database_url="sqlite://",
                cors_origins=["http://localhost:5173"],
            )
        )
    )


def test_root_identifies_api():
    with make_client() as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Quiz Platform API"}


def test_health_checks_database_connection():
    with make_client() as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "components": {"database": "ok"}}


def test_health_standardizes_database_failure():
    app = create_app(Settings(database_url="sqlite:////missing/directory/quiz.db"))
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "database_unavailable",
            "message": "The API is running, but the database is unavailable.",
        }
    }


def test_missing_route_uses_standard_error_shape():
    with make_client() as client:
        response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "http_error", "message": "Not Found"}
    }
