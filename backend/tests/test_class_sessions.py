from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import CurrentAccount
from app.models import (
    Account,
    AccountRole,
    AnswerChoice,
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    LiveSession,
    LiveSessionStatus,
    MembershipStatus,
    Question,
    QuizSubmission,
    QuizVersion,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
    SubmissionStatus,
)
from tests.class_quiz_helpers import approve_quiz, make_class, publish_quiz
from tests.test_session_api import QUIZ_PAYLOAD, session_client, use_account

__all__ = ["session_client"]


@pytest.fixture
def class_setup(
    session_client: tuple[TestClient, dict[str, CurrentAccount]],
) -> tuple[TestClient, dict[str, CurrentAccount], int]:
    """A class where author organizes, participant is an active member, and
    invited/removed hold those statuses. "other" stays outside the class."""
    client, accounts = session_client
    author_id = accounts["author"].account_id
    with client.app.state.database.session_factory() as db:
        db.get(Account, author_id).account_type = "ADMINISTRATOR"
        db.commit()
    accounts["author"] = CurrentAccount(author_id, AccountRole.ADMIN, True)
    use_account(client, accounts["author"])
    with client.app.state.database.session_factory() as db:
        for name in ["member", "invited", "removed"]:
            model = Account(
                auth0_sub=f"test|{name}",
                email=f"{name}@test.invalid",
                display_name=name.title(),
            )
            db.add(model)
            db.flush()
            accounts[name] = CurrentAccount(model.account_id, AccountRole.USER, True)

        class_ = Class(
            name="CS 440",
            created_by_id=accounts["author"].account_id,
            join_code="ABCD2345",
        )
        db.add(class_)
        db.flush()
        for name, role, status, via in [
            ("author", ClassRole.ORGANIZER, MembershipStatus.ACTIVE, JoinedVia.CREATOR),
            ("participant", ClassRole.MEMBER, MembershipStatus.ACTIVE, JoinedVia.CODE),
            ("member", ClassRole.MEMBER, MembershipStatus.ACTIVE, JoinedVia.CODE),
            ("invited", ClassRole.MEMBER, MembershipStatus.INVITED, JoinedVia.INVITE),
            ("removed", ClassRole.MEMBER, MembershipStatus.REMOVED, JoinedVia.CODE),
        ]:
            db.add(
                ClassMembership(
                    class_id=class_.class_id,
                    account_id=accounts[name].account_id,
                    role=role,
                    status=status,
                    joined_via=via,
                )
            )
        db.commit()
        class_id = class_.class_id
    return client, accounts, class_id


def class_quiz(
    client: TestClient,
    class_id: int,
    *,
    approve: bool = True,
) -> dict:
    """A published quiz owned by the current account in the class,
    approved for hosting there unless approve=False."""
    created = client.post(f"/classes/{class_id}/quizzes", json=QUIZ_PAYLOAD)
    assert created.status_code == 201
    quiz_id = created.json()["quiz_id"]
    publish_quiz(client, quiz_id)
    if approve:
        approve_quiz(client, quiz_id)
    return client.get(f"/quizzes/{quiz_id}").json()


def host(client: TestClient, quiz_id: int, class_id: int):
    return client.post(f"/classes/{class_id}/quizzes/{quiz_id}/sessions")


def error_code(response) -> str:
    return response.json()["error"]["code"]


def test_organizer_creates_class_scoped_session(class_setup) -> None:
    client, _, class_id = class_setup
    quiz = class_quiz(client, class_id)

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 201
    assert response.json()["class_id"] == class_id
    assert response.json()["quiz_version_id"] == quiz["version"]["quiz_version_id"]


def test_member_can_host_their_own_approved_quiz(class_setup) -> None:
    client, accounts, class_id = class_setup
    use_account(client, accounts["member"])
    quiz = class_quiz(client, class_id)

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 201
    assert response.json()["host_id"] == accounts["member"].account_id


def test_organizer_can_host_a_members_approved_quiz(class_setup) -> None:
    client, accounts, class_id = class_setup
    use_account(client, accounts["member"])
    quiz = class_quiz(client, class_id)
    use_account(client, accounts["author"])

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 201
    assert response.json()["host_id"] == accounts["author"].account_id


def test_plain_member_cannot_host_someone_elses_quiz(class_setup) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id)
    use_account(client, accounts["member"])

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 403
    assert error_code(response) == "session_host_denied"


def test_collaborator_cannot_host_just_by_collaborating(class_setup) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id)
    shared = client.post(
        f"/classes/{class_id}/quizzes/{quiz['quiz_id']}/collaborators",
        json={"email": "member@test.invalid", "permission": "EDITOR"},
    )
    assert shared.status_code == 201
    use_account(client, accounts["member"])

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 403
    assert error_code(response) == "session_host_denied"


