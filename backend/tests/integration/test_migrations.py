"""Run every migration up, down and up again on a throwaway MySQL database.

MySQL commits table changes immediately, so this can't share the normal
rollback-based test database. It creates `<test database>_migrations`, which
needs the CREATE and DROP DATABASE privileges, and always drops it at the end.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pymysql
import pytest
from pymysql.constants import CLIENT
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url

from app.models import Class, ClassMembership

MIGRATIONS = Path(__file__).resolve().parents[3] / "ulugbek-err" / "migrations"
UP_FILES = sorted(MIGRATIONS.glob("*.up.sql"))
DOWN_FILES = sorted(MIGRATIONS.glob("*.down.sql"), reverse=True)


@pytest.fixture
def scratch_database() -> Iterator[tuple[pymysql.Connection, str]]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run migration tests.")
    url = make_url(database_url)
    if not url.database or "test" not in url.database.lower():
        pytest.fail("TEST_DATABASE_URL database name must contain 'test'.")

    name = f"{url.database}_migrations"
    connection = pymysql.connect(
        host=url.host,
        port=url.port or 3306,
        user=url.username,
        password=url.password or "",
        charset="utf8mb4",
        client_flag=CLIENT.MULTI_STATEMENTS,
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
            cursor.execute(f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4")
            cursor.execute(f"USE `{name}`")
        yield connection, url.set(database=name).render_as_string(hide_password=False)
    finally:
        with connection.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
        connection.close()


def run_file(connection: pymysql.Connection, path: Path) -> None:
    with connection.cursor() as cursor:
        cursor.execute(path.read_text())
        while cursor.nextset():
            pass


def tables(connection: pymysql.Connection) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute("SHOW TABLES")
        return {row[0] for row in cursor.fetchall()}


def applied(connection: pymysql.Connection) -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT version FROM schema_migrations ORDER BY version")
        return [row[0] for row in cursor.fetchall()]


def test_every_migration_has_an_up_and_a_down_file() -> None:
    ups = {path.name.removesuffix(".up.sql") for path in UP_FILES}
    downs = {path.name.removesuffix(".down.sql") for path in DOWN_FILES}
    assert ups and ups == downs


def test_migrations_apply_revert_and_reapply(
    scratch_database: tuple[pymysql.Connection, str],
) -> None:
    connection, _ = scratch_database
    versions = [path.name.removesuffix(".up.sql") for path in UP_FILES]

    for path in UP_FILES:
        run_file(connection, path)
    assert applied(connection) == versions
    assert {"class", "class_membership"} <= tables(connection)

    for path in DOWN_FILES:
        run_file(connection, path)
    assert tables(connection) == set()

    for path in UP_FILES:
        run_file(connection, path)
    assert applied(connection) == versions


def test_migration_0006_down_only_removes_class_tables(
    scratch_database: tuple[pymysql.Connection, str],
) -> None:
    connection, _ = scratch_database
    for path in UP_FILES:
        run_file(connection, path)
    before = tables(connection)
    # Later migrations (0007: live_session.class_id) point at class, so they
    # come off first and go back on afterwards.
    later = [path for path in UP_FILES if path.name > "0006_classes.up.sql"]
    for path in reversed(later):
        run_file(connection, MIGRATIONS / path.name.replace(".up.", ".down."))

    run_file(connection, MIGRATIONS / "0006_classes.down.sql")
    assert tables(connection) == before - {"class", "class_membership"}
    assert "0006_classes" not in applied(connection)

    run_file(connection, MIGRATIONS / "0006_classes.up.sql")
    for path in later:
        run_file(connection, path)
    assert tables(connection) == before


def test_class_models_match_migrated_tables(
    scratch_database: tuple[pymysql.Connection, str],
) -> None:
    connection, database_url = scratch_database
    for path in UP_FILES:
        run_file(connection, path)

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        for model in (Class, ClassMembership):
            table = model.__table__
            columns = {
                column["name"]: column for column in inspector.get_columns(table.name)
            }
            assert list(columns) == list(table.c.keys())
            for column in table.c:
                assert columns[column.name]["nullable"] == column.nullable, column.name

            indexes = {
                index["name"]: index["column_names"]
                for index in inspector.get_indexes(table.name)
            }
            for index in table.indexes:
                assert indexes[index.name] == [c.name for c in index.columns]
            unique = {
                constraint["name"]: constraint["column_names"]
                for constraint in inspector.get_unique_constraints(table.name)
            }
            for constraint in table.constraints:
                if constraint.__class__.__name__ == "UniqueConstraint":
                    assert unique[constraint.name] == [
                        c.name for c in constraint.columns
                    ]
    finally:
        engine.dispose()
