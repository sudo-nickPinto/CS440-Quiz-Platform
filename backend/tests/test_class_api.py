from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.auth import CurrentAccount, get_active_account, get_current_account
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
    JoinedVia,
    MembershipStatus,
)
from app.schemas.classes import ClassCreate
from app.services.classes import (
    CLASS_CODE_ALPHABET,
    create_class,
    generate_class_code,
)


@pytest.fixture
def class_client() -> Iterator[tuple[TestClient, dict[str, CurrentAccount]]]:
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
            account_models = {
                name: Account(
                    auth0_sub=f"test|classes-{name}",
                    email=f"classes-{name}@test.invalid",
                    display_name=name.replace("_", " ").title(),
                    account_type="ADMINISTRATOR" if name == "admin" else None,
                )
                for name in (
                    "creator",
                    "member",
                    "organizer",
                    "invited",
                    "left",
                    "removed",
                    "outsider",
                    "admin",
                )
            }
            db.add_all(account_models.values())
            db.commit()
            identities = {
                name: CurrentAccount(
                    account_id=model.account_id,
                    role=(
                        AccountRole.ADMIN if name == "admin" else AccountRole.USER
                    ),
                    is_active=True,
                )
                for name, model in account_models.items()
            }

        client.app.dependency_overrides[get_active_account] = lambda: identities[
            "creator"
        ]
        yield client, identities
        client.app.dependency_overrides.clear()


def act_as(client: TestClient, identity: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: identity


def seed_class(
    client: TestClient,
    creator: CurrentAccount,
    *,
    name: str = "Seed Class",
    join_code: str | None = "ABCDEFGH",
    joining_open: bool = True,
    archived: bool = False,
    memberships: tuple[
        tuple[CurrentAccount, ClassRole, MembershipStatus, JoinedVia], ...
    ] = (),
) -> int:
    with client.app.state.database.session_factory() as db:
        class_ = Class(
            name=name,
            created_by_id=creator.account_id,
            join_code=None if archived else join_code,
            joining_open=False if archived else joining_open,
            archived_at=(
                datetime.now(UTC).replace(tzinfo=None) if archived else None
            ),
        )
        db.add(class_)
        db.flush()
        db.add(
            ClassMembership(
                class_id=class_.class_id,
                account_id=creator.account_id,
                role=ClassRole.ORGANIZER,
                status=MembershipStatus.ACTIVE,
                joined_via=JoinedVia.CREATOR,
            )
        )
        db.add_all(
            ClassMembership(
                class_id=class_.class_id,
                account_id=account.account_id,
                role=role,
                status=status,
                joined_via=joined_via,
            )
            for account, role, status, joined_via in memberships
        )
        db.commit()
        return class_.class_id


def test_generated_code_uses_approved_alphabet_and_length() -> None:
    codes = {generate_class_code() for _ in range(50)}

    assert all(len(code) == 8 for code in codes)
    assert all(set(code) <= set(CLASS_CODE_ALPHABET) for code in codes)
    assert not (set("0O1IL") & set(CLASS_CODE_ALPHABET))


def test_active_user_creates_class_and_becomes_organizer(class_client) -> None:
    client, identities = class_client

    response = client.post("/classes", json={"name": "  CS 440  "})

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "CS 440"
    assert body["created_by_id"] == identities["creator"].account_id
    assert len(body["join_code"]) == 9
    assert body["join_code"][4] == "-"
    assert body["current_role"] == "ORGANIZER"
    assert body["membership_status"] == "ACTIVE"

    with client.app.state.database.session_factory() as db:
        stored = db.get(Class, body["class_id"])
        membership = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == body["class_id"],
                ClassMembership.account_id == identities["creator"].account_id,
            )
        )

    assert stored is not None
    assert stored.join_code == body["join_code"].replace("-", "")
    assert "-" not in stored.join_code
    assert membership is not None
    assert membership.role == ClassRole.ORGANIZER
    assert membership.status == MembershipStatus.ACTIVE
    assert membership.joined_via == JoinedVia.CREATOR


