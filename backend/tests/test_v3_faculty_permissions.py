from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.auth import CurrentAccount, get_current_account
from app.config import Settings
from app.database import Base, Database
from app.errors import APIError
from app.main import create_app
from app.models import (
    Account,
    AccountRole,
    Class,
    ClassMembership,
    ClassRole,
    MembershipStatus,
)
from app.schemas.classes import ClassCreate
from app.services.classes import create_class


@pytest.fixture
def context(tmp_path, caplog):
    database_url = f"sqlite:///{(tmp_path / 'faculty.sqlite').as_posix()}"
    database = Database(database_url)
    try:
        Base.metadata.create_all(database.engine)
    finally:
        database.dispose()

    app = create_app(
        Settings(
            database_url=database_url,
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
            live_abandon_after_seconds=0,
        )
    )

    with TestClient(app) as client:
        assert not any(
            record.name == "app.main"
            and record.getMessage() == "Startup sweep of open questions failed"
            for record in caplog.records
        )

        with app.state.database.session_factory() as db:
            models = {
                name: Account(
                    auth0_sub=f"test|v3-{name}",
                    email=f"{name}@test.invalid",
                    display_name=name,
                    account_type=(
                        "ADMINISTRATOR"
                        if name in {"faculty", "other_faculty"}
                        else None
                    ),
                    is_active=True,
                )
                for name in ("faculty", "other_faculty", "student")
            }
            db.add_all(models.values())
            db.commit()

            identities = {
                name: CurrentAccount(
                    model.account_id,
                    (
                        AccountRole.ADMIN
                        if model.account_type == "ADMINISTRATOR"
                        else AccountRole.USER
                    ),
                    True,
                )
                for name, model in models.items()
            }

        actor = {"value": identities["faculty"]}
        app.dependency_overrides[get_current_account] = lambda: actor["value"]

        yield client, identities, actor

        app.dependency_overrides.clear()


def create_test_class(client):
    response = client.post("/classes", json={"name": "V3 class"})
    assert response.status_code == 201, response.text
    return response.json()["class_id"]


def add_member(client, class_id, identity, *, role=ClassRole.MEMBER):
    with client.app.state.database.session_factory() as db:
        db.add(
            ClassMembership(
                class_id=class_id,
                account_id=identity.account_id,
                role=role,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code


def test_student_cannot_create_class(context):
    client, identities, actor = context
    actor["value"] = identities["student"]

    response = client.post("/classes", json={"name": "Not allowed"})

    assert_error(response, 403, "faculty_required")

    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Class)) == 0


def test_inactive_faculty_cannot_create_class(context):
    client, identities, actor = context
    actor["value"] = replace(identities["faculty"], is_active=False)

    response = client.post("/classes", json={"name": "Not allowed"})

    assert_error(response, 403, "inactive_account")


def test_faculty_creation_creates_active_organizer(context):
    client, identities, _ = context

    response = client.post("/classes", json={"name": "Faculty class"})
    assert response.status_code == 201
    body = response.json()
    assert body["current_role"] == "ORGANIZER"
    assert body["membership_status"] == "ACTIVE"
    assert body["join_code"]

    with client.app.state.database.session_factory() as db:
        membership = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == body["class_id"],
                ClassMembership.account_id == identities["faculty"].account_id,
            )
        )
        assert membership.role == ClassRole.ORGANIZER
        assert membership.status == MembershipStatus.ACTIVE


@pytest.mark.parametrize(
    "suffix",
    [
        "",
        "/members",
        "/invites",
        "/dashboard",
        "/students",
        "/sessions",
        "/active-sessions",
        "/grades/export.csv",
        "/sessions/999/results",
        "/quizzes/999/results",
        "/students/999/results",
    ],
)
def test_unrelated_faculty_cannot_read_class(context, suffix):
    client, identities, actor = context
    class_id = create_test_class(client)
    actor["value"] = identities["other_faculty"]

    response = client.get(f"/classes/{class_id}{suffix}")

    assert_error(response, 404, "class_not_found")


def test_unrelated_faculty_cannot_list_or_manage_class(context):
    client, identities, actor = context
    class_id = create_test_class(client)
    actor["value"] = identities["other_faculty"]

    assert client.get("/classes").json() == []

    assert_error(
        client.patch(f"/classes/{class_id}", json={"name": "Changed"}),
        404,
        "class_not_found",
    )
    assert_error(
        client.delete(
            f"/classes/{class_id}/members/{identities['faculty'].account_id}"
        ),
        404,
        "class_not_found",
    )


