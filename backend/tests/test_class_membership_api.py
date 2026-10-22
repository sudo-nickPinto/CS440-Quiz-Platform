from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.classes import (
    Class,
    ClassRole,
    ClassMembership,
    MembershipStatus,
)


@pytest.fixture
def class_client() -> Iterator[tuple[TestClient, dict[str, CurrentAccount], int]]:
    app = create_app(
        Settings(
            database_url="sqlite://",
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
        )
    )
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.database.engine)
        with app.state.database.session_factory() as db:
            accounts = {
                name: Account(
                    auth0_sub=f"auth0|{name}",
                    email=email,
                    display_name=name.title(),
                    account_type=("ADMINISTRATOR" if name == "global_admin" else None),
                )
                for name, email in {
                    "class_admin": "admin@gettysburg.edu",
                    "other_admin": "other-admin@gettysburg.edu",
                    "member": "member@gettysburg.edu",
                    "target": "Student@GetTySburg.edu",
                    "global_admin": "global-admin@gettysburg.edu",
                }.items()
            }
            db.add_all(accounts.values())
            db.flush()
            class_ = Class(
                name="CS 440 Fall 2026",
                created_by_id=accounts["class_admin"].account_id,
                join_code="ABCDEFGH",
            )
            db.add(class_)
            db.flush()
            db.add_all(
                [
                    ClassMembership(
                        class_id=class_.class_id,
                        account_id=accounts["class_admin"].account_id,
                        role=ClassRole.ORGANIZER,
                    ),
                    ClassMembership(
                        class_id=class_.class_id,
                        account_id=accounts["member"].account_id,
                        role=ClassRole.MEMBER,
                    ),
                ]
            )
            db.commit()
            class_id = class_.class_id
            identities = {
                name: CurrentAccount(
                    model.account_id,
                    AccountRole.ADMIN if name == "global_admin" else AccountRole.USER,
                    True,
                )
                for name, model in accounts.items()
            }

        app.dependency_overrides[get_active_account] = lambda: identities["class_admin"]
        yield client, identities, class_id


