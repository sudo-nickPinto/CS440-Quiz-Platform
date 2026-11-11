"""The Host button and the start-session endpoint use the same rules.

Each quiz response says whether the caller can host it (`hosting`), and when
hosting is refused, the error carries the same reason and message.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import event, select

from app.models import (
    Class,
    ClassMembership,
    ClassRole,
    QuizSubmission,
    QuizVersion,
    SubmissionStatus,
)
from tests.test_class_sessions import (
    QUIZ_PAYLOAD,
    class_quiz,
    class_setup,
    error_code,
    host,
)
from tests.test_session_api import session_client, use_account

__all__ = ["class_setup", "session_client"]


def now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hosting(client, quiz_id: int) -> dict:
    response = client.get(f"/quizzes/{quiz_id}")
    assert response.status_code == 200
    return response.json()["hosting"]


def assert_blocked(client, quiz_id: int, class_id: int, reason: str, code: str):
    """The quiz response and the start-session error agree on the reason."""
    status = hosting(client, quiz_id)
    assert status["can_host"] is False
    assert status["reason"] == reason
    assert status["message"]

    response = host(client, quiz_id, class_id)
    assert response.status_code in (403, 409)
    assert error_code(response) == code
    error = response.json()["error"]
    assert error["details"] == {"reason": reason}
    assert error["message"] == status["message"]


def add_submission(client, class_id, version_id, account_id, status) -> None:
    decided = status != SubmissionStatus.PENDING
    with client.app.state.database.session_factory() as db:
        db.add(
            QuizSubmission(
                class_id=class_id,
                quiz_version_id=version_id,
                submitted_by_id=account_id,
                status=status,
                decided_by_id=account_id if decided else None,
                decided_at=now() if decided else None,
            )
        )
        db.commit()


def test_approved_quiz_can_be_hosted_by_its_owner(class_setup) -> None:
    client, _, class_id = class_setup
    quiz = class_quiz(client, class_id)

    assert quiz["hosting"] == {"can_host": True, "reason": None, "message": None}
    assert host(client, quiz["quiz_id"], class_id).status_code == 201


def test_organizer_sees_a_members_approved_quiz_as_hostable(class_setup) -> None:
    client, accounts, class_id = class_setup
    use_account(client, accounts["member"])
    quiz = class_quiz(client, class_id)
    use_account(client, accounts["author"])

    assert hosting(client, quiz["quiz_id"])["can_host"] is True
    assert host(client, quiz["quiz_id"], class_id).status_code == 201


def test_draft_must_be_published_first(class_setup) -> None:
    client, _, class_id = class_setup
    created = client.post(f"/classes/{class_id}/quizzes", json=QUIZ_PAYLOAD)
    assert created.status_code == 201
    assert created.json()["hosting"]["reason"] == "not_published"

    assert_blocked(
        client, created.json()["quiz_id"], class_id, "not_published", "quiz_not_hostable"
    )


def test_published_quiz_must_be_submitted(class_setup) -> None:
    client, _, class_id = class_setup
    quiz = class_quiz(client, class_id, approve=False)

    assert_blocked(
        client, quiz["quiz_id"], class_id, "not_submitted", "quiz_version_not_approved"
    )


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        (SubmissionStatus.PENDING, "pending_approval"),
        (SubmissionStatus.REJECTED, "rejected"),
        (SubmissionStatus.WITHDRAWN, "withdrawn"),
    ],
)
def test_each_unapproved_submission_state_has_its_own_reason(
    class_setup, status, reason
) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id, approve=False)
    add_submission(
        client,
        class_id,
        quiz["version"]["quiz_version_id"],
        accounts["author"].account_id,
        status,
    )

    assert_blocked(
        client, quiz["quiz_id"], class_id, reason, "quiz_version_not_approved"
    )


def test_newer_version_needs_its_own_approval(class_setup) -> None:
    client, _, class_id = class_setup
    quiz = class_quiz(client, class_id)
    with client.app.state.database.session_factory() as db:
        old = db.get(QuizVersion, quiz["version"]["quiz_version_id"])
        db.add(
            QuizVersion(
                quiz_id=quiz["quiz_id"],
                version_number=old.version_number + 1,
                title="Edited",
                published_at=now(),
            )
        )
        db.commit()

    assert_blocked(
        client,
        quiz["quiz_id"],
        class_id,
        "approval_outdated",
        "quiz_version_not_approved",
    )


def test_archived_quiz_is_not_hostable(class_setup) -> None:
    client, _, class_id = class_setup
    quiz = class_quiz(client, class_id)
    assert client.patch(f"/quizzes/{quiz['quiz_id']}/archive").status_code == 200

    assert_blocked(
        client, quiz["quiz_id"], class_id, "quiz_archived", "quiz_not_hostable"
    )


def test_archived_class_is_not_hostable(class_setup) -> None:
    client, _, class_id = class_setup
    quiz = class_quiz(client, class_id)
    with client.app.state.database.session_factory() as db:
        class_ = db.get(Class, class_id)
        class_.archived_at = now()
        class_.join_code = None
        class_.joining_open = False
        db.commit()

    assert_blocked(client, quiz["quiz_id"], class_id, "class_archived", "class_archived")


def test_collaborator_sees_why_they_cannot_host(class_setup) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id)
    shared = client.post(
        f"/classes/{class_id}/quizzes/{quiz['quiz_id']}/collaborators",
        json={"email": "member@test.invalid", "permission": "EDITOR"},
    )
    assert shared.status_code == 201
    use_account(client, accounts["member"])

    assert_blocked(
        client, quiz["quiz_id"], class_id, "not_host", "session_host_denied"
    )


def test_quiz_lists_include_hosting_status(class_setup) -> None:
    client, _, class_id = class_setup
    approved = class_quiz(client, class_id)
    pending = class_quiz(client, class_id, approve=False)

    mine = {item["quiz_id"]: item["hosting"] for item in client.get("/quizzes").json()}
    assert mine[approved["quiz_id"]]["can_host"] is True
    assert mine[pending["quiz_id"]]["reason"] == "not_submitted"

    page = client.get(f"/classes/{class_id}/quizzes").json()
    in_class = {item["quiz_id"]: item["hosting"] for item in page["items"]}
    assert in_class[approved["quiz_id"]]["can_host"] is True
    assert in_class[pending["quiz_id"]]["reason"] == "not_submitted"


def test_non_faculty_organizer_matches_create_session(class_setup) -> None:
    """Old class data can have organizers who aren't faculty. They don't get
    organizer powers (ClassAccess.is_organizer), so the Host button must
    not offer them someone else's quiz either."""
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id)
    with client.app.state.database.session_factory() as db:
        membership = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == accounts["member"].account_id,
            )
        )
        membership.role = ClassRole.ORGANIZER
        db.commit()
    use_account(client, accounts["member"])

    assert_blocked(
        client, quiz["quiz_id"], class_id, "not_host", "session_host_denied"
    )


