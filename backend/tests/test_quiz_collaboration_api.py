from collections.abc import Iterator
from copy import deepcopy
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth import CurrentAccount, get_active_account
from app.api.routes import quiz_editing_live
from app.config import Settings
from app.database import Base
from app.live.protocol import CloseCode
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.classes import (
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    MembershipStatus,
)
from app.models.quiz import (
    CollaboratorEventType,
    QuizCollaborator,
    QuizCollaboratorEvent,
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


def _new_question_payload(text: str) -> dict:
    payload = _question_payload(1, text)
    payload.pop("expected_revision")
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


def test_append_question_does_not_block_another_question_save(
    collaboration_client,
) -> None:
    client, class_id, owner, editor, _ = collaboration_client
    payload = deepcopy(QUIZ_PAYLOAD)
    payload["questions"].append(_new_question_payload("Second question?"))
    created = client.post(f"/classes/{class_id}/quizzes", json=payload).json()
    path = f"/classes/{class_id}/quizzes/{created['quiz_id']}"
    second = created["version"]["questions"][1]
    client.post(
        f"{path}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )

    appended = client.post(
        f"{path}/questions",
        json=_new_question_payload("Owner appended a third"),
    )
    assert appended.status_code == 201
    assert appended.json()["question"]["question_order"] == 3

    client.app.dependency_overrides[get_active_account] = lambda: editor
    edited = client.patch(
        f"{path}/questions/{second['question_id']}",
        json=_question_payload(second["revision"], "Editor saved question two"),
    )
    assert edited.status_code == 200

    client.app.dependency_overrides[get_active_account] = lambda: owner
    current = client.get(path).json()
    assert [q["question_text"] for q in current["version"]["questions"]] == [
        "Which answer?",
        "Editor saved question two",
        "Owner appended a third",
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


def test_published_question_ids_map_only_to_the_direct_successor_draft(
    collaboration_client,
) -> None:
    client, class_id, _, _, _ = collaboration_client
    payload = deepcopy(QUIZ_PAYLOAD)
    payload["questions"].append(_new_question_payload("Second question?"))
    quiz = client.post(f"/classes/{class_id}/quizzes", json=payload).json()
    base = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    published = client.post(
        f"{base}/publish",
        json={"expected_revision": quiz["revision"]},
    ).json()
    first, second = published["version"]["questions"]

    # This first save clones the published version, changing every question ID.
    changed_second = client.patch(
        f"{base}/questions/{second['question_id']}",
        json=_question_payload(second["revision"], "Changed in the new draft"),
    )
    assert changed_second.status_code == 200

    # A second editor still holding the immediately-published first-question
    # ID can save an untouched question; the server maps it by stable order.
    changed_first = client.patch(
        f"{base}/questions/{first['question_id']}",
        json=_question_payload(first["revision"], "Mapped into the new draft"),
    )
    assert changed_first.status_code == 200
    assert changed_first.json()["question"]["question_id"] != first["question_id"]

    # The old ID cannot overwrite the question that changed during cloning.
    stale_second = client.patch(
        f"{base}/questions/{second['question_id']}",
        json=_question_payload(second["revision"], "Must not overwrite"),
    )
    assert stale_second.status_code == 409
    assert stale_second.json()["error"]["code"] == "question_edit_conflict"


def test_stale_published_id_cannot_overwrite_replaced_question_at_same_order(
    collaboration_client,
) -> None:
    client, class_id, _, _, _ = collaboration_client
    quiz = _create(client, class_id)
    base = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    published = client.post(
        f"{base}/publish",
        json={"expected_revision": quiz["revision"]},
    ).json()
    old_question = published["version"]["questions"][0]

    replacement = _edit_payload(published["revision"], "Rebuilt draft")
    replacement["questions"][0]["question_text"] = "A different question"
    rebuilt = client.put(base, json=replacement)
    assert rebuilt.status_code == 200
    assert rebuilt.json()["version"]["questions"][0]["revision"] == 1

    stale = client.patch(
        f"{base}/questions/{old_question['question_id']}",
        json=_question_payload(old_question["revision"], "Must not overwrite"),
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "question_edit_conflict"
    current = client.get(base).json()
    assert current["version"]["questions"][0]["question_text"] == (
        "A different question"
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


def test_default_time_save_is_atomic_and_broadcasts_specific_event(
    collaboration_client,
    monkeypatch,
) -> None:
    client, class_id, owner, _, _ = collaboration_client
    quiz = _create(client, class_id)
    base = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    inherited = quiz["version"]["questions"][0]
    explicit = client.post(base + "/questions", json=_new_question_payload("Explicit"))
    assert explicit.status_code == 201
    explicit_question = explicit.json()["question"]
    monkeypatch.setattr(
        quiz_editing_live,
        "authenticate_token",
        lambda db, settings, token: owner,
    )

    with client.websocket_connect(f"/ws/quizzes/{quiz['quiz_id']}") as socket:
        socket.send_json({"type": "auth", "token": "test-token"})
        socket.receive_json()
        saved = client.patch(
            base + "/default-time",
            json={
                "time_limit_seconds": 45,
                "question_ids": [inherited["question_id"]],
            },
        )
        assert saved.status_code == 200
        event = socket.receive_json()

    body = saved.json()
    assert body["time_limit_seconds"] == 45
    assert body["questions"][0]["time_limit_seconds"] == 45
    assert body["questions"][0]["revision"] == 2
    current = client.get(base).json()
    questions = current["version"]["questions"]
    assert questions[0]["time_limit_seconds"] == 45
    assert questions[1]["question_id"] == explicit_question["question_id"]
    assert questions[1]["time_limit_seconds"] == 30
    assert event["type"] == "quiz_default_time_updated"
    assert event["time_limit_seconds"] == 45
    assert [item["question_id"] for item in event["questions"]] == [
        inherited["question_id"]
    ]


def test_deactivated_editor_is_closed_before_later_broadcast(
    collaboration_client,
    monkeypatch,
) -> None:
    client, class_id, owner, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    question = quiz["version"]["questions"][0]
    base = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    client.post(
        f"{base}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )
    monkeypatch.setattr(
        quiz_editing_live,
        "authenticate_token",
        lambda db, settings, token: editor,
    )

    with client.websocket_connect(f"/ws/quizzes/{quiz['quiz_id']}") as socket:
        socket.send_json({"type": "auth", "token": "test-token"})
        socket.receive_json()
        with client.app.state.database.session_factory() as db:
            stored = db.get(Account, editor.account_id)
            stored.is_active = False
            db.commit()

        client.app.dependency_overrides[get_active_account] = lambda: owner
        saved = client.patch(
            f"{base}/questions/{question['question_id']}",
            json=_question_payload(1, "Do not broadcast to inactive editor"),
        )
        assert saved.status_code == 200
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()

    assert closed.value.code == CloseCode.FORBIDDEN


def test_revoked_editor_ping_rechecks_access_without_waiting_for_an_edit(
    collaboration_client,
    monkeypatch,
) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    base = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    client.post(
        f"{base}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )
    monkeypatch.setattr(
        quiz_editing_live,
        "authenticate_token",
        lambda db, settings, token: editor,
    )

    with client.websocket_connect(f"/ws/quizzes/{quiz['quiz_id']}") as socket:
        socket.send_json({"type": "auth", "token": "test-token"})
        socket.receive_json()
        # Change the database directly so this test exercises ping-time
        # reauthorization rather than the DELETE route's proactive close.
        with client.app.state.database.session_factory() as db:
            collaborator = db.get(
                QuizCollaborator,
                (quiz["quiz_id"], editor.account_id),
            )
            collaborator.revoked_at = datetime.now(UTC).replace(tzinfo=None)
            db.commit()

        socket.send_json({"type": "ping"})
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()

    assert closed.value.code == CloseCode.FORBIDDEN


def test_archiving_advances_revision_and_closes_editor_sockets(
    collaboration_client,
    monkeypatch,
) -> None:
    client, class_id, owner, _, _ = collaboration_client
    quiz = _create(client, class_id)
    monkeypatch.setattr(
        quiz_editing_live,
        "authenticate_token",
        lambda db, settings, token: owner,
    )

    with client.websocket_connect(f"/ws/quizzes/{quiz['quiz_id']}") as socket:
        socket.send_json({"type": "auth", "token": "test-token"})
        socket.receive_json()
        archived = client.patch(f"/quizzes/{quiz['quiz_id']}/archive")
        assert archived.status_code == 200
        assert archived.json()["status"] == "ARCHIVED"
        assert archived.json()["revision"] == quiz["revision"] + 1
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()

    assert closed.value.code == CloseCode.FORBIDDEN


def test_question_append_broadcasts_without_reloading_other_questions(
    collaboration_client,
    monkeypatch,
) -> None:
    client, class_id, owner, _, _ = collaboration_client
    quiz = _create(client, class_id)
    monkeypatch.setattr(
        quiz_editing_live,
        "authenticate_token",
        lambda db, settings, token: owner,
    )

    with client.websocket_connect(f"/ws/quizzes/{quiz['quiz_id']}") as socket:
        socket.send_json({"type": "auth", "token": "test-token"})
        socket.receive_json()
        saved = client.post(
            f"/classes/{class_id}/quizzes/{quiz['quiz_id']}/questions",
            json=_new_question_payload("Broadcast appended question"),
        )
        assert saved.status_code == 201
        event = socket.receive_json()

    assert event["type"] == "question_added"
    assert event["editor_account_id"] == owner.account_id
    assert event["question"]["question_text"] == "Broadcast appended question"
    assert event["question"]["question_order"] == 2


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


def test_class_quiz_list_names_active_collaborators(collaboration_client) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"

    def names() -> list[str]:
        listed = client.get(f"/classes/{class_id}/quizzes?mine=true")
        assert listed.status_code == 200
        return listed.json()["items"][0]["collaborator_names"]

    assert names() == []
    client.post(
        f"{path}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )
    assert names() == ["Editor"]

    # The editor sees the quiz too, but not their own name in the list.
    owner = client.app.dependency_overrides[get_active_account]()
    client.app.dependency_overrides[get_active_account] = lambda: editor
    assert names() == []
    client.app.dependency_overrides[get_active_account] = lambda: owner

    client.delete(f"{path}/collaborators/{editor.account_id}")
    assert names() == []


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


# --- Attribution: creator and editor names on the quiz response ---------------


def _share(client: TestClient, path: str) -> None:
    shared = client.post(
        f"{path}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )
    assert shared.status_code == 201


def _add_organizer(
    client: TestClient, class_id: int, *, faculty: bool = False
) -> CurrentAccount:
    with client.app.state.database.session_factory() as db:
        organizer = Account(
            auth0_sub="auth0|organizer",
            email="organizer@example.com",
            display_name="Organizer",
            is_active=True,
            account_type="ADMINISTRATOR" if faculty else None,
        )
        db.add(organizer)
        db.flush()
        db.add(
            ClassMembership(
                class_id=class_id,
                account_id=organizer.account_id,
                role=ClassRole.ORGANIZER,
                status=MembershipStatus.ACTIVE,
                joined_via=JoinedVia.CODE,
            )
        )
        db.commit()
        role = AccountRole.ADMIN if faculty else AccountRole.USER
        return CurrentAccount(organizer.account_id, role, True)


@pytest.mark.parametrize("faculty", [True, False])
def test_class_organizer_editing_requires_active_faculty(
    collaboration_client, faculty, monkeypatch
) -> None:
    client, class_id, _, _, _ = collaboration_client
    quiz = _create(client, class_id)
    organizer = _add_organizer(client, class_id, faculty=faculty)
    client.app.dependency_overrides[get_active_account] = lambda: organizer
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    detail = client.get(path).json()
    assert detail["visibility"] == "PRIVATE"
    assert detail["can_edit"] is faculty

    edit = client.put(path, json=_edit_payload(quiz["revision"]))
    assert edit.status_code == (200 if faculty else 403), edit.text
    if faculty:
        assert client.post(
            f"{path}/publish", json={"expected_revision": edit.json()["revision"]}
        ).json()["error"]["code"] == "quiz_publish_denied"

    socket_path = f"/ws/quizzes/{quiz['quiz_id']}"
    monkeypatch.setattr(
        quiz_editing_live, "authenticate_token", lambda db, settings, token: organizer
    )
    with client.websocket_connect(socket_path) as socket:
        socket.send_json({"type": "auth", "token": "test-token"})
        if faculty:
            assert socket.receive_json()["type"] == "quiz_editor_state"
        else:
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.reason == "quiz_not_found"


def _assert_no_emails(body: dict) -> None:
    assert "@" not in str(
        {"author_name": body["author_name"], "collaborators": body["collaborators"]}
    )
    for collaborator in body["collaborators"]:
        assert set(collaborator) == {"account_id", "display_name"}


def test_attribution_is_shown_to_owner_collaborator_and_organizer(
    collaboration_client,
) -> None:
    client, class_id, owner, editor, _ = collaboration_client
    organizer = _add_organizer(client, class_id)
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    _share(client, path)

    expected = [{"account_id": editor.account_id, "display_name": "Editor"}]
    for viewer in (owner, editor, organizer):
        client.app.dependency_overrides[get_active_account] = lambda v=viewer: v
        response = client.get(path)
        assert response.status_code == 200
        body = response.json()
        assert body["author_name"] == "Owner"
        assert body["collaborators"] == expected
        _assert_no_emails(body)


def test_attribution_is_on_create_save_and_publish_responses(
    collaboration_client,
) -> None:
    client, class_id, _, editor, _ = collaboration_client
    created = _create(client, class_id)
    assert created["author_name"] == "Owner"
    assert created["collaborators"] == []
    path = f"/classes/{class_id}/quizzes/{created['quiz_id']}"
    _share(client, path)

    saved = client.put(path, json=_edit_payload(created["revision"]))
    assert saved.status_code == 200
    assert saved.json()["collaborators"] == [
        {"account_id": editor.account_id, "display_name": "Editor"}
    ]
    _assert_no_emails(saved.json())


def test_outsider_gets_404_and_no_attribution(collaboration_client) -> None:
    client, class_id, _, _, outsider = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    _share(client, path)

    client.app.dependency_overrides[get_active_account] = lambda: outsider
    response = client.get(path)
    assert response.status_code == 404
    assert "Owner" not in response.text
    assert "Editor" not in response.text


def test_revoked_collaborator_is_not_credited(collaboration_client) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    _share(client, path)
    assert client.delete(f"{path}/collaborators/{editor.account_id}").status_code == 204

    assert client.get(path).json()["collaborators"] == []


@pytest.mark.parametrize("status", [MembershipStatus.REMOVED, MembershipStatus.LEFT])
def test_collaborator_no_longer_in_class_is_not_credited(
    collaboration_client, status
) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    _share(client, path)
    with client.app.state.database.session_factory() as db:
        membership = db.query(ClassMembership).filter_by(
            class_id=class_id, account_id=editor.account_id
        ).one()
        membership.status = status
        db.commit()

    body = client.get(path).json()
    assert body["author_name"] == "Owner"
    assert body["collaborators"] == []


def test_deactivated_collaborator_is_not_credited(collaboration_client) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    path = f"/classes/{class_id}/quizzes/{quiz['quiz_id']}"
    _share(client, path)
    with client.app.state.database.session_factory() as db:
        db.get(Account, editor.account_id).is_active = False
        db.commit()

    assert client.get(path).json()["collaborators"] == []


@pytest.mark.parametrize("change", ["removed", "left", "deactivated"])
def test_class_quiz_list_skips_collaborators_without_access(
    collaboration_client, change
) -> None:
    client, class_id, _, editor, _ = collaboration_client
    quiz = _create(client, class_id)
    _share(client, f"/classes/{class_id}/quizzes/{quiz['quiz_id']}")
    with client.app.state.database.session_factory() as db:
        if change == "deactivated":
            db.get(Account, editor.account_id).is_active = False
        else:
            db.query(ClassMembership).filter_by(
                class_id=class_id, account_id=editor.account_id
            ).one().status = (
                MembershipStatus.REMOVED if change == "removed" else MembershipStatus.LEFT
            )
        db.commit()

    listed = client.get(f"/classes/{class_id}/quizzes?mine=true")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["collaborator_names"] == []


def _suggest(client: TestClient, class_id: int, quiz_id: int, q: str):
    return client.get(
        f"/classes/{class_id}/quizzes/{quiz_id}/collaborator-suggestions",
        params={"q": q},
    )


def test_collaborator_suggestions_list_classmates_as_you_type(
    collaboration_client,
) -> None:
    client, class_id, owner, editor, outsider = collaboration_client
    quiz_id = _create(client, class_id)["quiz_id"]

    by_name = _suggest(client, class_id, quiz_id, "ed").json()
    by_email = _suggest(client, class_id, quiz_id, "editor@ex").json()

    assert by_name == [
        {
            "account_id": editor.account_id,
            "email": "editor@example.com",
            "display_name": "Editor",
            "is_collaborator": False,
        }
    ]
    assert by_email == by_name
    # Not the owner, and not people outside the class.
    assert _suggest(client, class_id, quiz_id, "ow").json() == []
    assert _suggest(client, class_id, quiz_id, "out").json() == []
    # One character searches too; only wildcards finds nothing.
    assert _suggest(client, class_id, quiz_id, "e").json() == by_name
    assert _suggest(client, class_id, quiz_id, "%%").json() == []


def test_collaborator_suggestions_list_the_class_a_page_at_a_time(
    collaboration_client,
) -> None:
    client, class_id, owner, editor, outsider = collaboration_client
    quiz_id = _create(client, class_id)["quiz_id"]
    path = f"/classes/{class_id}/quizzes/{quiz_id}/collaborator-suggestions"

    # An empty search lists the class (not the owner, not outsiders).
    assert [item["account_id"] for item in _suggest(client, class_id, quiz_id, "").json()] == [
        editor.account_id
    ]
    assert client.get(path, params={"limit": 1}).json()[0]["account_id"] == editor.account_id
    assert client.get(path, params={"limit": 1, "offset": 1}).json() == []
    for params in ({"limit": 0}, {"limit": 51}, {"offset": -1}):
        assert client.get(path, params=params).status_code == 422, params


def test_collaborator_suggestions_mark_current_editors(collaboration_client) -> None:
    client, class_id, owner, editor, outsider = collaboration_client
    quiz_id = _create(client, class_id)["quiz_id"]
    added = client.post(
        f"/classes/{class_id}/quizzes/{quiz_id}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )
    assert added.status_code == 201

    suggestions = _suggest(client, class_id, quiz_id, "ed").json()

    assert suggestions[0]["is_collaborator"] is True


def test_collaborator_suggestions_put_collaborators_first(collaboration_client) -> None:
    client, class_id, owner, editor, outsider = collaboration_client
    with client.app.state.database.session_factory() as db:
        aaron = Account(auth0_sub="auth0|aaron", email="aaron@example.com", display_name="Aaron")
        db.add(aaron)
        db.flush()
        db.add(ClassMembership(class_id=class_id, account_id=aaron.account_id))
        db.commit()
        aaron_id = aaron.account_id
    quiz_id = _create(client, class_id)["quiz_id"]

    def order(q=""):
        return [(i["account_id"], i["is_collaborator"]) for i in _suggest(client, class_id, quiz_id, q).json()]

    # Alphabetical while nobody is a collaborator...
    assert order() == [(aaron_id, False), (editor.account_id, False)]
    added = client.post(
        f"/classes/{class_id}/quizzes/{quiz_id}/collaborators",
        json={"email": "editor@example.com", "permission": "EDITOR"},
    )
    assert added.status_code == 201
    # ...then the collaborator comes first, also when searching.
    assert order() == [(editor.account_id, True), (aaron_id, False)]
    assert order("e") == [(editor.account_id, True)]
    assert order("a") == [(aaron_id, False)]


def test_only_the_owner_gets_collaborator_suggestions(collaboration_client) -> None:
    client, class_id, owner, editor, outsider = collaboration_client
    quiz_id = _create(client, class_id)["quiz_id"]

    client.app.dependency_overrides[get_active_account] = lambda: editor
    as_editor = _suggest(client, class_id, quiz_id, "ow")
    client.app.dependency_overrides[get_active_account] = lambda: outsider
    as_outsider = _suggest(client, class_id, quiz_id, "ed")

    assert as_editor.status_code == 403
    assert as_editor.json()["error"]["code"] == "collaborator_management_denied"
    assert as_outsider.status_code == 404