def test_faculty_member_does_not_gain_organizer_access(context):
    client, identities, actor = context
    class_id = create_test_class(client)
    add_member(client, class_id, identities["other_faculty"])
    actor["value"] = identities["other_faculty"]

    response = client.get(f"/classes/{class_id}")
    assert response.status_code == 200
    assert response.json()["current_role"] == "MEMBER"
    assert response.json()["join_code"] is None

    assert_error(
        client.patch(f"/classes/{class_id}", json={"name": "Changed"}),
        403,
        "not_class_organizer",
    )
    assert_error(
        client.get(f"/classes/{class_id}/grades/export.csv"),
        403,
        "not_class_organizer",
    )


def test_student_cannot_be_promoted(context):
    client, identities, _ = context
    class_id = create_test_class(client)
    add_member(client, class_id, identities["student"])

    response = client.patch(
        f"/classes/{class_id}/members/{identities['student'].account_id}",
        json={"role": "ORGANIZER"},
    )

    assert_error(response, 409, "organizer_requires_faculty")


def test_faculty_member_can_be_promoted(context):
    client, identities, actor = context
    class_id = create_test_class(client)
    add_member(client, class_id, identities["other_faculty"])

    response = client.patch(
        f"/classes/{class_id}/members/{identities['other_faculty'].account_id}",
        json={"role": "ORGANIZER"},
    )

    assert response.status_code == 200
    actor["value"] = identities["other_faculty"]
    assert (
        client.patch(
            f"/classes/{class_id}",
            json={"name": "Updated by co-organizer"},
        ).status_code
        == 200
    )


def test_legacy_student_organizer_cannot_manage(context):
    client, identities, actor = context
    class_id = create_test_class(client)
    add_member(
        client,
        class_id,
        identities["student"],
        role=ClassRole.ORGANIZER,
    )
    actor["value"] = identities["student"]

    assert_error(
        client.patch(f"/classes/{class_id}", json={"name": "Changed"}),
        403,
        "not_class_organizer",
    )
    assert_error(
        client.get(f"/classes/{class_id}/grades/export.csv"),
        403,
        "not_class_organizer",
    )


def test_inactive_faculty_cannot_be_promoted(context):
    client, identities, _ = context
    class_id = create_test_class(client)
    target = identities["other_faculty"]
    add_member(client, class_id, target)

    with client.app.state.database.session_factory() as db:
        db.get(Account, target.account_id).is_active = False
        db.commit()

    response = client.patch(
        f"/classes/{class_id}/members/{target.account_id}",
        json={"role": "ORGANIZER"},
    )

    assert_error(response, 409, "organizer_requires_faculty")


def test_last_usable_organizer_cannot_be_demoted(context):
    client, identities, _ = context
    class_id = create_test_class(client)

    # This legacy student role must not count as a usable backup organizer.
    add_member(
        client,
        class_id,
        identities["student"],
        role=ClassRole.ORGANIZER,
    )

    response = client.patch(
        f"/classes/{class_id}/members/{identities['faculty'].account_id}",
        json={"role": "MEMBER"},
    )

    assert_error(response, 409, "last_organizer")


def test_class_and_creator_membership_roll_back_together():
    database = Database("sqlite://")
    Base.metadata.create_all(database.engine)

    def fail_membership_insert(mapper, connection, target):
        raise SQLAlchemyError("Simulated membership insert failure")

    try:
        with database.session_factory() as db:
            faculty = Account(
                auth0_sub="test|atomic-faculty",
                email="atomic@test.invalid",
                display_name="Faculty",
                account_type="ADMINISTRATOR",
            )
            db.add(faculty)
            db.commit()

            actor = CurrentAccount(
                faculty.account_id,
                AccountRole.ADMIN,
                True,
            )

            event.listen(
                ClassMembership,
                "before_insert",
                fail_membership_insert,
            )

            try:
                with pytest.raises(APIError) as error:
                    create_class(db, actor, ClassCreate(name="Atomic class"))
                assert error.value.code == "class_create_failed"
            finally:
                event.remove(
                    ClassMembership,
                    "before_insert",
                    fail_membership_insert,
                )

            assert db.scalar(select(func.count()).select_from(Class)) == 0
            assert db.scalar(select(func.count()).select_from(ClassMembership)) == 0
    finally:
        database.dispose()
