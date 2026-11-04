from collections.abc import Iterator
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentAccount, get_active_account
from app.api.routes import quiz_editing_live
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.classes import (
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    MembershipStatus,
)
from app.models.quiz import CollaboratorEventType, QuizCollaboratorEvent


QUIZ_PAYLOAD = {
    "title": "Shared quiz",
    "description": "Original",
    "questions": [
        {
            "question_text": "Which answer?",
            "time_limit_seconds": 20,
            "base_points": 1000,
            "choices": [
                {"choice_text": "Correct", "is_correct": True},
                {"choice_text": "Incorrect", "is_correct": False},
            ],
        }
    ],
}


@pytest.fixture
def collaboration_client() -> Iterator[
    tuple[TestClient, int, CurrentAccount, CurrentAccount, CurrentAccount]
]:
    app = create_app(
        Settings(
            database_url="sqlite://",
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
        )
    )
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.database.engine)
        with app.state.database.session_factory() as db:
            owner_model = Account(
                auth0_sub="auth0|owner",
                email="owner@example.com",
                display_name="Owner",
                is_active=True,
            )
            editor_model = Account(
                auth0_sub="auth0|editor",
                email="editor@example.com",
                display_name="Editor",
                is_active=True,
            )
            outsider_model = Account(
                auth0_sub="auth0|outsider",
                email="outsider@example.com",
                display_name="Outsider",
                is_active=True,
            )
            db.add_all([owner_model, editor_model, outsider_model])
            db.flush()
            class_ = Class(
                name="CS 440",
                created_by_id=owner_model.account_id,
                join_code="ABCDEFGH",
            )
            db.add(class_)
            db.flush()
            db.add_all(
                [
                    ClassMembership(
                        class_id=class_.class_id,
                        account_id=owner_model.account_id,
                        role=ClassRole.MEMBER,
                        status=MembershipStatus.ACTIVE,
                        joined_via=JoinedVia.CODE,
                    ),
                    ClassMembership(
                        class_id=class_.class_id,
                        account_id=editor_model.account_id,
                        role=ClassRole.MEMBER,
                        status=MembershipStatus.ACTIVE,
                        joined_via=JoinedVia.CODE,
                    ),
                ]
            )
            db.commit()
            class_id = class_.class_id
            owner = CurrentAccount(owner_model.account_id, AccountRole.USER, True)
            editor = CurrentAccount(editor_model.account_id, AccountRole.USER, True)
            outsider = CurrentAccount(
                outsider_model.account_id, AccountRole.USER, True
            )

        app.dependency_overrides[get_active_account] = lambda: owner
        yield client, class_id, owner, editor, outsider


def _create(client: TestClient, class_id: int) -> dict:
    response = client.post(f"/classes/{class_id}/quizzes", json=QUIZ_PAYLOAD)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "DRAFT"
    assert body["visibility"] == "PRIVATE"
    assert body["version"]["published_at"] is None
    return body


def _edit_payload(expected_revision: int, title: str = "Edited") -> dict:
    payload = deepcopy(QUIZ_PAYLOAD)
    payload["expected_revision"] = expected_revision
    payload["title"] = title
    return payload


def _question_payload(expected_revision: int, text: str) -> dict:
    return {
        "expected_revision": expected_revision,
        "question_text": text,
        "time_limit_seconds": 30,
        "base_points": 500,
        "choices": [
            {"choice_text": "Yes", "is_correct": True},
            {"choice_text": "No", "is_correct": False},
        ],
    }


def test_owner_shares_with_named_active_member_and_editor_updates(
    collaboration_client,
) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"

    shared = client.post(
        f"{path}/collaborators",
        json={"email": "  EDITOR@EXAMPLE.COM  ", "permission": "EDITOR"},
    )

    assert shared.status_code == 201
    assert shared.json()["account_id"] == editor.account_id
    assert client.get(f"{path}/collaborators").json()[0]["email"] == (
        "editor@example.com"
    )

    client.app.dependency_overrides[get_active_account] = lambda: editor
    assert client.get(path).status_code == 200
    updated = client.put(path, json=_edit_payload(1))

    assert updated.status_code == 200
    assert updated.json()["revision"] == 2
    assert updated.json()["version"]["version_number"] == 1
    assert updated.json()["version"]["published_at"] is None
    assert updated.json()["version"]["title"] == "Edited"
    assert client.get(path).json()["can_edit"] is True


