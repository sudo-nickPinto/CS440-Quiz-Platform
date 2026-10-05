import os
from collections.abc import Generator

import pytest
from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


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
