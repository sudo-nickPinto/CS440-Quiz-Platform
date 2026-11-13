"""Faculty granting and removing faculty status in the app (issue #116)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models import (
    Account,
    AccountRole,
    Class,
    ClassMembership,
    ClassRole,
    FacultyAccessAction,
    FacultyAccessEvent,
    MembershipStatus,
)


@pytest.fixture
def faculty_api() -> Iterator[tuple[TestClient, dict, dict]]:
    app = create_app(
        Settings(
            database_url="sqlite://",
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
        )
    )
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.database.engine)
        people = {
            # name: (email, account_type, is_active)
            "kim": ("kim@gettysburg.edu", "ADMINISTRATOR", True),
            "lee": ("lee@gettysburg.edu", "ADMINISTRATOR", True),
            "amy": ("Amy.Student@gettysburg.edu", None, True),
            "zed": ("zed@gettysburg.edu", "STUDENT", True),
            "gone": ("gone@gettysburg.edu", None, False),
        }
        with app.state.database.session_factory() as db:
            accounts = {
                name: Account(
                    auth0_sub=f"auth0|{name}",
                    email=email,
                    display_name=name.title(),
                    account_type=account_type,
                    is_active=is_active,
                )
                for name, (email, account_type, is_active) in people.items()
            }
            db.add_all(accounts.values())
            db.commit()
            ids = {name: account.account_id for name, account in accounts.items()}

        identities = {
            name: CurrentAccount(
                ids[name],
                AccountRole.ADMIN
                if people[name][1] == "ADMINISTRATOR"
                else AccountRole.USER,
                people[name][2],
            )
            for name in people
        }
        actor = {"value": identities["kim"]}
        app.dependency_overrides[get_active_account] = lambda: actor["value"]

        def act_as(name: str) -> None:
            actor["value"] = identities[name]

        yield client, ids, act_as
        app.dependency_overrides.clear()


def assert_error(response, status_code: int, code: str) -> None:
    assert response.status_code == status_code, response.json()
    assert response.json()["error"]["code"] == code


def account_type(client: TestClient, account_id: int) -> str | None:
    with client.app.state.database.session_factory() as db:
        return db.get(Account, account_id).account_type


def events(client: TestClient) -> list[tuple]:
    with client.app.state.database.session_factory() as db:
        return [
            (event.account_id, event.action, event.actor_id)
            for event in db.scalars(
                select(FacultyAccessEvent).order_by(FacultyAccessEvent.event_id)
            )
        ]


def test_faculty_list_shows_active_faculty_and_marks_me(faculty_api) -> None:
    client, ids, _ = faculty_api

    response = client.get("/faculty")

    assert response.status_code == 200
    body = response.json()
    assert [(person["display_name"], person["is_me"]) for person in body["faculty"]] == [
        ("Kim", True),
        ("Lee", False),
    ]
    # Set up in the database before this page existed: no grant on record.
    assert body["faculty"][0]["granted_at"] is None
    assert body["faculty"][0]["granted_by_name"] is None
    assert body["history"] == []


@pytest.mark.parametrize("name", ["amy", "zed"])
def test_non_faculty_cannot_see_or_change_faculty_access(faculty_api, name) -> None:
    client, ids, act_as = faculty_api
    act_as(name)

    assert_error(client.get("/faculty"), 403, "faculty_required")
    assert_error(
        client.post("/faculty", json={"email": "amy.student@gettysburg.edu"}),
        403,
        "faculty_required",
    )
    assert_error(client.delete(f"/faculty/{ids['lee']}"), 403, "faculty_required")
    assert account_type(client, ids["lee"]) == "ADMINISTRATOR"
    assert events(client) == []


def test_grant_by_email_is_case_insensitive_and_recorded(faculty_api) -> None:
    client, ids, _ = faculty_api

    response = client.post("/faculty", json={"email": "  AMY.student@Gettysburg.edu "})

    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["account_id"] == ids["amy"]
    assert body["granted_by_name"] == "Kim"
    assert body["granted_at"] is not None
    assert account_type(client, ids["amy"]) == "ADMINISTRATOR"
    assert events(client) == [(ids["amy"], FacultyAccessAction.GRANTED, ids["kim"])]

    listed = client.get("/faculty").json()
    amy = next(p for p in listed["faculty"] if p["account_id"] == ids["amy"])
    assert amy["granted_by_name"] == "Kim"
    assert listed["history"][0]["action"] == "GRANTED"
    assert listed["history"][0]["account_name"] == "Amy"
    assert listed["history"][0]["actor_name"] == "Kim"


def test_any_account_type_can_be_granted(faculty_api) -> None:
    client, ids, _ = faculty_api

    response = client.post("/faculty", json={"email": "zed@gettysburg.edu"})

    assert response.status_code == 201
    assert account_type(client, ids["zed"]) == "ADMINISTRATOR"


def test_newly_granted_faculty_can_grant_and_create_classes(faculty_api) -> None:
    client, ids, act_as = faculty_api
    client.post("/faculty", json={"email": "amy.student@gettysburg.edu"})

    # The role comes from the database on every request; in the real app the
    # next request after the grant already sees faculty status.
    with client.app.state.database.session_factory() as db:
        assert db.get(Account, ids["amy"]).account_type == "ADMINISTRATOR"
    client.app.dependency_overrides[get_active_account] = lambda: CurrentAccount(
        ids["amy"], AccountRole.ADMIN, True
    )

    assert client.get("/faculty").status_code == 200
    created = client.post("/classes", json={"name": "Amy's class"})
    assert created.status_code == 201, created.json()


@pytest.mark.parametrize(
    ("email", "status_code", "code"),
    [
        ("nobody@gettysburg.edu", 404, "account_not_found"),
        ("gone@gettysburg.edu", 409, "account_inactive"),
        ("lee@gettysburg.edu", 409, "already_faculty"),
        ("kim@gettysburg.edu", 409, "already_faculty"),
    ],
)
def test_grant_rejections_change_nothing(faculty_api, email, status_code, code) -> None:
    client, ids, _ = faculty_api

    assert_error(client.post("/faculty", json={"email": email}), status_code, code)
    assert events(client) == []


def test_grant_body_is_validated(faculty_api) -> None:
    client, _, _ = faculty_api

    assert client.post("/faculty", json={}).status_code == 422
    assert client.post("/faculty", json={"email": "a@b.c", "role": "x"}).status_code == 422
    assert_error(client.post("/faculty", json={"email": "      "}), 422, "email_required")


def test_revoke_removes_access_and_records_it(faculty_api) -> None:
    client, ids, _ = faculty_api

    response = client.delete(f"/faculty/{ids['lee']}")

    assert response.status_code == 204
    assert account_type(client, ids["lee"]) is None
    assert events(client) == [(ids["lee"], FacultyAccessAction.REVOKED, ids["kim"])]
    names = [p["display_name"] for p in client.get("/faculty").json()["faculty"]]
    assert names == ["Kim"]


def test_cannot_revoke_yourself_so_one_faculty_always_remains(faculty_api) -> None:
    client, ids, act_as = faculty_api
    client.delete(f"/faculty/{ids['lee']}")

    assert_error(client.delete(f"/faculty/{ids['kim']}"), 409, "cannot_revoke_self")
    assert account_type(client, ids["kim"]) == "ADMINISTRATOR"


@pytest.mark.parametrize("target", ["amy", "zed", "missing"])
def test_revoking_someone_without_faculty_access_is_not_found(faculty_api, target) -> None:
    client, ids, _ = faculty_api
    account_id = ids.get(target, 999_999)

    assert_error(client.delete(f"/faculty/{account_id}"), 404, "faculty_not_found")
    assert events(client) == []


def test_removed_faculty_loses_access_right_away(faculty_api) -> None:
    """Under the row lock the caller's own status is re-read from the
    database, so a token that still says ADMIN can't act after removal."""
    client, ids, act_as = faculty_api
    client.delete(f"/faculty/{ids['lee']}")

    act_as("lee")  # identity still claims ADMIN, but the account no longer is
    assert_error(
        client.post("/faculty", json={"email": "amy.student@gettysburg.edu"}),
        403,
        "faculty_required",
    )
    assert_error(client.delete(f"/faculty/{ids['kim']}"), 403, "faculty_required")
    assert account_type(client, ids["kim"]) == "ADMINISTRATOR"
    assert account_type(client, ids["amy"]) is None


