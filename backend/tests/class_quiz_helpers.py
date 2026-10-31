"""Create quizzes the V3 way in tests: inside a class.

Quizzes no longer exist outside a class, so tests that only need "a saved,
hostable quiz" put the current account in a fresh class as its organizer,
create the quiz there, and publish the draft.
"""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from httpx import Response

from app.auth import get_active_account
from app.models.classes import Class, ClassMembership, ClassRole, JoinedVia
from app.models.quiz import Quiz, QuizStatus


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
