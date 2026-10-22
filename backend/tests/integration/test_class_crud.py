import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.main import create_app
from app.models import (
    Account,
    AccountRole,
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    MembershipStatus,
)
from app.services.classes import CLASS_CODE_ALPHABET

ACCOUNT_PREFIX = "test|class-crud-integration-"
TRIGGER_NAME = "trg_test_class_crud_membership_failure"


def _approved_database_url() -> str:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run migrated MySQL integration tests.")

    parsed_url = make_url(database_url)
    if not parsed_url.drivername.startswith("mysql"):
        pytest.fail("TEST_DATABASE_URL must use MySQL.")
    database_name = parsed_url.database or ""
    if database_name.lower() == "f26_cs440_quizdb":
        pytest.fail("The shared course database must never be used for tests.")
    if "test" not in database_name.lower():
        pytest.fail("TEST_DATABASE_URL database name must contain 'test'.")
    return database_url


def _require_migration_0006(app) -> None:
    try:
        with app.state.database.engine.connect() as connection:
            applied = connection.scalar(
                text(
                    "SELECT COUNT(*) FROM schema_migrations "
                    "WHERE version = '0006_classes'"
                )
            )
    except SQLAlchemyError:
        pytest.fail(
            "The approved test database must have migrations through 0006_classes."
        )
    if applied != 1:
        pytest.fail(
            "The approved test database must have migrations through 0006_classes."
        )


def _cleanup_class_crud_rows(app) -> None:
    prefix = f"{ACCOUNT_PREFIX}%"
    with app.state.database.engine.begin() as connection:
        connection.execute(text(f"DROP TRIGGER IF EXISTS {TRIGGER_NAME}"))
        connection.execute(
            text(
                "DELETE cm FROM class_membership AS cm "
                "INNER JOIN `class` AS c ON c.class_id = cm.class_id "
                "INNER JOIN account AS creator "
                "ON creator.account_id = c.created_by_id "
                "WHERE creator.auth0_sub LIKE :prefix"
            ),
            {"prefix": prefix},
        )
        connection.execute(
            text(
                "DELETE cm FROM class_membership AS cm "
                "INNER JOIN account AS member "
                "ON member.account_id = cm.account_id "
                "WHERE member.auth0_sub LIKE :prefix"
            ),
            {"prefix": prefix},
        )
        connection.execute(
            text(
                "DELETE c FROM `class` AS c "
                "INNER JOIN account AS creator "
                "ON creator.account_id = c.created_by_id "
                "WHERE creator.auth0_sub LIKE :prefix"
            ),
            {"prefix": prefix},
        )
        connection.execute(
            text(
                "DELETE ai FROM account_identity AS ai "
                "INNER JOIN account AS a ON a.account_id = ai.account_id "
                "WHERE a.auth0_sub LIKE :prefix"
            ),
            {"prefix": prefix},
        )
        connection.execute(
            text("DELETE FROM account WHERE auth0_sub LIKE :prefix"),
            {"prefix": prefix},
        )


def _seed_accounts(app) -> dict[str, CurrentAccount]:
    with app.state.database.session_factory() as db:
        account_models = {
            name: Account(
                auth0_sub=f"{ACCOUNT_PREFIX}{name}",
                email=f"class-crud-integration-{name}@test.invalid",
                display_name=name.replace("_", " ").title(),
                account_type="ADMINISTRATOR" if name == "admin" else None,
            )
            for name in (
                "creator",
                "member",
                "invited",
                "left",
                "removed",
                "outsider",
                "admin",
            )
        }
        db.add_all(account_models.values())
        db.commit()
        return {
            name: CurrentAccount(
                account_id=model.account_id,
                role=AccountRole.ADMIN if name == "admin" else AccountRole.USER,
                is_active=True,
            )
            for name, model in account_models.items()
        }


@pytest.fixture
def mysql_class_client() -> Iterator[tuple[TestClient, dict[str, CurrentAccount]]]:
    database_url = _approved_database_url()
    app = create_app(
        Settings(
            database_url=database_url,
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
        )
    )
    with TestClient(app) as client:
        _require_migration_0006(app)
        _cleanup_class_crud_rows(app)
        accounts = _seed_accounts(app)
        client.app.dependency_overrides[get_active_account] = lambda: accounts[
            "creator"
        ]
        try:
            yield client, accounts
        finally:
            client.app.dependency_overrides.clear()
            _cleanup_class_crud_rows(app)