def test_regrant_after_revoke_keeps_full_history(faculty_api) -> None:
    client, ids, _ = faculty_api

    client.delete(f"/faculty/{ids['lee']}")
    regrant = client.post("/faculty", json={"email": "lee@gettysburg.edu"})

    assert regrant.status_code == 201
    history = client.get("/faculty").json()["history"]
    assert [(item["action"], item["account_name"]) for item in history] == [
        ("GRANTED", "Lee"),
        ("REVOKED", "Lee"),
    ]


def add_class(client, ids, class_id, name, organizers, *, archived=False, others=()):
    """A class whose organizers are the given names; `others` adds
    (name, role, status) memberships."""
    from datetime import datetime

    with client.app.state.database.session_factory() as db:
        db.add(
            Class(
                class_id=class_id,
                name=name,
                created_by_id=ids[organizers[0]] if organizers else ids["kim"],
                # Archived classes have no join code and are closed to joining.
                join_code=None if archived else f"CODE{class_id:04d}",
                joining_open=not archived,
                archived_at=datetime(2026, 11, 1) if archived else None,
            )
        )
        for organizer in organizers:
            db.add(
                ClassMembership(
                    class_id=class_id,
                    account_id=ids[organizer],
                    role=ClassRole.ORGANIZER,
                )
            )
        for other, role, status in others:
            db.add(
                ClassMembership(
                    class_id=class_id,
                    account_id=ids[other],
                    role=role,
                    status=status,
                )
            )
        db.commit()


