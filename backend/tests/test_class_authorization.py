from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.database import Base, Database
from app.errors import APIError
from app.models import (
    Account,
    AccountRole,
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    MembershipStatus,
)
from app.services.class_authorization import (
    get_class,
    require_class_member,
    require_class_organizer,
)


@pytest.fixture
def authorization_context() -> Iterator[tuple[Session, dict[str, CurrentAccount], int, int]]:
    database = Database("sqlite://")
    Base.metadata.create_all(database.engine)

    with database.session_factory() as db:
        account_models = {
            name: Account(
                auth0_sub=f"test|class-authorization-{name}",
                email=f"class-authorization-{name}@test.invalid",
                display_name=name.replace("_", " ").title(),
                account_type="ADMINISTRATOR" if name == "admin" else None,
            )
            for name in (
                "outsider",
                "invited",
                "left",
                "removed",
                "member",
                "organizer",
                "admin",
            )
        }
        db.add_all(account_models.values())
        db.flush()

        class_ = Class(
            name="Authorization 101",
            created_by_id=account_models["organizer"].account_id,
            join_code="K7RMQ4XP",
        )
        archived_class = Class(
            name="Authorization History",
            created_by_id=account_models["organizer"].account_id,
            join_code=None,
            joining_open=False,
            archived_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add_all([class_, archived_class])
        db.flush()

        memberships = [
            ClassMembership(
                class_id=class_.class_id,
                account_id=account_models["invited"].account_id,
                status=MembershipStatus.INVITED,
                joined_via=JoinedVia.INVITE,
            ),
            ClassMembership(
                class_id=class_.class_id,
                account_id=account_models["left"].account_id,
                status=MembershipStatus.LEFT,
            ),
            ClassMembership(
                class_id=class_.class_id,
                account_id=account_models["removed"].account_id,
                status=MembershipStatus.REMOVED,
            ),
            ClassMembership(
                class_id=class_.class_id,
                account_id=account_models["member"].account_id,
            ),
            ClassMembership(
                class_id=class_.class_id,
                account_id=account_models["organizer"].account_id,
                role=ClassRole.ORGANIZER,
                joined_via=JoinedVia.CREATOR,
            ),
            ClassMembership(
                class_id=archived_class.class_id,
                account_id=account_models["member"].account_id,
            ),
        ]
        db.add_all(memberships)
        db.commit()

        accounts = {
            name: CurrentAccount(
                account_id=model.account_id,
                role=AccountRole.ADMIN if name == "admin" else AccountRole.USER,
                is_active=True,
            )
            for name, model in account_models.items()
        }
        yield db, accounts, class_.class_id, archived_class.class_id

    database.dispose()


def assert_api_error(
    expected_status: int,
    expected_code: str,
    action,
) -> None:
    with pytest.raises(APIError) as error:
        action()

    assert error.value.status_code == expected_status
    assert error.value.code == expected_code


def test_missing_class_returns_class_not_found(authorization_context) -> None:
    db, _, _, _ = authorization_context

    assert_api_error(404, "class_not_found", lambda: get_class(db, 999_999))


def test_outsider_receives_hidden_class_not_found(authorization_context) -> None:
    db, accounts, class_id, _ = authorization_context

    for authorization_check in (require_class_member, require_class_organizer):
        assert_api_error(
            404,
            "class_not_found",
            lambda: authorization_check(db, accounts["outsider"], class_id),
        )


@pytest.mark.parametrize("account_name", ["invited", "left", "removed"])
def test_inactive_membership_receives_hidden_class_not_found(
    authorization_context,
    account_name: str,
) -> None:
    db, accounts, class_id, _ = authorization_context

    for authorization_check in (require_class_member, require_class_organizer):
        assert_api_error(
            404,
            "class_not_found",
            lambda: authorization_check(db, accounts[account_name], class_id),
        )


def test_active_member_passes_member_check(authorization_context) -> None:
    db, accounts, class_id, _ = authorization_context

    access = require_class_member(db, accounts["member"], class_id)

    assert access.class_.class_id == class_id
    assert access.membership is not None
    assert access.membership.status == MembershipStatus.ACTIVE
    assert access.membership.role == ClassRole.MEMBER
    assert access.is_global_admin is False


def test_active_organizer_passes_member_and_organizer_checks(
    authorization_context,
) -> None:
    db, accounts, class_id, _ = authorization_context

    member_access = require_class_member(db, accounts["organizer"], class_id)
    organizer_access = require_class_organizer(db, accounts["organizer"], class_id)

    assert member_access.membership is not None
    assert member_access.membership.role == ClassRole.ORGANIZER
    assert organizer_access.membership is not None
    assert organizer_access.membership.role == ClassRole.ORGANIZER


def test_active_member_is_not_class_organizer(authorization_context) -> None:
    db, accounts, class_id, _ = authorization_context

    assert_api_error(
        403,
        "not_class_organizer",
        lambda: require_class_organizer(db, accounts["member"], class_id),
    )


def test_global_admin_bypasses_member_and_organizer_checks(
    authorization_context,
) -> None:
    db, accounts, class_id, _ = authorization_context

    member_access = require_class_member(db, accounts["admin"], class_id)
    organizer_access = require_class_organizer(db, accounts["admin"], class_id)

    assert member_access.class_.class_id == class_id
    assert member_access.membership is None
    assert member_access.is_global_admin is True
    assert organizer_access.class_.class_id == class_id
    assert organizer_access.membership is None
    assert organizer_access.is_global_admin is True


def test_archived_class_remains_readable_to_active_member_and_global_admin(
    authorization_context,
) -> None:
    db, accounts, _, archived_class_id = authorization_context

    member_access = require_class_member(
        db, accounts["member"], archived_class_id
    )
    admin_access = require_class_member(db, accounts["admin"], archived_class_id)

    assert member_access.class_.archived_at is not None
    assert member_access.membership is not None
    assert member_access.membership.status == MembershipStatus.ACTIVE
    assert admin_access.class_.archived_at is not None
    assert admin_access.is_global_admin is True