def _act_as(client: TestClient, account: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: account


def _create_class(client: TestClient, name: str = "MySQL Class") -> dict:
    response = client.post("/classes", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_mysql_class_creation_is_atomic_and_codes_are_unique(
    mysql_class_client,
) -> None:
    client, accounts = mysql_class_client

    body = _create_class(client)
    stored_code = body["join_code"].replace("-", "")

    assert len(stored_code) == 8
    assert set(stored_code) <= set(CLASS_CODE_ALPHABET)
    assert body["join_code"] == f"{stored_code[:4]}-{stored_code[4:]}"
    with client.app.state.database.session_factory() as db:
        classes = db.scalars(
            select(Class).where(
                Class.class_id == body["class_id"],
                Class.created_by_id == accounts["creator"].account_id,
            )
        ).all()
        memberships = db.scalars(
            select(ClassMembership).where(
                ClassMembership.class_id == body["class_id"],
                ClassMembership.account_id == accounts["creator"].account_id,
            )
        ).all()
        assert len(classes) == 1
        assert len(memberships) == 1
        assert classes[0].join_code == stored_code
        assert memberships[0].account_id == accounts["creator"].account_id
        assert memberships[0].role == ClassRole.ORGANIZER
        assert memberships[0].status == MembershipStatus.ACTIVE
        assert memberships[0].joined_via == JoinedVia.CREATOR

    with pytest.raises(IntegrityError):
        with client.app.state.database.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO `class` (name, created_by_id, join_code) "
                    "VALUES (:name, :created_by_id, :join_code)"
                ),
                {
                    "name": "Duplicate Code",
                    "created_by_id": accounts["creator"].account_id,
                    "join_code": stored_code,
                },
            )

    retry_code = "ABCDEFGH" if stored_code != "ABCDEFGH" else "JKMNPQRS"
    with patch(
        "app.services.classes.generate_class_code",
        side_effect=[stored_code, retry_code],
    ):
        retried = client.post("/classes", json={"name": "Retried Code"})

    assert retried.status_code == 201
    assert retried.json()["join_code"] == f"{retry_code[:4]}-{retry_code[4:]}"


def test_mysql_membership_failure_rolls_back_class_and_removes_trigger(
    mysql_class_client,
) -> None:
    client, accounts = mysql_class_client
    engine = client.app.state.database.engine
    try:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER IF EXISTS {TRIGGER_NAME}"))
            connection.execute(
                text(
                    f"CREATE TRIGGER {TRIGGER_NAME} "
                    "BEFORE INSERT ON class_membership FOR EACH ROW "
                    "SIGNAL SQLSTATE '45000' "
                    "SET MESSAGE_TEXT = 'forced class membership failure'"
                )
            )

        response = client.post("/classes", json={"name": "Rollback Class"})
    finally:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TRIGGER IF EXISTS {TRIGGER_NAME}"))

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "class_create_failed",
            "message": "Could not create the class.",
        }
    }
    with client.app.state.database.session_factory() as db:
        rollback_classes = select(Class.class_id).where(
            Class.name == "Rollback Class",
            Class.created_by_id == accounts["creator"].account_id,
        )
        assert db.scalar(select(func.count()).select_from(rollback_classes.subquery())) == 0
        assert (
            db.scalar(
                select(func.count(ClassMembership.membership_id))
                .join(Class, Class.class_id == ClassMembership.class_id)
                .where(
                    Class.name == "Rollback Class",
                    Class.created_by_id == accounts["creator"].account_id,
                    ClassMembership.account_id == accounts["creator"].account_id,
                )
            )
            == 0
        )
    with engine.connect() as connection:
        trigger_count = connection.scalar(
            text(
                "SELECT COUNT(*) FROM information_schema.TRIGGERS "
                "WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME = :name"
            ),
            {"name": TRIGGER_NAME},
        )
    assert trigger_count == 0