def act_as(client: TestClient, identity: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: identity


def add_target(client: TestClient, class_id: int, role: str = "MEMBER"):
    return client.post(
        f"/classes/{class_id}/members",
        json={"email": "  STUDENT@gettysburg.EDU ", "role": role},
    )


def test_class_admin_can_add_list_and_get_existing_account(class_client) -> None:
    client, identities, class_id = class_client

    created = add_target(client, class_id)
    listing = client.get(f"/classes/{class_id}/members")
    detail = client.get(
        f"/classes/{class_id}/members/{identities['target'].account_id}"
    )

    assert created.status_code == 201
    assert created.json()["email"] == "Student@GetTySburg.edu"
    assert created.json()["role"] == "MEMBER"
    assert created.json()["status"] == "ACTIVE"
    assert listing.status_code == 200
    assert {item["account_id"] for item in listing.json()} == {
        identities["class_admin"].account_id,
        identities["member"].account_id,
        identities["target"].account_id,
    }
    assert detail.status_code == 200
    assert detail.json()["account_id"] == identities["target"].account_id


def test_add_requires_an_existing_account_and_prevents_duplicates(class_client) -> None:
    client, _, class_id = class_client

    missing = client.post(
        f"/classes/{class_id}/members",
        json={"email": "missing@gettysburg.edu", "role": "MEMBER"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "account_not_found"

    assert add_target(client, class_id).status_code == 201
    duplicate = add_target(client, class_id)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "class_membership_exists"


def test_removed_membership_is_soft_deleted_and_can_be_reactivated(class_client) -> None:
    client, identities, class_id = class_client
    target_id = identities["target"].account_id
    created = add_target(client, class_id)
    membership_id = created.json()["membership_id"]

    removed = client.delete(f"/classes/{class_id}/members/{target_id}")
    assert removed.status_code == 204

    with client.app.state.database.session_factory() as db:
        stored = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == target_id,
            )
        )
        assert stored is not None
        assert stored.membership_id == membership_id
        assert stored.status == MembershipStatus.REMOVED

    assert target_id not in {
        item["account_id"]
        for item in client.get(f"/classes/{class_id}/members").json()
    }
    reactivated = add_target(client, class_id, "CLASS_ADMIN")
    assert reactivated.status_code == 201
    assert reactivated.json()["membership_id"] == membership_id
    assert reactivated.json()["status"] == "ACTIVE"
    assert reactivated.json()["role"] == "CLASS_ADMIN"


def test_class_admin_can_promote_and_demote_other_admins(class_client) -> None:
    client, identities, class_id = class_client
    target_id = identities["target"].account_id
    add_target(client, class_id)

    promoted = client.patch(
        f"/classes/{class_id}/members/{target_id}",
        json={"role": "CLASS_ADMIN"},
    )
    demoted = client.patch(
        f"/classes/{class_id}/members/{target_id}",
        json={"role": "MEMBER"},
    )

    assert promoted.status_code == 200
    assert promoted.json()["role"] == "CLASS_ADMIN"
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "MEMBER"


@pytest.mark.parametrize("operation", ["demote", "remove"])
def test_final_active_class_admin_is_protected(class_client, operation: str) -> None:
    client, identities, class_id = class_client
    admin_id = identities["class_admin"].account_id

    if operation == "demote":
        response = client.patch(
            f"/classes/{class_id}/members/{admin_id}",
            json={"role": "MEMBER"},
        )
    else:
        response = client.delete(f"/classes/{class_id}/members/{admin_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "final_class_admin"


def test_one_admin_can_remove_another_when_one_will_remain(class_client) -> None:
    client, identities, class_id = class_client
    other_id = identities["other_admin"].account_id
    response = client.post(
        f"/classes/{class_id}/members",
        json={
            "email": "other-admin@gettysburg.edu",
            "role": "CLASS_ADMIN",
        },
    )
    assert response.status_code == 201

    removed = client.delete(f"/classes/{class_id}/members/{other_id}")
    assert removed.status_code == 204


def test_ordinary_member_cannot_read_or_modify_roster(class_client) -> None:
    client, identities, class_id = class_client
    act_as(client, identities["member"])

    responses = [
        client.get(f"/classes/{class_id}/members"),
        add_target(client, class_id),
        client.patch(
            f"/classes/{class_id}/members/{identities['class_admin'].account_id}",
            json={"role": "MEMBER"},
        ),
        client.delete(
            f"/classes/{class_id}/members/{identities['class_admin'].account_id}"
        ),
    ]

    assert all(response.status_code == 403 for response in responses)
    assert all(
        response.json()["error"]["code"] == "class_roster_access_denied"
        for response in responses
    )


def test_outsider_and_removed_member_cannot_discover_class(class_client) -> None:
    client, identities, class_id = class_client

    act_as(client, identities["target"])
    outsider = client.get(f"/classes/{class_id}/members")

    act_as(client, identities["class_admin"])
    removed = client.delete(
        f"/classes/{class_id}/members/{identities['member'].account_id}"
    )
    act_as(client, identities["member"])
    former_member = client.get(f"/classes/{class_id}/members")
    unknown = client.get("/classes/999999/members")

    assert removed.status_code == 204
    assert outsider.status_code == former_member.status_code == unknown.status_code == 404
    assert outsider.json() == former_member.json() == unknown.json()
    assert outsider.json()["error"]["code"] == "class_not_found"


def test_global_admin_can_manage_any_class_roster(class_client) -> None:
    client, identities, class_id = class_client
    act_as(client, identities["global_admin"])

    created = add_target(client, class_id)
    listing = client.get(f"/classes/{class_id}/members")

    assert created.status_code == 201
    assert listing.status_code == 200


def test_unknown_class_member_and_invalid_role_errors(class_client) -> None:
    client, identities, class_id = class_client

    unknown_class = client.get("/classes/999999/members")
    unknown_member = client.get(f"/classes/{class_id}/members/999999")
    invalid_role = client.patch(
        f"/classes/{class_id}/members/{identities['member'].account_id}",
        json={"role": "PROFESSOR"},
    )

    assert unknown_class.status_code == 404
    assert unknown_class.json()["error"]["code"] == "class_not_found"
    assert unknown_member.status_code == 404
    assert unknown_member.json()["error"]["code"] == "class_member_not_found"
    assert invalid_role.status_code == 422