@pytest.mark.parametrize("name", ["invited", "removed", "other"])
def test_people_outside_the_class_cannot_host(class_setup, name) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id)
    use_account(client, accounts[name])

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 404
    assert error_code(response) == "class_not_found"


def test_unrelated_faculty_cannot_host(class_setup) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id)
    use_account(client, accounts["admin"])

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 404
    assert error_code(response) == "class_not_found"


def test_quiz_from_another_class_cannot_be_hosted(class_setup) -> None:
    client, accounts, class_id = class_setup
    other_class_id = make_class(client, accounts["author"].account_id, "Other")
    quiz = class_quiz(client, other_class_id)

    # Approved in its own class, but hosted in the wrong one.
    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 404
    assert error_code(response) == "quiz_not_found"


def test_missing_quiz_looks_the_same_as_another_classes_quiz(class_setup) -> None:
    client, _, class_id = class_setup

    response = host(client, 999_999, class_id)

    assert response.status_code == 404
    assert error_code(response) == "quiz_not_found"


def test_unapproved_quiz_cannot_be_hosted(class_setup) -> None:
    client, _, class_id = class_setup
    quiz = class_quiz(client, class_id, approve=False)

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 409
    assert error_code(response) == "quiz_version_not_approved"


@pytest.mark.parametrize("status", ["PENDING", "REJECTED", "WITHDRAWN"])
def test_pending_rejected_and_withdrawn_versions_cannot_be_hosted(
    class_setup, status
) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id, approve=False)
    decided = status != "PENDING"
    with client.app.state.database.session_factory() as db:
        db.add(
            QuizSubmission(
                class_id=class_id,
                quiz_version_id=quiz["version"]["quiz_version_id"],
                submitted_by_id=accounts["author"].account_id,
                status=SubmissionStatus(status),
                decided_by_id=accounts["author"].account_id if decided else None,
                decided_at=datetime.now(UTC).replace(tzinfo=None) if decided else None,
            )
        )
        db.commit()

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 409
    assert error_code(response) == "quiz_version_not_approved"


def test_stale_approved_version_cannot_be_hosted(class_setup) -> None:
    client, _, class_id = class_setup
    quiz = class_quiz(client, class_id)
    # A newer version is published after approval; it needs its own approval.
    with client.app.state.database.session_factory() as db:
        old = db.get(QuizVersion, quiz["version"]["quiz_version_id"])
        db.add(
            QuizVersion(
                quiz_id=quiz["quiz_id"],
                version_number=old.version_number + 1,
                title="Edited",
                published_at=datetime.now(UTC).replace(tzinfo=None),
            )
        )
        db.commit()

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 409
    assert error_code(response) == "quiz_version_not_approved"


def test_archived_quiz_cannot_be_hosted(class_setup) -> None:
    client, _, class_id = class_setup
    quiz = class_quiz(client, class_id)
    assert client.patch(f"/quizzes/{quiz['quiz_id']}/archive").status_code == 200

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 409
    assert error_code(response) == "quiz_not_hostable"


def test_archived_class_cannot_start_sessions(class_setup) -> None:
    client, _, class_id = class_setup
    quiz = class_quiz(client, class_id)
    with client.app.state.database.session_factory() as db:
        class_ = db.get(Class, class_id)
        class_.archived_at = datetime(2026, 10, 1)
        class_.join_code = None
        class_.joining_open = False
        db.commit()

    response = host(client, quiz["quiz_id"], class_id)

    assert response.status_code == 409
    assert error_code(response) == "class_archived"


def test_sessions_cannot_be_created_without_a_class(class_setup) -> None:
    client, _, class_id = class_setup
    quiz = class_quiz(client, class_id)

    # The old open-session route is gone.
    response = client.post(f"/quizzes/{quiz['quiz_id']}/sessions")

    assert response.status_code in (404, 405)


def legacy_open_session(client: TestClient, quiz: dict, host_id: int) -> LiveSession:
    """A pre-V3 session with no class, as old data may still have."""
    with client.app.state.database.session_factory() as db:
        session = LiveSession(
            quiz_version_id=quiz["version"]["quiz_version_id"],
            host_id=host_id,
            class_id=None,
            join_code="246810",
            status=LiveSessionStatus.LOBBY,
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        return session


def test_old_sessions_without_a_class_cannot_be_joined(class_setup) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id)
    session = legacy_open_session(client, quiz, accounts["author"].account_id)
    use_account(client, accounts["participant"])

    by_code = client.post("/sessions/join", json={"join_code": "246810"})
    by_id = client.post(f"/sessions/{session.session_id}/join")

    assert by_code.status_code == 403
    assert error_code(by_code) == "not_class_member"
    assert by_id.status_code == 404
    assert error_code(by_id) == "session_not_found"


