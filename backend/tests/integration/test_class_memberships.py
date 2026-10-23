from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import CurrentAccount, get_active_account
from app.models.account import Account, AccountRole
from app.models.classes import (
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    MembershipStatus,
)
from app.schemas.class_membership import ClassMemberUpdate
from app.services.class_memberships import remove_class_member, update_class_member


def test_class_membership_crud_uses_migrated_mysql_schema(
    mysql_quiz_client,
) -> None:
    client, class_admin, target = mysql_quiz_client
    with client.app.state.database.session_factory() as db:
        db: Session
        class_ = Class(
            name="MySQL Class",
            created_by_id=class_admin.account_id,
            join_code="MYSQL123",
        )
        db.add(class_)
        db.flush()
        db.add(
            ClassMembership(
                class_id=class_.class_id,
                account_id=class_admin.account_id,
                role=ClassRole.ORGANIZER,
            )
        )
        db.commit()
        class_id = class_.class_id

    invited = client.post(
        f"/classes/{class_id}/invites",
        json={"email": "READER@test.invalid"},
    )
    client.app.dependency_overrides[get_active_account] = lambda: CurrentAccount(
        target.account_id, AccountRole.USER, True
    )
    accepted = client.post(f"/classes/{class_id}/invite/accept")
    client.app.dependency_overrides[get_active_account] = lambda: CurrentAccount(
        class_admin.account_id, AccountRole.USER, True
    )
    promoted = client.patch(
        f"/classes/{class_id}/members/{target.account_id}",
        json={"role": "ORGANIZER"},
    )
    removed = client.delete(
        f"/classes/{class_id}/members/{target.account_id}"
    )
    reinvited = client.post(
        f"/classes/{class_id}/invites",
        json={"email": "reader@test.invalid"},
    )

    assert invited.status_code == 201
    assert invited.json()["status"] == "INVITED"
    assert accepted.status_code == 200
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "ORGANIZER"
    assert removed.status_code == 204
    assert reinvited.status_code == 201
    assert reinvited.json()["membership_id"] == invited.json()["membership_id"]
    assert reinvited.json()["status"] == "INVITED"
    with client.app.state.database.session_factory() as db:
        stored = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == target.account_id,
            )
        )
        assert stored is not None
        assert stored.joined_via == JoinedVia.INVITE


@pytest.mark.parametrize("operation", ["remove", "demote"])
def test_concurrent_admin_changes_are_serialized(mysql_quiz_client, operation) -> None:
    client, class_admin, target = mysql_quiz_client
    with client.app.state.database.session_factory() as db:
        third = Account(
            auth0_sub=f"test|third-{operation}",
            email=f"third-{operation}@test.invalid",
            display_name="Third Admin",
        )
        db.add(third)
        db.flush()
        class_ = Class(
            name=f"Concurrent {operation}",
            created_by_id=class_admin.account_id,
            join_code="REMOVE12" if operation == "remove" else "DEMOTE12",
        )
        db.add(class_)
        db.flush()
        db.add_all(
            ClassMembership(
                class_id=class_.class_id,
                account_id=account_id,
                role=ClassRole.ORGANIZER,
            )
            for account_id in (
                class_admin.account_id,
                target.account_id,
                third.account_id,
            )
        )
        db.commit()
        class_id = class_.class_id
        targets = (target.account_id, third.account_id)

    barrier = Barrier(2)
    global_admin = CurrentAccount(class_admin.account_id, AccountRole.ADMIN, True)

    def change_membership(account_id: int) -> None:
        with client.app.state.database.session_factory() as db:
            barrier.wait()
            if operation == "remove":
                remove_class_member(db, global_admin, class_id, account_id)
            else:
                update_class_member(
                    db,
                    global_admin,
                    class_id,
                    account_id,
                    ClassMemberUpdate(role=ClassRole.MEMBER),
                )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(change_membership, account_id) for account_id in targets]
        for future in futures:
            future.result(timeout=10)

    with client.app.state.database.session_factory() as db:
        active_admins = db.scalar(
            select(func.count(ClassMembership.membership_id)).where(
                ClassMembership.class_id == class_id,
                ClassMembership.status == MembershipStatus.ACTIVE,
                ClassMembership.role == ClassRole.ORGANIZER,
            )
        )
        assert active_admins == 1
