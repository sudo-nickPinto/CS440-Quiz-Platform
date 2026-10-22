"""Dummy class data for trying class-aware live sessions (task 6) locally.

Creates one demo class with you as ORGANIZER, two ACTIVE members, one REMOVED
member and one outsider, then prints the DEV_QUIZ_CLASS_MAP line that puts
your published quizzes in that class. Safe to run more than once.

    cd backend
    python -m scripts.seed_class_demo --organizer-email you@gettysburg.edu

Local only: it refuses to run unless APP_ENV is development and the database
is on localhost, so it can never touch the shared cray database. Delete it when
task 3 (create/join classes) and task 5 (quiz.class_id) are merged.
"""

import argparse
import secrets
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Account,
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    MembershipStatus,
    Quiz,
    QuizStatus,
)

CLASS_NAME = "Demo class (task 6)"
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
DEMO_PEOPLE = [
    # auth0_sub, display name, membership status (None = not in the class)
    ("demo|member-1", "Demo Member One", MembershipStatus.ACTIVE),
    ("demo|member-2", "Demo Member Two", MembershipStatus.ACTIVE),
    ("demo|removed", "Demo Removed Member", MembershipStatus.REMOVED),
    ("demo|outsider", "Demo Outsider", None),
]


def _local_url() -> URL:
    settings = get_settings()
    url = make_url(settings.sqlalchemy_url)
    if settings.app_env != "development" or url.host not in ("127.0.0.1", "localhost"):
        sys.exit("Refusing: only runs with APP_ENV=development on a localhost database.")
    return url


def _account(db: Session, sub: str, name: str) -> Account:
    account = db.scalar(select(Account).where(Account.auth0_sub == sub))
    if account is None:
        email = sub.replace("|", "-") + "@demo.invalid"
        account = Account(auth0_sub=sub, email=email, display_name=name, is_active=True)
        db.add(account)
        db.flush()
    return account


def _membership(
    db: Session,
    class_id: int,
    account_id: int,
    role: ClassRole,
    status: MembershipStatus,
    via: JoinedVia,
) -> None:
    row = db.scalar(
        select(ClassMembership).where(
            ClassMembership.class_id == class_id,
            ClassMembership.account_id == account_id,
        )
    )
    if row is None:
        row = ClassMembership(class_id=class_id, account_id=account_id, joined_via=via)
        db.add(row)
    row.role = role
    row.status = status


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--organizer-email", required=True)
    args = parser.parse_args()

    engine = create_engine(_local_url())
    with Session(engine) as db:
        organizer = db.scalar(select(Account).where(Account.email == args.organizer_email))
        if organizer is None:
            sys.exit("No account with that email. Sign in to the app once first.")

        class_ = db.scalar(
            select(Class).where(
                Class.name == CLASS_NAME, Class.created_by_id == organizer.account_id
            )
        )
        if class_ is None:
            class_ = Class(
                name=CLASS_NAME,
                created_by_id=organizer.account_id,
                join_code="".join(secrets.choice(CODE_ALPHABET) for _ in range(8)),
            )
            db.add(class_)
            db.flush()
        _membership(
            db,
            class_.class_id,
            organizer.account_id,
            ClassRole.ORGANIZER,
            MembershipStatus.ACTIVE,
            JoinedVia.CREATOR,
        )

        people = []
        for sub, name, status in DEMO_PEOPLE:
            account = _account(db, sub, name)
            if status is not None:
                _membership(
                    db,
                    class_.class_id,
                    account.account_id,
                    ClassRole.MEMBER,
                    status,
                    JoinedVia.CODE,
                )
            people.append((account, status))

        quiz_ids = db.scalars(
            select(Quiz.quiz_id).where(
                Quiz.author_id == organizer.account_id,
                Quiz.status == QuizStatus.PUBLISHED,
            )
        ).all()
        db.commit()

        print(f"Class {class_.class_id}: {class_.name} (code {class_.join_code})")
        print(f"  organizer  {organizer.account_id}  {organizer.email}")
        for account, status in people:
            label = status.value if status else "NOT A MEMBER"
            print(f"  {label:<12} {account.account_id}  {account.display_name}")
        if quiz_ids:
            pairs = ",".join(f"{quiz_id}:{class_.class_id}" for quiz_id in quiz_ids)
            print(f"\nAdd to backend/.env, then restart the API:\nDEV_QUIZ_CLASS_MAP={pairs}")
        else:
            print("\nPublish a quiz first, then run this again for the DEV_QUIZ_CLASS_MAP line.")


if __name__ == "__main__":
    main()
