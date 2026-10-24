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
    ClassMembership,
    ClassRole,
    JoinedVia,
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
                    display_name=name.replace("_", " ").title(),
                    account_type=("ADMINISTRATOR" if name == "global_admin" else None),
                )
                for name, email in {
                    "organizer": "organizer@gettysburg.edu",
                    "other_organizer": "other-organizer@gettysburg.edu",
                    "member": "member@gettysburg.edu",
                    "target": "Student@GetTySburg.edu",
                    "global_admin": "global-admin@gettysburg.edu",
                }.items()
            }
            db.add_all(accounts.values())
            db.flush()
            class_ = Class(
                name="CS 440 Fall 2026",
                created_by_id=accounts["organizer"].account_id,
                join_code="ABCDEFGH",
            )
            db.add(class_)
            db.flush()
            db.add_all(
                [
                    ClassMembership(
                        class_id=class_.class_id,
                        account_id=accounts["organizer"].account_id,
                        role=ClassRole.ORGANIZER,
                        joined_via=JoinedVia.CREATOR,
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

        app.dependency_overrides[get_active_account] = lambda: identities["organizer"]
        yield client, identities, class_id


def act_as(client: TestClient, identity: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: identity


def invite_target(client: TestClient, class_id: int):
    return client.post(
        f"/classes/{class_id}/invites",
        json={"email": "  STUDENT@gettysburg.EDU "},
    )


def test_organizer_invites_existing_account_and_user_accepts(class_client) -> None:
    client, identities, class_id = class_client

    invited = invite_target(client, class_id)
    before_accept = client.get(f"/classes/{class_id}/members")
    act_as(client, identities["target"])
    accepted = client.post(f"/classes/{class_id}/invite/accept")
    act_as(client, identities["organizer"])
    after_accept = client.get(f"/classes/{class_id}/members")

    assert invited.status_code == 201
    assert invited.json()["email"] == "Student@GetTySburg.edu"
    assert invited.json()["role"] == "MEMBER"
    assert invited.json()["status"] == "INVITED"
    assert identities["target"].account_id not in {
        item["account_id"] for item in before_accept.json()
    }
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "ACTIVE"
    assert identities["target"].account_id in {
        item["account_id"] for item in after_accept.json()
    }

    with client.app.state.database.session_factory() as db:
        stored = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == identities["target"].account_id,
            )
        )
        assert stored is not None
        assert stored.joined_via == JoinedVia.INVITE
        assert stored.invited_by_id == identities["organizer"].account_id


def test_invite_requires_existing_account_and_rejects_duplicates(class_client) -> None:
    client, _, class_id = class_client

    missing = client.post(
        f"/classes/{class_id}/invites",
        json={"email": "missing@gettysburg.edu"},
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "account_not_found"

    assert invite_target(client, class_id).status_code == 201
    duplicate = invite_target(client, class_id)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "invite_already_exists"

    active = client.post(
        f"/classes/{class_id}/invites",
        json={"email": "member@gettysburg.edu"},
    )
    assert active.status_code == 409
    assert active.json()["error"]["code"] == "already_class_member"


@pytest.mark.parametrize("action", ["decline", "cancel"])
def test_declined_or_cancelled_invite_can_be_sent_again(class_client, action) -> None:
    client, identities, class_id = class_client
    target_id = identities["target"].account_id
    created = invite_target(client, class_id)
    membership_id = created.json()["membership_id"]

    if action == "decline":
        act_as(client, identities["target"])
        ended = client.post(f"/classes/{class_id}/invite/decline")
        expected_status = MembershipStatus.LEFT
        act_as(client, identities["organizer"])
    else:
        ended = client.delete(f"/classes/{class_id}/invites/{target_id}")
        expected_status = MembershipStatus.REMOVED

    assert ended.status_code == 204
    with client.app.state.database.session_factory() as db:
        stored = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == target_id,
            )
        )
        assert stored is not None
        assert stored.status == expected_status

    reinvited = invite_target(client, class_id)
    assert reinvited.status_code == 201
    assert reinvited.json()["membership_id"] == membership_id
    assert reinvited.json()["status"] == "INVITED"


def test_accept_decline_and_cancel_require_an_active_invite(class_client) -> None:
    client, identities, class_id = class_client

    act_as(client, identities["target"])
    accept = client.post(f"/classes/{class_id}/invite/accept")
    decline = client.post(f"/classes/{class_id}/invite/decline")
    act_as(client, identities["organizer"])
    cancel = client.delete(
        f"/classes/{class_id}/invites/{identities['target'].account_id}"
    )

    for response in (accept, decline, cancel):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "invite_not_found"


@pytest.mark.parametrize("action", ["accept", "decline"])
def test_invite_response_does_not_reveal_class_existence(
    class_client, action: str
) -> None:
    client, identities, class_id = class_client
    act_as(client, identities["target"])

    existing_class = client.post(f"/classes/{class_id}/invite/{action}")
    unknown_class = client.post(f"/classes/999999/invite/{action}")

    assert existing_class.status_code == unknown_class.status_code == 404
    assert existing_class.json() == unknown_class.json()
    assert existing_class.json()["error"]["code"] == "invite_not_found"


def test_organizer_can_promote_and_demote_other_organizers(class_client) -> None:
    client, identities, class_id = class_client
    target_id = identities["target"].account_id
    invite_target(client, class_id)
    act_as(client, identities["target"])
    client.post(f"/classes/{class_id}/invite/accept")
    act_as(client, identities["organizer"])

    promoted = client.patch(
        f"/classes/{class_id}/members/{target_id}",
        json={"role": "ORGANIZER"},
    )
    demoted = client.patch(
        f"/classes/{class_id}/members/{target_id}",
        json={"role": "MEMBER"},
    )

    assert promoted.status_code == 200
    assert promoted.json()["role"] == "ORGANIZER"
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "MEMBER"


@pytest.mark.parametrize("operation", ["demote", "remove"])
def test_last_active_organizer_is_protected(class_client, operation: str) -> None:
    client, identities, class_id = class_client
    organizer_id = identities["organizer"].account_id

    if operation == "demote":
        response = client.patch(
            f"/classes/{class_id}/members/{organizer_id}",
            json={"role": "MEMBER"},
        )
    else:
        response = client.delete(f"/classes/{class_id}/members/{organizer_id}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_organizer"


def test_one_organizer_can_remove_another_when_one_remains(class_client) -> None:
    client, identities, class_id = class_client
    other_id = identities["other_organizer"].account_id
    with client.app.state.database.session_factory() as db:
        db.add(
            ClassMembership(
                class_id=class_id,
                account_id=other_id,
                role=ClassRole.ORGANIZER,
                status=MembershipStatus.ACTIVE,
                joined_via=JoinedVia.INVITE,
            )
        )
        db.commit()

    removed = client.delete(f"/classes/{class_id}/members/{other_id}")
    assert removed.status_code == 204


def test_ordinary_member_cannot_read_or_modify_roster(class_client) -> None:
    client, identities, class_id = class_client
    act_as(client, identities["member"])

    responses = [
        client.get(f"/classes/{class_id}/members"),
        invite_target(client, class_id),
        client.patch(
            f"/classes/{class_id}/members/{identities['organizer'].account_id}",
            json={"role": "MEMBER"},
        ),
        client.delete(
            f"/classes/{class_id}/members/{identities['organizer'].account_id}"
        ),
    ]

    assert all(response.status_code == 403 for response in responses)
    assert all(
        response.json()["error"]["code"] == "not_class_organizer"
        for response in responses
    )


def test_outsider_and_removed_member_cannot_discover_class(class_client) -> None:
    client, identities, class_id = class_client

    act_as(client, identities["target"])
    outsider = client.get(f"/classes/{class_id}/members")

    act_as(client, identities["organizer"])
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

    invited = invite_target(client, class_id)
    listing = client.get(f"/classes/{class_id}/members")

    assert invited.status_code == 201
    assert listing.status_code == 200


def test_unknown_member_and_invalid_role_errors(class_client) -> None:
    client, identities, class_id = class_client

    unknown_class = client.get("/classes/999999/members")
    unknown_member = client.patch(
        f"/classes/{class_id}/members/999999", json={"role": "MEMBER"}
    )
    invalid_role = client.patch(
        f"/classes/{class_id}/members/{identities['member'].account_id}",
        json={"role": "PROFESSOR"},
    )

    assert unknown_class.status_code == 404
    assert unknown_class.json()["error"]["code"] == "class_not_found"
    assert unknown_member.status_code == 404
    assert unknown_member.json()["error"]["code"] == "class_member_not_found"
    assert invalid_role.status_code == 422
