from app.models import Class, ClassMembership, ClassRole, JoinedVia, MembershipStatus


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


def test_class_table_matches_migration_0006() -> None:
    table = Class.__table__

    assert table.name == "class"
    assert list(table.c.keys()) == [
        "class_id",
        "name",
        "created_by_id",
        "join_code",
        "joining_open",
        "archived_at",
        "created_at",
        "updated_at",
    ]
    assert constraint_columns(table, "uq_class_join_code") == ["join_code"]
    assert table.c.join_code.nullable
    assert not table.c.created_by_id.nullable
    assert foreign_key(table, "created_by_id").target_fullname == "account.account_id"
    assert foreign_key(table, "created_by_id").ondelete == "RESTRICT"


def test_class_membership_table_matches_migration_0006() -> None:
    table = ClassMembership.__table__

    assert table.name == "class_membership"
    assert constraint_columns(table, "uq_class_membership") == [
        "class_id",
        "account_id",
    ]
    assert index_columns(table, "idx_class_membership_account") == [
        "account_id",
        "status",
    ]
    assert index_columns(table, "idx_class_membership_roster") == [
        "class_id",
        "status",
        "role",
    ]
    assert foreign_key(table, "class_id").ondelete == "RESTRICT"
    assert foreign_key(table, "account_id").ondelete == "RESTRICT"
    assert foreign_key(table, "invited_by_id").ondelete == "SET NULL"
    assert foreign_key(table, "decided_by_id").ondelete == "SET NULL"


def test_membership_enums_match_migration_0006() -> None:
    assert [role.value for role in ClassRole] == ["ORGANIZER", "MEMBER"]
    assert [status.value for status in MembershipStatus] == [
        "INVITED",
        "ACTIVE",
        "LEFT",
        "REMOVED",
    ]
    assert [via.value for via in JoinedVia] == ["CREATOR", "CODE", "INVITE"]


def test_new_membership_defaults_to_active_member_joined_by_code() -> None:
    table = ClassMembership.__table__

    assert table.c.role.server_default.arg == "MEMBER"
    assert table.c.status.server_default.arg == "ACTIVE"
    assert table.c.joined_via.server_default.arg == "CODE"
