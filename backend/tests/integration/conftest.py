import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.main import create_app
from app.models.account import AccountRole


@pytest.fixture
def mysql_quiz_client() -> Iterator[tuple[TestClient, CurrentAccount, CurrentAccount]]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run migrated MySQL integration tests.")

    parsed_url = make_url(database_url)
    if not parsed_url.drivername.startswith("mysql"):
        pytest.fail("TEST_DATABASE_URL must use MySQL.")
    if not parsed_url.database or "test" not in parsed_url.database.lower():
        pytest.fail("TEST_DATABASE_URL database name must contain 'test'.")

    app = create_app(
        Settings(
            database_url=database_url,
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
        )
    )
    with TestClient(app) as client:
        cleanup_database(app)
        with app.state.database.engine.begin() as connection:
            author_id = connection.execute(
                text(
                    "INSERT INTO account "
                    "(auth0_sub, email, display_name, is_active) "
                    "VALUES ('test|author', 'author@test.invalid', 'Author', TRUE)"
                )
            ).lastrowid
            reader_id = connection.execute(
                text(
                    "INSERT INTO account "
                    "(auth0_sub, email, display_name, is_active) "
                    "VALUES ('test|reader', 'reader@test.invalid', 'Reader', TRUE)"
                )
            ).lastrowid

        author = CurrentAccount(author_id, AccountRole.USER, True)
        reader = CurrentAccount(reader_id, AccountRole.USER, True)
        app.dependency_overrides[get_active_account] = lambda: author
        yield client, author, reader
        app.dependency_overrides.clear()
        cleanup_database(app)


def cleanup_database(app) -> None:
    # Child-first order respects every foreign key in migrations 0001-0005.
    tables = [
        "result",
        "response",
        "session_question",
        "session_participant",
        "live_session",
        "answer_choice",
        "question",
        "quiz_version",
        "quiz_collaborator",
        "quiz_group",
        "quiz",
        "group_membership",
        "course_group",
        "account_identity",
        "account",
    ]
    with app.state.database.engine.begin() as connection:
        for table in tables:
            connection.execute(text(f"DELETE FROM {table}"))