def test_class_creation_retries_an_existing_code(class_client) -> None:
    client, identities = class_client
    seed_class(client, identities["organizer"], join_code="ABCDEFGH")

    with patch(
        "app.services.classes.generate_class_code",
        side_effect=["ABCDEFGH", "JKMNPQRS"],
    ):
        response = client.post("/classes", json={"name": "Unique Code"})

    assert response.status_code == 201
    assert response.json()["join_code"] == "JKMN-PQRS"


def test_class_and_creator_membership_are_atomic() -> None:
    database = Database("sqlite://")
    Base.metadata.create_all(database.engine)
    with database.session_factory() as db:
        account = Account(
            auth0_sub="test|atomic-class",
            email="atomic-class@test.invalid",
            display_name="Atomic Creator",
        )
        db.add(account)
        db.commit()
        identity = CurrentAccount(account.account_id, AccountRole.USER, True)
        db.execute(
            text(
                "CREATE TRIGGER fail_class_membership_insert "
                "BEFORE INSERT ON class_membership "
                "BEGIN SELECT RAISE(FAIL, 'forced membership failure'); END"
            )
        )

        with pytest.raises(APIError) as error:
            create_class(db, identity, ClassCreate(name="Atomic Class"))

        assert error.value.status_code == 500
        assert error.value.code == "class_create_failed"
        assert db.scalar(select(func.count(Class.class_id))) == 0
        assert db.scalar(select(func.count(ClassMembership.membership_id))) == 0

    database.dispose()


def test_normal_list_includes_active_and_invited_but_not_inactive_memberships(
    class_client,
) -> None:
    client, identities = class_client
    target = identities["member"]
    memberships = {
        status: (
            target,
            ClassRole.MEMBER,
            status,
            JoinedVia.INVITE if status == MembershipStatus.INVITED else JoinedVia.CODE,
        )
        for status in MembershipStatus
    }
    class_ids = {
        status: seed_class(
            client,
            identities["organizer"],
            name=f"{status.value} Class",
            join_code=code,
            memberships=(memberships[status],),
        )
        for status, code in zip(
            MembershipStatus,
            ("ABCDEFGH", "JKMNPQRS", "TUVWXYZ2", "3456789A"),
            strict=True,
        )
    }
    act_as(client, target)

    response = client.get("/classes")

    assert response.status_code == 200
    assert [item["class_id"] for item in response.json()] == [
        class_ids[MembershipStatus.ACTIVE],
        class_ids[MembershipStatus.INVITED],
    ]
    by_status = {item["membership_status"]: item for item in response.json()}
    assert by_status["ACTIVE"]["current_role"] == "MEMBER"
    assert by_status["INVITED"]["current_role"] is None
    assert all(item["join_code"] is None for item in response.json())


def test_global_admin_lists_every_class_including_archived(class_client) -> None:
    client, identities = class_client
    first_id = seed_class(client, identities["organizer"], name="First")
    archived_id = seed_class(
        client,
        identities["organizer"],
        name="Archived",
        archived=True,
    )
    act_as(client, identities["admin"])

    response = client.get("/classes")

    assert response.status_code == 200
    assert [item["class_id"] for item in response.json()] == [archived_id, first_id]
    assert response.json()[0]["archived_at"] is not None
    assert all(item["current_role"] is None for item in response.json())
    assert all(item["membership_status"] is None for item in response.json())


def test_class_detail_hides_code_from_member_but_not_organizer_or_admin(
    class_client,
) -> None:
    client, identities = class_client
    class_id = seed_class(
        client,
        identities["organizer"],
        memberships=(
            (
                identities["member"],
                ClassRole.MEMBER,
                MembershipStatus.ACTIVE,
                JoinedVia.CODE,
            ),
        ),
    )

    act_as(client, identities["member"])
    member_response = client.get(f"/classes/{class_id}")
    act_as(client, identities["organizer"])
    organizer_response = client.get(f"/classes/{class_id}")
    act_as(client, identities["admin"])
    admin_response = client.get(f"/classes/{class_id}")

    assert member_response.status_code == 200
    assert member_response.json()["join_code"] is None
    assert organizer_response.json()["join_code"] == "ABCD-EFGH"
    assert admin_response.json()["join_code"] == "ABCD-EFGH"