def count_queries(client, request):
    engine = client.app.state.database.engine
    statements = []

    def record(*_args):
        statements.append(1)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = request()
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert response.status_code == 200
    return len(statements)


def test_quiz_lists_use_the_same_number_of_queries_for_any_length(
    class_setup,
) -> None:
    """Hosting status is batch-loaded, so longer lists don't add queries."""
    client, accounts, class_id = class_setup
    class_quiz(client, class_id)

    def lists():
        return (
            count_queries(client, lambda: client.get("/quizzes")),
            count_queries(client, lambda: client.get(f"/classes/{class_id}/quizzes")),
        )

    small = lists()

    # One quiz in every state: approved, not submitted, pending, rejected,
    # withdrawn, outdated approval, draft and archived.
    for _ in range(2):
        class_quiz(client, class_id, approve=False)
    for status in (
        SubmissionStatus.PENDING,
        SubmissionStatus.REJECTED,
        SubmissionStatus.WITHDRAWN,
    ):
        quiz = class_quiz(client, class_id, approve=False)
        add_submission(
            client,
            class_id,
            quiz["version"]["quiz_version_id"],
            accounts["author"].account_id,
            status,
        )
    outdated = class_quiz(client, class_id)
    with client.app.state.database.session_factory() as db:
        db.add(
            QuizVersion(
                quiz_id=outdated["quiz_id"],
                version_number=outdated["version"]["version_number"] + 1,
                title="Edited",
                published_at=now(),
            )
        )
        db.commit()
    assert client.post(f"/classes/{class_id}/quizzes", json=QUIZ_PAYLOAD).status_code == 201
    archived = class_quiz(client, class_id)
    assert client.patch(f"/quizzes/{archived['quiz_id']}/archive").status_code == 200

    assert lists() == small


