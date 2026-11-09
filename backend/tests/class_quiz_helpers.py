"""Create and host quizzes the V3 way in tests: inside a class.

Quizzes no longer exist outside a class, so tests that only need "a saved,
hostable quiz" put the current account in a fresh class as its organizer,
create the quiz there, and publish the draft. Every session belongs to a
class too, so host_quiz() approves the quiz for its class, puts the test's
accounts in the class, and starts the session there.
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from httpx import Response

from sqlalchemy import select

from app.auth import get_active_account
from app.models.account import Account
from app.models.classes import (
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    MembershipStatus,
)
from app.models.quiz import Quiz, QuizStatus, QuizVersion
from app.models.quiz_submission import QuizSubmission, SubmissionStatus


def make_class(client: TestClient, account_id: int, name: str = "Quiz Class") -> int:
    """A new class with account_id as its active organizer."""
    with client.app.state.database.session_factory() as db:
        class_ = Class(
            name=name,
            created_by_id=account_id,
            join_code=None,
            joining_open=False,
            memberships=[
                ClassMembership(
                    account_id=account_id,
                    role=ClassRole.ORGANIZER,
                    joined_via=JoinedVia.CREATOR,
                )
            ],
        )
        db.add(class_)
        db.commit()
        return class_.class_id


def publish_quiz(client: TestClient, quiz_id: int) -> None:
    """Publish the quiz's draft directly; the API has no publish step yet."""
    with client.app.state.database.session_factory() as db:
        quiz = db.get(Quiz, quiz_id)
        quiz.status = QuizStatus.PUBLISHED
        for version in quiz.versions:
            version.published_at = version.published_at or datetime.now(UTC).replace(
                tzinfo=None
            )
        db.commit()


def post_class_quiz(client: TestClient, payload: dict) -> Response:
    """Create and publish a quiz as the current account, in a class it
    organizes. Returns a 201 response with the published quiz, or the
    failed create response."""
    account = client.app.dependency_overrides[get_active_account]()
    class_id = make_class(client, account.account_id)
    created = client.post(f"/classes/{class_id}/quizzes", json=payload)
    if created.status_code != 201:
        return created
    quiz_id = created.json()["quiz_id"]
    publish_quiz(client, quiz_id)
    return Response(201, json=client.get(f"/quizzes/{quiz_id}").json())


def create_approved_quiz(client: TestClient, class_id: int, payload: dict) -> dict:
    """A published quiz by the current account in an existing class,
    approved for hosting there."""
    created = client.post(f"/classes/{class_id}/quizzes", json=payload)
    assert created.status_code == 201, created.text
    quiz_id = created.json()["quiz_id"]
    publish_quiz(client, quiz_id)
    approve_quiz(client, quiz_id)
    return client.get(f"/quizzes/{quiz_id}").json()


def quiz_class_id(client: TestClient, quiz_id: int) -> int:
    with client.app.state.database.session_factory() as db:
        return db.get(Quiz, quiz_id).class_id


def add_member(
    client: TestClient,
    class_id: int,
    account_id: int,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> None:
    """Put the account in the class as a plain member with this status."""
    with client.app.state.database.session_factory() as db:
        membership = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == account_id,
            )
        )
        if membership is None:
            membership = ClassMembership(
                class_id=class_id,
                account_id=account_id,
                role=ClassRole.MEMBER,
                joined_via=JoinedVia.CODE,
            )
            db.add(membership)
        membership.status = status
        db.commit()


def enroll_everyone(client: TestClient, class_id: int) -> None:
    """Make every account in the test database an active class member."""
    with client.app.state.database.session_factory() as db:
        account_ids = db.scalars(select(Account.account_id)).all()
    for account_id in account_ids:
        with client.app.state.database.session_factory() as db:
            exists = db.scalar(
                select(ClassMembership.membership_id).where(
                    ClassMembership.class_id == class_id,
                    ClassMembership.account_id == account_id,
                )
            )
        if exists is None:
            add_member(client, class_id, account_id)


def approve_quiz(client: TestClient, quiz_id: int) -> None:
    """Approve the quiz's newest published version for its class."""
    with client.app.state.database.session_factory() as db:
        quiz = db.get(Quiz, quiz_id)
        version = db.scalar(
            select(QuizVersion)
            .where(
                QuizVersion.quiz_id == quiz_id,
                QuizVersion.published_at.is_not(None),
            )
            .order_by(QuizVersion.version_number.desc())
            .limit(1)
        )
        already = db.scalar(
            select(QuizSubmission.submission_id).where(
                QuizSubmission.class_id == quiz.class_id,
                QuizSubmission.quiz_version_id == version.quiz_version_id,
                QuizSubmission.status == SubmissionStatus.APPROVED,
            )
        )
        if already is None:
            db.add(
                QuizSubmission(
                    class_id=quiz.class_id,
                    quiz_version_id=version.quiz_version_id,
                    submitted_by_id=quiz.author_id,
                    status=SubmissionStatus.APPROVED,
                    decided_by_id=quiz.author_id,
                    decided_at=datetime.now(UTC).replace(tzinfo=None),
                )
            )
            db.commit()


def host_quiz(
    client: TestClient,
    quiz_id: int,
    *,
    enroll: bool = True,
    approve: bool = True,
    members: list[int] | None = None,
) -> Response:
    """Start a session for the quiz in its own class as the current account.

    By default the quiz is approved first and every test account is made an
    active member, so older tests about timing and scoring keep working.
    Pass members to put only those accounts in the class instead.
    """
    class_id = quiz_class_id(client, quiz_id)
    if approve:
        approve_quiz(client, quiz_id)
    if members is not None:
        for account_id in members:
            add_member(client, class_id, account_id)
    elif enroll:
        enroll_everyone(client, class_id)
    return client.post(f"/classes/{class_id}/quizzes/{quiz_id}/sessions")