@pytest.mark.parametrize(
    ("account_name", "status"),
    [
        ("invited", MembershipStatus.INVITED),
        ("left", MembershipStatus.LEFT),
        ("removed", MembershipStatus.REMOVED),
    ],
)
def test_outsider_and_nonactive_memberships_receive_hidden_404(
    class_client,
    account_name: str,
    status: MembershipStatus,
) -> None:
    client, identities = class_client
    class_id = seed_class(
        client,
        identities["organizer"],
        memberships=(
            (
                identities[account_name],
                ClassRole.MEMBER,
                status,
                JoinedVia.INVITE if status == MembershipStatus.INVITED else JoinedVia.CODE,
            ),
        ),
    )

    act_as(client, identities["outsider"])
    outsider = client.get(f"/classes/{class_id}")
    act_as(client, identities[account_name])
    inactive_membership = client.get(f"/classes/{class_id}")

    for response in (outsider, inactive_membership):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "class_not_found"


@pytest.mark.parametrize(
    ("account_name", "status"),
    [
        ("outsider", None),
        ("invited", MembershipStatus.INVITED),
        ("left", MembershipStatus.LEFT),
        ("removed", MembershipStatus.REMOVED),
    ],
)
def test_outsider_and_nonactive_memberships_cannot_mutate_class(
    class_client,
    account_name: str,
    status: MembershipStatus | None,
) -> None:
    client, identities = class_client
    memberships = (
        ()
        if status is None
        else (
            (
                identities[account_name],
                ClassRole.MEMBER,
                status,
                (
                    JoinedVia.INVITE
                    if status == MembershipStatus.INVITED
                    else JoinedVia.CODE
                ),
            ),
        )
    )
    class_id = seed_class(
        client,
        identities["organizer"],
        memberships=memberships,
    )
    act_as(client, identities[account_name])

    responses = (
        client.patch(f"/classes/{class_id}", json={"name": "Hidden"}),
        client.post(f"/classes/{class_id}/code"),
        client.post(f"/classes/{class_id}/archive"),
    )

    for response in responses:
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "class_not_found"


def test_member_cannot_rename_rotate_or_archive(class_client) -> None:
    client, identities = class_client
    class_id = seed_class(
        client,
        identities["organizer"],
        memberships=(
            (
                identities["member"],
                ClassRole.MEMBER,
                MembershipStatus.ACTIVE,
                JoinedVia.CODE,
            ),
        ),
    )
    act_as(client, identities["member"])

    responses = (
        client.patch(f"/classes/{class_id}", json={"name": "Denied"}),
        client.post(f"/classes/{class_id}/code"),
        client.post(f"/classes/{class_id}/archive"),
    )

    for response in responses:
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "not_class_organizer"


def test_organizer_and_global_admin_can_rename(class_client) -> None:
    client, identities = class_client
    class_id = seed_class(client, identities["organizer"])

    act_as(client, identities["organizer"])
    organizer_update = client.patch(
        f"/classes/{class_id}", json={"name": "Organizer Name"}
    )
    act_as(client, identities["admin"])
    admin_update = client.patch(f"/classes/{class_id}", json={"name": "Admin Name"})

    assert organizer_update.status_code == 200
    assert organizer_update.json()["name"] == "Organizer Name"
    assert admin_update.status_code == 200
    assert admin_update.json()["name"] == "Admin Name"


def test_global_admin_can_rotate_code_and_archive(class_client) -> None:
    client, identities = class_client
    class_id = seed_class(client, identities["organizer"])
    act_as(client, identities["admin"])

    with patch(
        "app.services.classes.generate_class_code",
        return_value="JKMNPQRS",
    ):
        rotated = client.post(f"/classes/{class_id}/code")
    archived = client.post(f"/classes/{class_id}/archive")

    assert rotated.status_code == 200
    assert rotated.json()["join_code"] == "JKMN-PQRS"
    assert rotated.json()["joining_open"] is True
    assert archived.status_code == 200
    assert archived.json()["archived_at"] is not None
    assert archived.json()["join_code"] is None
    assert archived.json()["joining_open"] is False


def test_joining_can_be_closed_and_reopened_when_not_archived(class_client) -> None:
    client, identities = class_client
    class_id = seed_class(client, identities["organizer"])
    act_as(client, identities["organizer"])

    closed = client.patch(f"/classes/{class_id}", json={"joining_open": False})
    reopened = client.patch(f"/classes/{class_id}", json={"joining_open": True})

    assert closed.status_code == 200
    assert closed.json()["joining_open"] is False
    assert reopened.status_code == 200
    assert reopened.json()["joining_open"] is True