def test_editing_an_approved_quiz_blocks_hosting_until_the_new_version_is_approved(
    class_setup,
) -> None:
    """Approve v1, edit it into draft v2: hosting must not silently fall back
    to v1, because the page now shows v2. Uses the real API end to end."""
    client, accounts, class_id = class_setup
    base = f"/classes/{class_id}"

    def submit_and_approve(version_id: int) -> None:
        use_account(client, accounts["member"])
        submitted = client.post(
            f"{base}/quiz-submissions", json={"quiz_version_id": version_id}
        )
        assert submitted.status_code == 201
        use_account(client, accounts["author"])
        decided = client.patch(
            f"{base}/quiz-submissions/{submitted.json()['submission_id']}",
            json={"status": "APPROVED"},
        )
        assert decided.status_code == 200
        use_account(client, accounts["member"])

    use_account(client, accounts["member"])
    created = client.post(f"{base}/quizzes", json=QUIZ_PAYLOAD).json()
    quiz_id = created["quiz_id"]
    published = client.post(
        f"{base}/quizzes/{quiz_id}/publish",
        json={"expected_revision": created["revision"]},
    )
    assert published.status_code == 200
    v1 = published.json()["version"]["quiz_version_id"]
    submit_and_approve(v1)
    assert hosting(client, quiz_id)["can_host"] is True

    edited = client.put(
        f"{base}/quizzes/{quiz_id}",
        json={
            **QUIZ_PAYLOAD,
            "title": "Edited title",
            "expected_revision": published.json()["revision"],
        },
    )
    assert edited.status_code == 200
    assert edited.json()["hosting"]["reason"] == "unpublished_changes"
    assert_blocked(
        client, quiz_id, class_id, "unpublished_changes", "quiz_not_hostable"
    )

    republished = client.post(
        f"{base}/quizzes/{quiz_id}/publish",
        json={"expected_revision": edited.json()["revision"]},
    )
    assert republished.status_code == 200
    # The publish response itself already reflects the new state.
    assert republished.json()["hosting"]["reason"] == "approval_outdated"
    v2 = republished.json()["version"]["quiz_version_id"]
    assert v2 != v1

    submit_and_approve(v2)
    session = host(client, quiz_id, class_id)
    assert session.status_code == 201
    assert session.json()["quiz_version_id"] == v2


def test_draft_version_on_top_blocks_hosting_even_if_status_says_published(
    class_setup,
) -> None:
    """Defense in depth: the versions themselves decide, not just the status."""
    client, _, class_id = class_setup
    quiz = class_quiz(client, class_id)
    with client.app.state.database.session_factory() as db:
        db.add(
            QuizVersion(
                quiz_id=quiz["quiz_id"],
                version_number=quiz["version"]["version_number"] + 1,
                title="Unpublished draft",
                published_at=None,
            )
        )
        db.commit()

    assert_blocked(
        client, quiz["quiz_id"], class_id, "unpublished_changes", "quiz_not_hostable"
    )