def test_mysql_visibility_authorization_rotation_and_archive(
    mysql_class_client,
) -> None:
    client, accounts = mysql_class_client
    body = _create_class(client, "Authorization Class")
    class_id = body["class_id"]
    old_code = body["join_code"].replace("-", "")
    with client.app.state.database.session_factory() as db:
        db.add_all(
            [
                ClassMembership(
                    class_id=class_id,
                    account_id=accounts[name].account_id,
                    role=ClassRole.MEMBER,
                    status=status,
                    joined_via=(
                        JoinedVia.INVITE
                        if status == MembershipStatus.INVITED
                        else JoinedVia.CODE
                    ),
                )
                for name, status in (
                    ("member", MembershipStatus.ACTIVE),
                    ("invited", MembershipStatus.INVITED),
                    ("left", MembershipStatus.LEFT),
                    ("removed", MembershipStatus.REMOVED),
                )
            ]
        )
        db.commit()

    for name in ("member", "invited"):
        _act_as(client, accounts[name])
        listing = client.get("/classes")
        assert listing.status_code == 200
        assert [item["class_id"] for item in listing.json()] == [class_id]
        assert listing.json()[0]["join_code"] is None
    for name in ("left", "removed", "outsider"):
        _act_as(client, accounts[name])
        assert client.get("/classes").json() == []

    _act_as(client, accounts["member"])
    member_detail = client.get(f"/classes/{class_id}")
    member_mutation = client.patch(
        f"/classes/{class_id}", json={"name": "Denied"}
    )
    assert member_detail.status_code == 200
    assert member_detail.json()["join_code"] is None
    assert member_mutation.status_code == 403
    assert member_mutation.json()["error"]["code"] == "not_class_organizer"

    for name in ("invited", "left", "removed", "outsider"):
        _act_as(client, accounts[name])
        hidden = client.get(f"/classes/{class_id}")
        assert hidden.status_code == 404
        assert hidden.json()["error"]["code"] == "class_not_found"

    _act_as(client, accounts["creator"])
    organizer_detail = client.get(f"/classes/{class_id}")
    assert organizer_detail.json()["join_code"] == body["join_code"]

    _act_as(client, accounts["admin"])
    admin_detail = client.get(f"/classes/{class_id}")
    assert admin_detail.status_code == 200
    assert admin_detail.json()["join_code"] == body["join_code"]
    renamed_and_closed = client.patch(
        f"/classes/{class_id}",
        json={"name": "Admin Renamed", "joining_open": False},
    )
    assert renamed_and_closed.status_code == 200
    assert renamed_and_closed.json()["joining_open"] is False

    new_code = "ABCDEFGH" if old_code != "ABCDEFGH" else "JKMNPQRS"
    with patch("app.services.classes.generate_class_code", return_value=new_code):
        rotated = client.post(f"/classes/{class_id}/code")
    assert rotated.status_code == 200
    assert rotated.json()["join_code"] == f"{new_code[:4]}-{new_code[4:]}"
    assert rotated.json()["joining_open"] is True
    with client.app.state.database.session_factory() as db:
        stored = db.get(Class, class_id)
        assert stored is not None
        assert stored.join_code == new_code
        assert stored.joining_open is True
        assert db.scalar(select(Class).where(Class.join_code == old_code)) is None

    _act_as(client, accounts["member"])
    assert client.get(f"/classes/{class_id}").json()["join_code"] is None

    _act_as(client, accounts["admin"])
    first_archive = client.post(f"/classes/{class_id}/archive")
    second_archive = client.post(f"/classes/{class_id}/archive")
    assert first_archive.status_code == 200
    assert first_archive.json()["archived_at"] is not None
    assert first_archive.json()["joining_open"] is False
    assert first_archive.json()["join_code"] is None
    assert second_archive.status_code == 200
    assert second_archive.json()["archived_at"] == first_archive.json()["archived_at"]

    with client.app.state.database.session_factory() as db:
        archived = db.get(Class, class_id)
        assert archived is not None
        assert archived.archived_at is not None
        assert archived.joining_open is False
        assert archived.join_code is None
        assert (
            db.scalar(
                select(func.count(ClassMembership.membership_id)).where(
                    ClassMembership.class_id == class_id
                )
            )
            == 5
        )

    _act_as(client, accounts["member"])
    historical = client.get(f"/classes/{class_id}")
    assert historical.status_code == 200
    assert historical.json()["archived_at"] is not None

    _act_as(client, accounts["admin"])
    reopen = client.patch(f"/classes/{class_id}", json={"joining_open": True})
    reissue = client.post(f"/classes/{class_id}/code")
    for response in (reopen, reissue):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "class_archived"
