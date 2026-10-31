"""Create quizzes the V3 way in tests: inside a class.

Quizzes no longer exist outside a class, so tests that only need "a saved
quiz" put the current account in a fresh class as its organizer first.
"""

from fastapi.testclient import TestClient
from httpx import Response

from app.auth import get_active_account
from app.models.classes import Class, ClassMembership, ClassRole, JoinedVia


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


def post_class_quiz(client: TestClient, payload: dict) -> Response:
    """POST the quiz as the current account, into a class it organizes."""
    account = client.app.dependency_overrides[get_active_account]()
    class_id = make_class(client, account.account_id)
    return client.post(f"/classes/{class_id}/quizzes", json=payload)
