from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.models.account import Account, AccountRole
from app.models.classes import (
    Class,
    ClassMembership,
    ClassRole,
    MembershipStatus,
)
from app.schemas.class_membership import ClassMemberRole, ClassMemberUpdate
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

    created = client.post(
        f"/classes/{class_id}/members",
        json={"email": "READER@test.invalid", "role": "MEMBER"},
    )
    promoted = client.patch(
        f"/classes/{class_id}/members/{target.account_id}",
        json={"role": "CLASS_ADMIN"},
    )
    removed = client.delete(
        f"/classes/{class_id}/members/{target.account_id}"
    )
    reactivated = client.post(
        f"/classes/{class_id}/members",
        json={"email": "reader@test.invalid", "role": "MEMBER"},
    )

    assert created.status_code == 201
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "CLASS_ADMIN"
    assert removed.status_code == 204
    assert reactivated.status_code == 201
    assert reactivated.json()["membership_id"] == created.json()["membership_id"]
    assert reactivated.json()["role"] == "MEMBER"


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
                    ClassMemberUpdate(role=ClassMemberRole.MEMBER),
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
