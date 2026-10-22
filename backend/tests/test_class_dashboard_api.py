from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.classes import (
    Class,
    ClassRole,
    ClassMembership,
)


@pytest.fixture
def dashboard_client() -> Iterator[tuple[TestClient, dict[str, CurrentAccount], int]]:
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
            accounts = {
                name: Account(
                    auth0_sub=f"auth0|{name}",
                    email=f"{name}@gettysburg.edu",
                    display_name=display_name,
                    account_type="ADMINISTRATOR" if name == "global" else None,
                )
                for name, display_name in {
                    "owner": "Owner",
                    "member": "Member",
                    "nonmember": "Nonmember",
                    "global": "Global Admin",
                    "amy": "Amy Student",
                    "zoe": "Zoe Student",
                }.items()
            }
            db.add_all(accounts.values())
            db.flush()
            class_ = Class(
                name="CS 440 Fall 2026",
                created_by_id=accounts["owner"].account_id,
                join_code="DASH0001",
            )
            db.add(class_)
            db.flush()
            db.add_all(
                [
                    ClassMembership(
                        class_id=class_.class_id,
                        account_id=accounts["owner"].account_id,
                        role=ClassRole.ORGANIZER,
                    ),
                    *(
                        ClassMembership(
                            class_id=class_.class_id,
                            account_id=accounts[name].account_id,
                        )
                        for name in ("member", "amy", "zoe")
                    ),
                ]
            )
            db.commit()
            identities = {
                name: CurrentAccount(
                    account_id=model.account_id,
                    role=(
                        AccountRole.ADMIN if name == "global" else AccountRole.USER
                    ),
                    is_active=True,
                )
                for name, model in accounts.items()
            }
            class_id = class_.class_id

        app.dependency_overrides[get_active_account] = lambda: identities["owner"]
        yield client, identities, class_id


def act_as(client: TestClient, identity: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: identity


def test_class_organizer_dashboard_returns_real_class_and_roster_data(
    dashboard_client,
) -> None:
    client, _, class_id = dashboard_client

    response = client.get(f"/classes/{class_id}/dashboard")

    assert response.status_code == 200
    body = response.json()
    assert body["class_name"] == "CS 440 Fall 2026"
    assert body["current_user_role"] == "ORGANIZER"
    assert body["active_member_count"] == 4
    assert [student["display_name"] for student in body["students"]] == [
        "Amy Student",
        "Member",
        "Zoe Student",
    ]
    assert body["dependency"] == {
        "is_complete": False,
        "blocked_by": [
            "task_5_quiz_class_association",
            "task_6_class_sessions",
        ],
    }


def test_member_gets_basic_dashboard_but_not_roster_wide_grades(
    dashboard_client,
) -> None:
    client, identities, class_id = dashboard_client
    act_as(client, identities["member"])

    dashboard = client.get(f"/classes/{class_id}/dashboard")
    students = client.get(f"/classes/{class_id}/students")

    assert dashboard.status_code == 200
    assert dashboard.json()["current_user_role"] == "MEMBER"
    assert dashboard.json()["students"] is None
    assert students.status_code == 403
    assert students.json()["error"]["code"] == "not_class_organizer"


def test_member_can_access_paginated_quiz_and_session_contracts(
    dashboard_client,
) -> None:
    client, identities, class_id = dashboard_client
    act_as(client, identities["member"])

    quizzes = client.get(
        f"/classes/{class_id}/quizzes?page=2&page_size=5&sort=title&order=asc"
    )
    sessions = client.get(
        f"/classes/{class_id}/sessions?page=3&page_size=10&sort=started_at"
    )

    assert quizzes.status_code == 200
    assert quizzes.json()["pagination"] == {
        "page": 2,
        "page_size": 5,
        "total_items": 0,
        "total_pages": 0,
    }
    assert sessions.status_code == 200
    assert sessions.json()["pagination"]["page"] == 3
    assert not quizzes.json()["dependency"]["is_complete"]
    assert not sessions.json()["dependency"]["is_complete"]


def test_student_roster_supports_sorting_and_pagination(dashboard_client) -> None:
    client, _, class_id = dashboard_client

    first = client.get(
        f"/classes/{class_id}/students?page=1&page_size=2&sort=name&order=asc"
    )
    second = client.get(
        f"/classes/{class_id}/students?page=2&page_size=2&sort=name&order=asc"
    )

    assert first.status_code == 200
    assert [row["display_name"] for row in first.json()["items"]] == [
        "Amy Student",
        "Member",
    ]
    assert [row["display_name"] for row in second.json()["items"]] == [
        "Zoe Student"
    ]
    assert first.json()["pagination"]["total_items"] == 3
    assert first.json()["pagination"]["total_pages"] == 2


def test_global_admin_can_access_students_without_membership(dashboard_client) -> None:
    client, identities, class_id = dashboard_client
    act_as(client, identities["global"])

    dashboard = client.get(f"/classes/{class_id}/dashboard")
    students = client.get(f"/classes/{class_id}/students")

    assert dashboard.status_code == 200
    assert dashboard.json()["is_global_admin"] is True
    assert dashboard.json()["current_user_role"] is None
    assert students.status_code == 200


def test_nonmember_cannot_discover_class(dashboard_client) -> None:
    client, identities, class_id = dashboard_client
    act_as(client, identities["nonmember"])

    for suffix in ("dashboard", "quizzes", "sessions", "students"):
        response = client.get(f"/classes/{class_id}/{suffix}")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "class_not_found"


def test_empty_archived_class_is_supported(dashboard_client) -> None:
    client, identities, _ = dashboard_client
    with client.app.state.database.session_factory() as db:
        archived = Class(
            name="Archived Empty Class",
            created_by_id=identities["global"].account_id,
            join_code=None,
            joining_open=False,
            archived_at=datetime.now(UTC).replace(tzinfo=None),
        )
        db.add(archived)
        db.commit()
        archived_id = archived.class_id
    act_as(client, identities["global"])

    dashboard = client.get(f"/classes/{archived_id}/dashboard")
    students = client.get(f"/classes/{archived_id}/students")

    assert dashboard.status_code == 200
    assert dashboard.json()["is_archived"] is True
    assert dashboard.json()["active_member_count"] == 0
    assert dashboard.json()["active_sessions"] == []
    assert students.status_code == 200
    assert students.json()["items"] == []
    assert students.json()["pagination"]["total_pages"] == 0


def test_student_listing_has_constant_query_count(dashboard_client) -> None:
    client, _, class_id = dashboard_client
    statements: list[str] = []

    def record_query(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    engine = client.app.state.database.engine
    event.listen(engine, "before_cursor_execute", record_query)
    try:
        response = client.get(f"/classes/{class_id}/students")
    finally:
        event.remove(engine, "before_cursor_execute", record_query)

    assert response.status_code == 200
    selects = [
        statement
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
    ]
    assert len(selects) <= 4


@pytest.mark.parametrize(
    "query",
    ["page=0", "page_size=0", "page_size=101", "sort=unknown", "order=sideways"],
)
def test_invalid_pagination_and_sorting_are_rejected(
    dashboard_client, query: str
) -> None:
    client, _, class_id = dashboard_client

    response = client.get(f"/classes/{class_id}/students?{query}")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