def test_active_members_join_a_class_session(class_setup) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id)
    session = host(client, quiz["quiz_id"], class_id).json()

    use_account(client, accounts["participant"])
    by_code = client.post("/sessions/join", json={"join_code": session["join_code"]})
    use_account(client, accounts["member"])
    by_id = client.post(f"/sessions/{session['session_id']}/join")

    assert by_code.status_code == 201
    assert by_id.status_code == 201
    listed = client.get(f"/classes/{class_id}/active-sessions")
    assert listed.status_code == 200
    assert [row["session_id"] for row in listed.json()] == [session["session_id"]]
    assert listed.json()[0]["joined"] is True
    assert listed.json()[0]["left"] is False


def test_departed_participant_is_labeled_and_cannot_rejoin(class_setup) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id)
    session = host(client, quiz["quiz_id"], class_id).json()
    use_account(client, accounts["participant"])
    joined = client.post(
        "/sessions/join", json={"join_code": session["join_code"]}
    )
    assert joined.status_code == 201

    with client.app.state.database.session_factory() as db:
        participant = db.scalar(
            select(SessionParticipant).where(
                SessionParticipant.session_id == session["session_id"],
                SessionParticipant.account_id == accounts["participant"].account_id,
            )
        )
        assert participant is not None
        participant.left_at = datetime.now(UTC).replace(tzinfo=None)
        db.commit()

    listed = client.get(f"/classes/{class_id}/active-sessions")
    assert listed.status_code == 200
    assert listed.json()[0]["joined"] is False
    assert listed.json()[0]["left"] is True

    rejoin = client.post(f"/sessions/{session['session_id']}/join")
    assert rejoin.status_code == 409
    assert error_code(rejoin) == "session_already_joined"


def test_removed_member_cannot_answer_after_joining(class_setup) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id)
    session = host(client, quiz["quiz_id"], class_id).json()
    use_account(client, accounts["participant"])
    joined = client.post(
        "/sessions/join", json={"join_code": session["join_code"]}
    )
    assert joined.status_code == 201

    now = datetime.now(UTC).replace(tzinfo=None)
    with client.app.state.database.session_factory() as db:
        live_session = db.get(LiveSession, session["session_id"])
        assert live_session is not None
        question = db.scalar(
            select(Question).where(
                Question.quiz_version_id == live_session.quiz_version_id,
                Question.question_order == 1,
            )
        )
        assert question is not None
        choice = db.scalar(
            select(AnswerChoice).where(
                AnswerChoice.question_id == question.question_id,
                AnswerChoice.choice_order == 1,
            )
        )
        assert choice is not None
        membership = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == accounts["participant"].account_id,
            )
        )
        assert membership is not None
        membership.status = MembershipStatus.REMOVED
        live_session.status = LiveSessionStatus.ACTIVE
        live_session.current_question_order = 1
        played = SessionQuestion(
            session_id=live_session.session_id,
            question_id=question.question_id,
            status=SessionQuestionStatus.OPEN,
            opened_at=now - timedelta(seconds=1),
            closes_at=now + timedelta(seconds=29),
        )
        db.add(played)
        db.commit()
        session_question_id = played.session_question_id
        choice_id = choice.choice_id

    response = client.post(
        f"/sessions/{session['session_id']}/questions/"
        f"{session_question_id}/responses",
        json={"choice_id": choice_id},
    )
    assert response.status_code == 403
    assert error_code(response) == "not_class_member"


@pytest.mark.parametrize("name", ["invited", "removed", "other"])
def test_invited_removed_and_outside_users_cannot_join(class_setup, name) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id)
    session = host(client, quiz["quiz_id"], class_id).json()
    use_account(client, accounts[name])

    by_code = client.post("/sessions/join", json={"join_code": session["join_code"]})
    by_id = client.post(f"/sessions/{session['session_id']}/join")
    listed = client.get(f"/classes/{class_id}/active-sessions")

    assert by_code.status_code == 403
    assert error_code(by_code) == "not_class_member"
    assert by_id.status_code == 404
    assert error_code(by_id) == "session_not_found"
    assert listed.status_code == 404
    assert error_code(listed) == "class_not_found"


def test_removed_member_cannot_view_their_old_results(class_setup) -> None:
    client, accounts, class_id = class_setup
    quiz = class_quiz(client, class_id)
    session = host(client, quiz["quiz_id"], class_id).json()
    use_account(client, accounts["participant"])
    joined = client.post("/sessions/join", json={"join_code": session["join_code"]})
    assert joined.status_code == 201
    with client.app.state.database.session_factory() as db:
        db.get(LiveSession, session["session_id"]).status = LiveSessionStatus.COMPLETED
        membership = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == accounts["participant"].account_id,
            )
        )
        membership.status = MembershipStatus.REMOVED
        db.commit()

    response = client.get(f"/sessions/{session['session_id']}/results")

    assert response.status_code == 404
    assert error_code(response) == "class_not_found"