def test_cannot_remove_the_only_organizer_of_a_class(faculty_api) -> None:
    client, ids, _ = faculty_api
    add_class(client, ids, 1, "CS 440", ["lee"])

    response = client.delete(f"/faculty/{ids['lee']}")

    assert_error(response, 409, "last_organizer")
    error = response.json()["error"]
    assert "Lee is the only organizer of “CS 440”" in error["message"]
    assert error["details"] == {"classes": [{"class_id": 1, "name": "CS 440"}]}
    assert account_type(client, ids["lee"]) == "ADMINISTRATOR"
    assert events(client) == []


def test_names_every_class_they_alone_organize(faculty_api) -> None:
    client, ids, _ = faculty_api
    add_class(client, ids, 1, "CS 440", ["lee"])
    add_class(client, ids, 2, "Shared class", ["lee", "kim"])
    add_class(client, ids, 3, "Old class", ["lee"], archived=True)

    response = client.delete(f"/faculty/{ids['lee']}")

    assert_error(response, 409, "last_organizer")
    assert [c["name"] for c in response.json()["error"]["details"]["classes"]] == [
        "CS 440",
        "Old class",
    ]
    assert "“CS 440” and “Old class”" in response.json()["error"]["message"]


def test_a_non_faculty_co_organizer_does_not_count(faculty_api) -> None:
    """Organizer powers need faculty status, so an ORGANIZER membership held
    by a non-faculty account can't take over the class."""
    client, ids, _ = faculty_api
    add_class(
        client,
        ids,
        1,
        "CS 440",
        ["lee"],
        others=[("amy", ClassRole.ORGANIZER, MembershipStatus.ACTIVE)],
    )

    assert_error(client.delete(f"/faculty/{ids['lee']}"), 409, "last_organizer")


def test_former_and_invited_organizer_memberships_do_not_block(faculty_api) -> None:
    client, ids, _ = faculty_api
    with client.app.state.database.session_factory() as db:
        db.add(Class(class_id=1, name="Left class", created_by_id=ids["kim"], join_code="LEFT0001"))
        db.add(Class(class_id=2, name="Invited class", created_by_id=ids["kim"], join_code="INVT0001"))
        db.add_all(
            [
                ClassMembership(class_id=1, account_id=ids["kim"], role=ClassRole.ORGANIZER),
                ClassMembership(
                    class_id=1,
                    account_id=ids["lee"],
                    role=ClassRole.ORGANIZER,
                    status=MembershipStatus.LEFT,
                ),
                ClassMembership(class_id=2, account_id=ids["kim"], role=ClassRole.ORGANIZER),
                ClassMembership(
                    class_id=2,
                    account_id=ids["lee"],
                    role=ClassRole.ORGANIZER,
                    status=MembershipStatus.INVITED,
                ),
            ]
        )
        db.commit()

    assert client.delete(f"/faculty/{ids['lee']}").status_code == 204


def test_removed_organizer_keeps_membership_but_loses_organizer_powers(
    faculty_api,
) -> None:
    """With another faculty organizer in the class, removal is allowed; the
    membership stays but its organizer powers stop working."""
    client, ids, act_as = faculty_api
    add_class(client, ids, 1, "CS 440", ["lee", "kim"])

    assert client.delete(f"/faculty/{ids['lee']}").status_code == 204

    with client.app.state.database.session_factory() as db:
        membership = db.scalar(
            select(ClassMembership).where(ClassMembership.account_id == ids["lee"])
        )
        assert membership.role == ClassRole.ORGANIZER
    client.app.dependency_overrides[get_active_account] = lambda: CurrentAccount(
        ids["lee"], AccountRole.USER, True
    )
    rename = client.patch("/classes/1", json={"name": "Renamed"})
    assert_error(rename, 403, "not_class_organizer")
