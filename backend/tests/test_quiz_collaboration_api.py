from collections.abc import Iterator
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentAccount, get_active_account
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