def test_code_rotation_invalidates_old_code_and_reopens_joining(class_client) -> None:
    client, identities = class_client
    class_id = seed_class(
        client,
        identities["organizer"],
        joining_open=False,
    )
    act_as(client, identities["organizer"])

    with patch(
        "app.services.classes.generate_class_code",
        return_value="JKMNPQRS",
    ):
        response = client.post(f"/classes/{class_id}/code")

    assert response.status_code == 200
    assert response.json()["join_code"] == "JKMN-PQRS"
    assert response.json()["joining_open"] is True
    with client.app.state.database.session_factory() as db:
        assert db.scalar(select(Class).where(Class.join_code == "ABCDEFGH")) is None
        assert db.scalar(select(Class).where(Class.join_code == "JKMNPQRS")) is not None


def test_archive_is_idempotent_and_preserves_memberships(class_client) -> None:
    client, identities = class_client
    class_id = seed_class(
        client,
        identities["organizer"],
        memberships=(
            (
                identities["member"],
                ClassRole.MEMBER,
                MembershipStatus.ACTIVE,
                JoinedVia.CODE,
            ),
        ),
    )
    act_as(client, identities["organizer"])

    first = client.post(f"/classes/{class_id}/archive")
    second = client.post(f"/classes/{class_id}/archive")

    assert first.status_code == 200
    assert first.json()["archived_at"] is not None
    assert datetime.fromisoformat(first.json()["archived_at"]).microsecond % 1000 == 0
    assert first.json()["join_code"] is None
    assert first.json()["joining_open"] is False
    assert second.status_code == 200
    assert second.json()["archived_at"] == first.json()["archived_at"]
    with client.app.state.database.session_factory() as db:
        membership_count = db.scalar(
            select(func.count(ClassMembership.membership_id)).where(
                ClassMembership.class_id == class_id
            )
        )
    assert membership_count == 2


def test_archived_class_stays_readable_but_cannot_reopen_or_rotate(
    class_client,
) -> None:
    client, identities = class_client
    class_id = seed_class(
        client,
        identities["organizer"],
        archived=True,
        memberships=(
            (
                identities["member"],
                ClassRole.MEMBER,
                MembershipStatus.ACTIVE,
                JoinedVia.CODE,
            ),
        ),
    )

    act_as(client, identities["member"])
    readable = client.get(f"/classes/{class_id}")
    act_as(client, identities["organizer"])
    renamed = client.patch(f"/classes/{class_id}", json={"name": "History Fix"})
    reopened = client.patch(f"/classes/{class_id}", json={"joining_open": True})
    rotated = client.post(f"/classes/{class_id}/code")

    assert readable.status_code == 200
    assert readable.json()["archived_at"] is not None
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "History Fix"
    for response in (reopened, rotated):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "class_archived"


def test_class_code_generation_failure_is_stable_and_safe(class_client) -> None:
    client, identities = class_client
    seed_class(client, identities["organizer"], join_code="ABCDEFGH")

    with patch(
        "app.services.classes.generate_class_code",
        return_value="ABCDEFGH",
    ):
        response = client.post("/classes", json={"name": "No Available Code"})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "class_create_failed",
            "message": "Could not create the class.",
        }
    }
    with client.app.state.database.session_factory() as db:
        assert (
            db.scalar(select(Class).where(Class.name == "No Available Code")) is None
        )


def test_inactive_account_is_blocked_by_route_dependency(class_client) -> None:
    client, identities = class_client
    client.app.dependency_overrides.pop(get_active_account)
    client.app.dependency_overrides[get_current_account] = lambda: CurrentAccount(
        identities["creator"].account_id,
        AccountRole.USER,
        False,
    )

    response = client.post("/classes", json={"name": "Blocked"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "inactive_account"


def test_delete_class_endpoint_is_not_implemented(class_client) -> None:
    client, identities = class_client
    class_id = seed_class(client, identities["organizer"])

    response = client.delete(f"/classes/{class_id}")

    assert response.status_code == 405
