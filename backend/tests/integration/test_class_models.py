import os
from collections.abc import Iterator
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DataError, IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models import (
    Account,
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    MembershipStatus,
)


@pytest.fixture
def class_engine() -> Iterator[Engine]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to run migrated MySQL integration tests.")
    url = make_url(database_url)
    if not url.database or "test" not in url.database.lower():
        pytest.fail("TEST_DATABASE_URL database name must contain 'test'.")

    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as connection:
        applied = set(
            connection.execute(text("SELECT version FROM schema_migrations")).scalars()
        )
    if "0006_classes" not in applied:
        engine.dispose()
        pytest.fail("Apply migration 0006_classes to the test database first.")
    yield engine
    engine.dispose()


@pytest.fixture
def db(class_engine: Engine) -> Iterator[Session]:
    """A session whose classes and accounts are deleted after the test."""
    tag = uuid4().hex[:12]
    session = Session(class_engine, expire_on_commit=False)
    session.info["tag"] = tag
    try:
        yield session
    finally:
        session.rollback()
        accounts = select(Account.account_id).where(Account.email.like(f"%{tag}%"))
        account_ids = list(session.scalars(accounts))
        class_ids = list(
            session.scalars(select(Class.class_id).where(Class.name.like(f"%{tag}%")))
        )
        session.execute(
            delete(ClassMembership).where(ClassMembership.class_id.in_(class_ids))
        )
        session.execute(delete(Class).where(Class.class_id.in_(class_ids)))
        session.execute(delete(Account).where(Account.account_id.in_(account_ids)))
        session.commit()
        session.close()


def make_account(db: Session, name: str) -> Account:
    tag = db.info["tag"]
    account = Account(
        auth0_sub=f"test|{name}-{tag}",
        email=f"{name}-{tag}@class-test.invalid",
        display_name=name,
    )
    db.add(account)
    db.flush()
    return account


def make_class(db: Session, creator: Account, code: str | None = None) -> Class:
    tag = db.info["tag"]
    course = Class(
        name=f"CS 440 {tag}",
        created_by_id=creator.account_id,
        join_code=code or tag[:8].upper(),
    )
    db.add(course)
    db.flush()
    return course


def test_class_and_memberships_round_trip(db: Session) -> None:
    organizer = make_account(db, "organizer")
    student = make_account(db, "student")
    course = make_class(db, organizer)
    db.add_all(
        [
            ClassMembership(
                class_id=course.class_id,
                account_id=organizer.account_id,
                role=ClassRole.ORGANIZER,
                joined_via=JoinedVia.CREATOR,
            ),
            ClassMembership(class_id=course.class_id, account_id=student.account_id),
        ]
    )
    db.commit()
    db.expire_all()

    stored = db.get(Class, course.class_id)
    assert stored.joining_open is True
    assert stored.archived_at is None
    assert stored.created_at is not None and stored.updated_at is not None

    by_account = {m.account_id: m for m in stored.memberships}
    assert by_account[organizer.account_id].role == ClassRole.ORGANIZER
    assert by_account[organizer.account_id].joined_via == JoinedVia.CREATOR
    # A membership with nothing set is an active member who joined by code.
    assert by_account[student.account_id].role == ClassRole.MEMBER
    assert by_account[student.account_id].status == MembershipStatus.ACTIVE
    assert by_account[student.account_id].joined_via == JoinedVia.CODE


def test_person_can_only_have_one_membership_per_class(db: Session) -> None:
    organizer = make_account(db, "organizer")
    course = make_class(db, organizer)
    db.add(ClassMembership(class_id=course.class_id, account_id=organizer.account_id))
    db.commit()

    db.add(
        ClassMembership(
            class_id=course.class_id,
            account_id=organizer.account_id,
            status=MembershipStatus.INVITED,
        )
    )
    with pytest.raises(IntegrityError, match="uq_class_membership"):
        db.commit()


def test_removed_membership_is_reactivated_in_place(db: Session) -> None:
    organizer = make_account(db, "organizer")
    student = make_account(db, "student")
    course = make_class(db, organizer)
    membership = ClassMembership(
        class_id=course.class_id, account_id=student.account_id
    )
    db.add(membership)
    db.commit()
    membership_id = membership.membership_id

    membership.status = MembershipStatus.REMOVED
    membership.decided_by_id = organizer.account_id
    membership.decided_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    membership.status = MembershipStatus.ACTIVE
    db.commit()
    db.expire_all()

    rows = db.scalars(
        select(ClassMembership).where(ClassMembership.class_id == course.class_id)
    ).all()
    assert [(row.membership_id, row.status) for row in rows] == [
        (membership_id, MembershipStatus.ACTIVE)
    ]


def test_class_codes_are_unique(db: Session) -> None:
    organizer = make_account(db, "organizer")
    first = make_class(db, organizer, code="K7RMQ4XP")
    db.commit()

    db.add(
        Class(
            name=f"Other {db.info['tag']}",
            created_by_id=organizer.account_id,
            join_code=first.join_code,
        )
    )
    with pytest.raises(IntegrityError, match="uq_class_join_code"):
        db.commit()


def test_many_classes_can_have_no_code(db: Session) -> None:
    organizer = make_account(db, "organizer")
    for number in range(2):
        db.add(
            Class(
                name=f"No code {number} {db.info['tag']}",
                created_by_id=organizer.account_id,
                join_code=None,
            )
        )
    db.commit()


def test_archived_class_must_have_no_code_and_closed_joining(db: Session) -> None:
    organizer = make_account(db, "organizer")
    course = make_class(db, organizer)
    db.commit()

    course.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    with pytest.raises(OperationalError, match="ck_class_archived_closed"):
        db.commit()
    db.rollback()

    course.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
    course.join_code = None
    course.joining_open = False
    db.commit()


def test_class_with_members_cannot_be_deleted(db: Session) -> None:
    organizer = make_account(db, "organizer")
    course = make_class(db, organizer)
    db.add(ClassMembership(class_id=course.class_id, account_id=organizer.account_id))
    db.commit()

    with pytest.raises(IntegrityError, match="fk_class_membership_class"):
        db.execute(delete(Class).where(Class.class_id == course.class_id))


def test_deleting_inviter_keeps_membership_and_clears_inviter(db: Session) -> None:
    organizer = make_account(db, "organizer")
    inviter = make_account(db, "inviter")
    student = make_account(db, "student")
    course = make_class(db, organizer)
    membership = ClassMembership(
        class_id=course.class_id,
        account_id=student.account_id,
        status=MembershipStatus.INVITED,
        joined_via=JoinedVia.INVITE,
        invited_by_id=inviter.account_id,
        decided_by_id=inviter.account_id,
    )
    db.add(membership)
    db.commit()

    db.execute(delete(Account).where(Account.account_id == inviter.account_id))
    db.commit()
    db.expire_all()

    stored = db.get(ClassMembership, membership.membership_id)
    assert stored.invited_by_id is None
    assert stored.decided_by_id is None
    assert stored.status == MembershipStatus.INVITED


def test_unknown_status_is_rejected(db: Session) -> None:
    organizer = make_account(db, "organizer")
    course = make_class(db, organizer)
    db.commit()

    with pytest.raises(DataError, match="status"):
        db.execute(
            text(
                "INSERT INTO class_membership (class_id, account_id, status) "
                "VALUES (:class_id, :account_id, 'PENDING')"
            ),
            {"class_id": course.class_id, "account_id": organizer.account_id},
        )
