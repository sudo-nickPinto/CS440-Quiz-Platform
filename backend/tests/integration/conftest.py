import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_current_account
from app.config import Settings
from app.database import get_db
from app.main import create_app
from app.models import Account, AccountType


@pytest.fixture
def mysql_connection() -> Generator[Connection, None, None]:
    """Open a rollback-only connection to an explicitly configured test database."""
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run MySQL integration tests.")

    url = make_url(database_url)
    if url.drivername != "mysql+pymysql":
        pytest.fail("TEST_DATABASE_URL must use the mysql+pymysql driver.")
    if not url.database or "test" not in url.database.lower():
        pytest.fail("TEST_DATABASE_URL must point to a dedicated test database.")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            applied = set(
                connection.execute(text("SELECT version FROM schema_migrations")).scalars()
            )
            required = {"0001_accounts_and_groups", "0002_quizzes"}
            if not required.issubset(applied):
                pytest.fail("Apply migrations 0001 and 0002 to the test database first.")
            yield connection
        finally:
            transaction.rollback()
    engine.dispose()


@pytest.fixture
def mysql_session(mysql_connection: Connection) -> Generator[Session, None, None]:
    with Session(bind=mysql_connection, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def current_account(mysql_session: Session) -> CurrentAccount:
    account = Account(
        auth0_sub="test|quiz-api-account",
        email="quiz-api-account@example.test",
        display_name="Quiz API test",
        account_type=AccountType.STUDENT,
    )
    mysql_session.add(account)
    mysql_session.flush()
    return CurrentAccount(account.account_id, AccountType.STUDENT)


@pytest.fixture
def mysql_client(
    mysql_session: Session, current_account: CurrentAccount
) -> Generator[TestClient, None, None]:
    database_url = os.environ["TEST_DATABASE_URL"]
    app = create_app(Settings(database_url=database_url))

    def override_db() -> Generator[Session, None, None]:
        yield mysql_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_account] = lambda: current_account
    with TestClient(app) as client:
        yield client
