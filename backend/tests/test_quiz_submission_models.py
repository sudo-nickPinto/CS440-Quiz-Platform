from sqlalchemy import CheckConstraint

from app.models import QuizSubmission, SubmissionStatus


def constraint_columns(table, name: str) -> list[str]:
    for constraint in table.constraints:
        if constraint.name == name:
            return [column.name for column in constraint.columns]
    raise AssertionError(f"{table.name} has no constraint {name}")


def index_columns(table, name: str) -> list[str]:
    for index in table.indexes:
        if index.name == name:
            return [column.name for column in index.columns]
    raise AssertionError(f"{table.name} has no index {name}")


def foreign_key(table, column: str):
    (fk,) = table.c[column].foreign_keys
    return fk


def test_submission_status_values_match_migration_0010() -> None:
    assert [status.value for status in SubmissionStatus] == [
        "PENDING",
        "APPROVED",
        "REJECTED",
        "WITHDRAWN",
    ]


def test_quiz_submission_table_matches_migration_0010() -> None:
    table = QuizSubmission.__table__

    assert table.name == "quiz_submission"
    assert list(table.c.keys()) == [
        "submission_id",
        "class_id",
        "quiz_version_id",
        "submitted_by_id",
        "status",
        "decided_by_id",
        "submitted_at",
        "decided_at",
        "active_version_id",
    ]
    assert table.c.status.server_default.arg == SubmissionStatus.PENDING.value
    for column in (
        "class_id",
        "quiz_version_id",
        "submitted_by_id",
        "decided_by_id",
    ):
        assert foreign_key(table, column).ondelete == "RESTRICT"

    checks = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    decision_check = checks["ck_quiz_submission_decision"]
    assert "status = 'PENDING'" in decision_check
    assert "decided_by_id IS NULL" in decision_check
    assert "decided_by_id IS NOT NULL" in decision_check


def test_active_version_is_private_stored_generated_uniqueness_metadata() -> None:
    table = QuizSubmission.__table__
    column = table.c.active_version_id

    assert not hasattr(QuizSubmission, "active_version_id")
    assert hasattr(QuizSubmission, "_active_version_id")
    assert column.computed is not None
    assert column.computed.persisted is True
    expression = str(column.computed.sqltext)
    assert "PENDING" in expression
    assert "APPROVED" in expression
    assert "quiz_version_id" in expression
    assert constraint_columns(table, "uq_quiz_submission_active") == [
        "class_id",
        "active_version_id",
    ]


def test_submission_listing_indexes_match_migration_0010() -> None:
    table = QuizSubmission.__table__

    assert index_columns(table, "idx_quiz_submission_class_status_newest") == [
        "class_id",
        "status",
        "submitted_at",
        "submission_id",
    ]
    assert index_columns(table, "idx_quiz_submission_member_newest") == [
        "class_id",
        "submitted_by_id",
        "submitted_at",
        "submission_id",
    ]
