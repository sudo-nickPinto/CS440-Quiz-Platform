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
from sqlalchemy.engine import URL, make_url

from app.models import (
    Class,
    ClassMembership,
    Quiz,
    QuizCollaborator,
    QuizCollaboratorEvent,
    QuizSubmission,
)

MIGRATIONS = Path(__file__).resolve().parents[3] / "ulugbek-err" / "migrations"
UP_FILES = sorted(MIGRATIONS.glob("*.up.sql"))
DOWN_FILES = sorted(MIGRATIONS.glob("*.down.sql"), reverse=True)


@pytest.fixture
def scratch_database() -> Iterator[tuple[pymysql.Connection, URL]]:
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
        # Passing a URL object keeps its password redacted in pytest failure output.
        yield connection, url.set(database=name)
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
    scratch_database: tuple[pymysql.Connection, URL],
) -> None:
    connection, _ = scratch_database
    versions = [path.name.removesuffix(".up.sql") for path in UP_FILES]

    for path in UP_FILES:
        run_file(connection, path)
    assert applied(connection) == versions
    assert {"class", "class_membership", "quiz_submission"} <= tables(connection)

    for path in DOWN_FILES:
        run_file(connection, path)
    assert tables(connection) == set()

    for path in UP_FILES:
        run_file(connection, path)
    assert applied(connection) == versions


def test_migration_0006_down_only_removes_class_tables(
    scratch_database: tuple[pymysql.Connection, URL],
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
    after_later_down = tables(connection)

    run_file(connection, MIGRATIONS / "0006_classes.down.sql")
    assert tables(connection) == after_later_down - {"class", "class_membership"}
    assert "0006_classes" not in applied(connection)

    run_file(connection, MIGRATIONS / "0006_classes.up.sql")
    for path in later:
        run_file(connection, path)
    assert tables(connection) == before


def test_models_match_migrated_tables(
    scratch_database: tuple[pymysql.Connection, URL],
) -> None:
    connection, database_url = scratch_database
    for path in UP_FILES:
        run_file(connection, path)

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        for model in (
            Class,
            ClassMembership,
            Quiz,
            QuizCollaborator,
            QuizCollaboratorEvent,
            QuizSubmission,
        ):
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


def test_migration_0010_generated_active_version_metadata(
    scratch_database: tuple[pymysql.Connection, URL],
) -> None:
    connection, database_url = scratch_database
    for path in UP_FILES:
        run_file(connection, path)

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        columns = {
            column["name"]: column
            for column in inspector.get_columns("quiz_submission")
        }
        computed = columns["active_version_id"]["computed"]
        normalized_sql = " ".join(computed["sqltext"].upper().split())
        assert computed["persisted"] is True
        assert "PENDING" in normalized_sql
        assert "APPROVED" in normalized_sql
        assert "QUIZ_VERSION_ID" in normalized_sql

        unique = {
            constraint["name"]: constraint["column_names"]
            for constraint in inspector.get_unique_constraints("quiz_submission")
        }
        assert unique["uq_quiz_submission_active"] == [
            "class_id",
            "active_version_id",
        ]

        indexes = {
            index["name"]: index["column_names"]
            for index in inspector.get_indexes("quiz_submission")
        }
        assert indexes["idx_quiz_submission_class_status_newest"] == [
            "class_id",
            "status",
            "submitted_at",
            "submission_id",
        ]
        assert indexes["idx_quiz_submission_member_newest"] == [
            "class_id",
            "submitted_by_id",
            "submitted_at",
            "submission_id",
        ]

        checks = {
            check["name"]: " ".join(check["sqltext"].upper().split())
            for check in inspector.get_check_constraints("quiz_submission")
        }
        decision_check = (
            checks["ck_quiz_submission_decision"]
            .replace("`", "")
            .replace("_UTF8MB4", "")
        )
        assert "STATUS = 'PENDING'" in decision_check
        assert "DECIDED_BY_ID IS NULL" in decision_check
        assert "DECIDED_BY_ID IS NOT NULL" in decision_check

        foreign_keys = {
            foreign_key["name"]: foreign_key
            for foreign_key in inspector.get_foreign_keys("quiz_submission")
        }
        assert set(foreign_keys) == {
            "fk_quiz_submission_class",
            "fk_quiz_submission_version",
            "fk_quiz_submission_submitted_by",
            "fk_quiz_submission_decided_by",
        }
        for foreign_key in foreign_keys.values():
            assert foreign_key["options"].get("ondelete") == "RESTRICT"
    finally:
        engine.dispose()


def quiz_classes(connection: pymysql.Connection) -> dict[int, int | None]:
    with connection.cursor() as cursor:
        cursor.execute("SELECT quiz_id, class_id FROM quiz ORDER BY quiz_id")
        return dict(cursor.fetchall())


def test_migration_0008_gives_quizzes_their_only_class(
    scratch_database: tuple[pymysql.Connection, URL],
) -> None:
    connection, _ = scratch_database
    for path in UP_FILES:
        if path.name < "0008":
            run_file(connection, path)

    # Quiz 1 was played only in class 1, quiz 2 in classes 1 and 2, quiz 3
    # only as an open session and quiz 4 never.
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO account (account_id, auth0_sub, email, display_name)
            VALUES (1, 'test|prof', 'prof@test.invalid', 'Prof');
            INSERT INTO class (class_id, name, created_by_id, join_code)
            VALUES (1, 'A', 1, 'AAAA0001'), (2, 'B', 1, 'BBBB0002');
            INSERT INTO quiz (quiz_id, author_id)
            VALUES (1, 1), (2, 1), (3, 1), (4, 1);
            INSERT INTO quiz_version (quiz_version_id, quiz_id, version_number, title)
            VALUES (1, 1, 1, 'One'), (2, 1, 2, 'One again'),
                   (3, 2, 1, 'Two'), (4, 3, 1, 'Three'), (5, 4, 1, 'Four');
            INSERT INTO live_session
                (quiz_version_id, host_id, class_id, join_code, status)
            VALUES (1, 1, 1, '100001', 'COMPLETED'),
                   (2, 1, 1, '100002', 'COMPLETED'),
                   (3, 1, 1, '100003', 'COMPLETED'),
                   (3, 1, 2, '100004', 'COMPLETED'),
                   (4, 1, NULL, '100005', 'COMPLETED');
            """
        )
        while cursor.nextset():
            pass

    run_file(connection, MIGRATIONS / "0008_quiz_class.up.sql")
    assert quiz_classes(connection) == {1: 1, 2: None, 3: None, 4: None}

    run_file(connection, MIGRATIONS / "0008_quiz_class.down.sql")
    with connection.cursor() as cursor:
        cursor.execute("SHOW COLUMNS FROM quiz LIKE 'class_id'")
        assert cursor.fetchall() == ()
    assert "0008_quiz_class" not in applied(connection)