def test_collaborators_save_different_questions_without_conflicting(
    collaboration_client,
) -> None:
    client, class_id, owner, editor, _ = collaboration_client
    payload = deepcopy(QUIZ_PAYLOAD)
    payload["questions"].append(
        {
            "question_text": "Second question?",
            "choices": [
                {"choice_text": "A", "is_correct": True},
                {"choice_text": "B", "is_correct": False},
            ],
        }
    )
    created = client.post(f"/classes/{class_id}/quizzes", json=payload).json()
    path = f"/classes/{class_id}/quizzes/{created['quiz_id']}"
    first, second = created["version"]["questions"]
    client.post(
        f"{path}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )

    first_saved = client.patch(
        f"{path}/questions/{first['question_id']}",
        json=_question_payload(1, "Owner changed the first"),
    )
    client.app.dependency_overrides[get_active_account] = lambda: editor
    second_saved = client.patch(
        f"{path}/questions/{second['question_id']}",
        json=_question_payload(1, "Editor changed the second"),
    )

    assert first_saved.status_code == 200
    assert second_saved.status_code == 200
    assert first_saved.json()["question"]["revision"] == 2
    assert second_saved.json()["question"]["revision"] == 2
    assert second_saved.json()["quiz_revision"] == 3

    client.app.dependency_overrides[get_active_account] = lambda: owner
    current = client.get(path).json()
    assert [q["question_text"] for q in current["version"]["questions"]] == [
        "Owner changed the first",
        "Editor changed the second",
    ]


def test_same_question_stale_save_returns_question_revision(
    collaboration_client,
) -> None:
    client, class_id, _, _, _ = collaboration_client
    quiz = _create(client, class_id)
    question = quiz["version"]["questions"][0]
    path = (
        f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
        f"/questions/{question['question_id']}"
    )

    assert client.patch(path, json=_question_payload(1, "First save")).status_code == 200
    stale = client.patch(path, json=_question_payload(1, "Stale save"))

    assert stale.status_code == 409
    assert stale.json()["error"] == {
        "code": "question_edit_conflict",
        "message": "This question changed after you opened it. Reload that question before saving.",
        "details": {"current_revision": 2},
    }


def test_first_question_edit_after_publish_creates_editable_draft(
    collaboration_client,
) -> None:
    client, class_id, _, _, _ = collaboration_client
    quiz = _create(client, class_id)
    base = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    published = client.post(
        f"{base}/publish", json={"expected_revision": quiz["revision"]}
    ).json()
    question = published["version"]["questions"][0]

    saved = client.patch(
        f"{base}/questions/{question['question_id']}",
        json=_question_payload(question["revision"], "New draft question"),
    )

    assert saved.status_code == 200
    current = client.get(base).json()
    assert current["status"] == "DRAFT"
    assert current["version"]["version_number"] == 2
    assert current["version"]["questions"][0]["question_text"] == (
        "New draft question"
    )


def test_question_save_broadcasts_committed_update(
    collaboration_client,
    monkeypatch,
) -> None:
    client, class_id, owner, _, _ = collaboration_client
    quiz = _create(client, class_id)
    question = quiz["version"]["questions"][0]
    monkeypatch.setattr(
        quiz_editing_live,
        "authenticate_token",
        lambda db, settings, token: owner,
    )

    with client.websocket_connect(f"/ws/quizzes/{quiz['quiz_id']}") as socket:
        socket.send_json({"type": "auth", "token": "test-token"})
        assert socket.receive_json() == {
            "type": "quiz_editor_state",
            "quiz_id": quiz["quiz_id"],
        }

        saved = client.patch(
            f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
            f"/questions/{question['question_id']}",
            json=_question_payload(1, "Broadcast this"),
        )
        assert saved.status_code == 200
        event = socket.receive_json()

    assert event["type"] == "question_updated"
    assert event["editor_account_id"] == owner.account_id
    assert event["question"]["question_text"] == "Broadcast this"
    assert event["question"]["revision"] == 2


def test_stale_revision_returns_current_revision_without_partial_save(
    collaboration_client,
) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    client.post(
        f"{path}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )

    client.app.dependency_overrides[get_active_account] = lambda: editor
    assert client.put(path, json=_edit_payload(1, "First save")).status_code == 200
    stale = client.put(path, json=_edit_payload(1, "Must not save"))

    assert stale.status_code == 409
    assert stale.json()["error"] == {
        "code": "quiz_edit_conflict",
        "message": "This quiz changed after you opened it. Reload the latest version before saving again.",
        "details": {"current_revision": 2},
    }
    current = client.get(path).json()
    assert current["revision"] == 2
    assert current["version"]["title"] == "First save"


def test_owner_publishes_draft_and_a_later_edit_creates_a_new_version(
    collaboration_client,
) -> None:
    client, class_id, _, _, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"

    published = client.post(
        f"{path}/publish",
        json={"expected_revision": quiz["revision"]},
    )

    assert published.status_code == 200
    assert published.json()["status"] == "PUBLISHED"
    assert published.json()["revision"] == 2
    assert published.json()["version"]["version_number"] == 1
    assert published.json()["version"]["published_at"] is not None

    edited = client.put(path, json=_edit_payload(2, "Next draft"))
    assert edited.status_code == 200
    assert edited.json()["status"] == "DRAFT"
    assert edited.json()["revision"] == 3
    assert edited.json()["version"]["version_number"] == 2
    assert edited.json()["version"]["published_at"] is None


def test_collaborator_can_edit_but_cannot_publish(collaboration_client) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    client.post(
        f"{path}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )
    client.app.dependency_overrides[get_active_account] = lambda: editor

    edited = client.put(path, json=_edit_payload(1, "Editor draft"))
    assert edited.status_code == 200
    denied = client.post(
        f"{path}/publish",
        json={"expected_revision": edited.json()["revision"]},
    )

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "quiz_publish_denied"


def test_publish_rejects_stale_revision_and_requires_an_unpublished_draft(
    collaboration_client,
) -> None:
    client, class_id, _, _, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    assert client.put(path, json=_edit_payload(1, "Updated")).status_code == 200

    stale = client.post(f"{path}/publish", json={"expected_revision": 1})
    assert stale.status_code == 409
    assert stale.json()["error"] == {
        "code": "quiz_edit_conflict",
        "message": "This quiz changed after you opened it. Reload before publishing.",
        "details": {"current_revision": 2},
    }

    published = client.post(f"{path}/publish", json={"expected_revision": 2})
    assert published.status_code == 200
    again = client.post(f"{path}/publish", json={"expected_revision": 3})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "quiz_not_publishable"


def test_revocation_blocks_future_reads_and_writes(collaboration_client) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    client.post(
        f"{path}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )
    revoked = client.delete(f"{path}/collaborators/{editor.account_id}")
    assert revoked.status_code == 204

    client.app.dependency_overrides[get_active_account] = lambda: editor
    assert client.get(path).status_code == 404
    denied = client.put(path, json=_edit_payload(1))
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "quiz_edit_denied"


def test_only_owner_manages_collaborators(collaboration_client) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"

    client.app.dependency_overrides[get_active_account] = lambda: editor
    response = client.post(
        f"{path}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "collaborator_management_denied"


def test_nonmember_cannot_be_added(collaboration_client) -> None:
    client, class_id, _, _, outsider = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"

    response = client.post(
        f"{path}/collaborators",
        json={"email": "outsider@example.com", "permission": "EDITOR"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_class_member"

    client.app.dependency_overrides[get_active_account] = lambda: outsider
    assert client.get(path).status_code == 404


def test_unknown_email_and_nonmember_use_the_same_private_error(
    collaboration_client,
) -> None:
    client, class_id, _, _, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}/collaborators"

    unknown = client.post(
        path,
        json={"email": "missing@example.com", "permission": "EDITOR"},
    )
    outsider = client.post(
        path,
        json={"email": "outsider@example.com", "permission": "EDITOR"},
    )

    assert unknown.status_code == outsider.status_code == 409
    assert unknown.json()["error"]["code"] == "not_class_member"
    assert unknown.json()["error"] == outsider.json()["error"]


def test_removed_member_immediately_loses_collaborator_access(
    collaboration_client,
) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    client.post(
        f"{path}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )
    with client.app.state.database.session_factory() as db:
        membership = db.query(ClassMembership).filter_by(
            class_id=class_id,
            account_id=editor.account_id,
        ).one()
        membership.status = MembershipStatus.REMOVED
        db.commit()

    client.app.dependency_overrides[get_active_account] = lambda: editor
    assert client.get(path).status_code == 404
    denied = client.put(path, json=_edit_payload(1))
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "class_not_found"


def test_every_draft_edit_requires_expected_revision(
    collaboration_client,
) -> None:
    client, class_id, _, _, _ = collaboration_client
    quiz = _create(client, class_id)
    payload = deepcopy(QUIZ_PAYLOAD)

    response = client.put(
        f"/classes/{class_id}/quizzes/{quiz['quiz_id']}",
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"

    legacy = {**payload, "base_version": 1}
    legacy_response = client.put(
        f"/classes/{class_id}/quizzes/{quiz['quiz_id']}",
        json=legacy,
    )
    assert legacy_response.status_code == 422
    assert legacy_response.json()["error"]["code"] == "request_validation_error"


def test_readding_collaborator_preserves_share_and_revocation_history(
    collaboration_client,
) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}/collaborators"
    payload = {"email": "editor@example.com", "permission": "EDITOR"}

    assert client.post(path, json=payload).status_code == 201
    assert client.delete(f"{path}/{editor.account_id}").status_code == 204
    assert client.post(path, json=payload).status_code == 201

    with client.app.state.database.session_factory() as db:
        actions = [
            event.action
            for event in db.query(QuizCollaboratorEvent)
            .filter_by(quiz_id=quiz["quiz_id"], account_id=editor.account_id)
            .order_by(QuizCollaboratorEvent.event_id)
        ]

    assert actions == [
        CollaboratorEventType.SHARED,
        CollaboratorEventType.REVOKED,
        CollaboratorEventType.SHARED,
    ]


def test_duplicate_and_owner_collaborators_are_rejected(
    collaboration_client,
) -> None:
    client, class_id, _, _, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"

    first = client.post(
        f"{path}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )
    assert first.status_code == 201
    duplicate = client.post(
        f"{path}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "already_quiz_collaborator"

    owner = client.post(
        f"{path}/collaborators",
        json={"email": "owner@example.com", "permission": "EDITOR"},
    )
    assert owner.status_code == 409
    assert owner.json()["error"]["code"] == "quiz_owner_cannot_collaborate"
