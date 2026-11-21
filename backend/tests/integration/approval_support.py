"""An authenticated class on migrated MySQL for approval and live-session tests."""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import text

from app import auth
from app.auth import CurrentAccount, get_active_account
from app.models import Account, AccountRole, ClassMembership, ClassRole
from tests.test_accounts import PRIVATE_KEY, make_token


@dataclass(frozen=True)
class ApprovalClass:
    client: TestClient
    class_id: int
    accounts: dict[str, CurrentAccount]
    tokens: dict[str, str]

    @property
    def path(self) -> str:
        return f"/classes/{self.class_id}"

    def request(self, actor: str, method: str, path: str, *, status: int = 200, **kwargs) -> Response:
        response = self.client.request(
            method, path, headers={"Authorization": f"Bearer {self.tokens[actor]}"}, **kwargs
        )
        assert response.status_code == status, response.text
        return response

    def create_quiz(self, owner: str, payload: dict) -> dict:
        return self.request(
            owner, "POST", f"{self.path}/quizzes", json=payload, status=201
        ).json()

    def publish(self, owner: str, quiz: dict) -> dict:
        return self.request(
            owner, "POST", f"{self.path}/quizzes/{quiz['quiz_id']}/publish",
            json={"expected_revision": quiz["revision"]},
        ).json()

    def submit(self, actor: str, quiz: dict) -> dict:
        return self.request(
            actor, "POST", f"{self.path}/quiz-submissions", status=201,
            json={"quiz_version_id": quiz["version"]["quiz_version_id"]},
        ).json()

    def approve(self, submission: dict) -> None:
        self.request(
            "organizer", "PATCH", f"{self.path}/quiz-submissions/{submission['submission_id']}",
            json={"status": "APPROVED"},
        )

    def approve_quiz(self, owner: str, payload: dict) -> dict:
        quiz = self.publish(owner, self.create_quiz(owner, payload))
        self.approve(self.submit(owner, quiz))
        return quiz


@pytest.fixture
def approval_class(mysql_quiz_client, monkeypatch) -> ApprovalClass:
    client, _, _ = mysql_quiz_client
    app = client.app
    fake_jwks = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=PRIVATE_KEY.public_key())
    )
    monkeypatch.setattr(auth, "_jwks_client", lambda domain: fake_jwks)
    app.dependency_overrides.pop(get_active_account)

    accounts = {}
    tokens = {}
    organizers = {"organizer", "coorganizer"}
    with app.state.database.session_factory() as db:
        for name in ("organizer", "coorganizer", "owner", "submitter", "editor", "member"):
            model = Account(
                auth0_sub=f"test|{name}",
                email=f"{name}@test.invalid",
                display_name=name.title(),
                account_type="ADMINISTRATOR" if name in organizers else None,
            )
            db.add(model)
            db.flush()
            db.execute(
                text("INSERT INTO account_identity (auth0_sub, account_id) VALUES (:sub, :id)"),
                {"sub": model.auth0_sub, "id": model.account_id},
            )
            accounts[name] = CurrentAccount(
                model.account_id, AccountRole.ADMIN if name in organizers else AccountRole.USER, True
            )
            tokens[name] = make_token(sub=model.auth0_sub, audience=app.state.settings.auth0_audience)
        db.commit()

    created = client.post(
        "/classes", json={"name": "Approval and Results"},
        headers={"Authorization": f"Bearer {tokens['organizer']}"},
    )
    assert created.status_code == 201, created.text
    class_id = created.json()["class_id"]
    with app.state.database.session_factory() as db:
        for name, account in accounts.items():
            if name != "organizer":
                db.add(ClassMembership(
                    class_id=class_id,
                    account_id=account.account_id,
                    role=ClassRole.ORGANIZER if name in organizers else ClassRole.MEMBER,
                ))
        db.commit()
    return ApprovalClass(client, class_id, accounts, tokens)
