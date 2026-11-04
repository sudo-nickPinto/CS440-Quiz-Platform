"""V3 task 2: quizzes are created in, and visible only within, their class."""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

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
    MembershipStatus,
    Quiz,
    QuizStatus,
    QuizVersion,
    QuizVisibility,
)
from tests.test_quiz_api import QUIZ_PAYLOAD

# name -> (role, status) in the main class; None = not in it.
PEOPLE = {
    "prof": (ClassRole.ORGANIZER, MembershipStatus.ACTIVE),
    "amy": (ClassRole.MEMBER, MembershipStatus.ACTIVE),
    "zoe": (ClassRole.MEMBER, MembershipStatus.ACTIVE),
    "invited": (ClassRole.MEMBER, MembershipStatus.INVITED),
    "left": (ClassRole.MEMBER, MembershipStatus.LEFT),
    "removed": (ClassRole.MEMBER, MembershipStatus.REMOVED),
    "outsider": None,
}


@pytest.fixture
def classes() -> Iterator[tuple[TestClient, dict[str, CurrentAccount], dict]]:
    """CS 440 with everyone in PEOPLE, plus an Other class (the outsider
    organizes it, Amy is a member) and an archived class Amy is in."""
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
                    display_name=name.title(),
                )
                for name in PEOPLE
            }
            db.add_all(accounts.values())
            db.flush()
            ids = {name: model.account_id for name, model in accounts.items()}

            main = Class(name="CS 440", created_by_id=ids["prof"], join_code="QUIZ0001")
            other = Class(
                name="Other", created_by_id=ids["outsider"], join_code="QUIZ0002"
            )
            archived = Class(
                name="Old",
                created_by_id=ids["prof"],
                join_code=None,
                joining_open=False,
                archived_at=datetime.now(UTC).replace(tzinfo=None),
            )
            db.add_all([main, other, archived])
            db.flush()
            for name, membership in PEOPLE.items():
                if membership is not None:
                    role, status = membership
                    db.add(
                        ClassMembership(
                            class_id=main.class_id,
                            account_id=ids[name],
                            role=role,
                            status=status,
                        )
                    )
            db.add_all(
                [
                    ClassMembership(
                        class_id=other.class_id,
                        account_id=ids["outsider"],
                        role=ClassRole.ORGANIZER,
                    ),
                    ClassMembership(class_id=other.class_id, account_id=ids["amy"]),
                    ClassMembership(class_id=archived.class_id, account_id=ids["amy"]),
                ]
            )
            db.commit()
            data = {
                "main": main.class_id,
                "other": other.class_id,
                "archived": archived.class_id,
                "ids": ids,
            }

        identities = {
            name: CurrentAccount(ids[name], AccountRole.USER, True) for name in PEOPLE
        }
        act_as(client, identities["amy"])
        yield client, identities, data


def act_as(client: TestClient, identity: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: identity


def create(client: TestClient, class_id: int, title: str = "MVP Quiz") -> dict:
    response = client.post(
        f"/classes/{class_id}/quizzes", json={**QUIZ_PAYLOAD, "title": title}
    )
    assert response.status_code == 201, response.json()
    return response.json()


# Creating


@pytest.mark.parametrize("name", ["amy", "prof"])
def test_student_member_and_faculty_organizer_can_create_quizzes(classes, name) -> None:
    client, identities, data = classes
    act_as(client, identities[name])

    body = create(client, data["main"])

    assert body["class_id"] == data["main"]
    assert body["author_id"] == identities[name].account_id
    assert body["status"] == "DRAFT"
    assert body["visibility"] == "PRIVATE"
    assert body["version"]["version_number"] == 1
    assert body["version"]["published_at"] is None


def test_a_new_draft_cannot_be_hosted(classes) -> None:
    client, identities, data = classes
    act_as(client, identities["prof"])
    quiz = create(client, data["main"])

    response = client.post(f"/quizzes/{quiz['quiz_id']}/sessions")

    assert response.status_code == 409


@pytest.mark.parametrize("name", ["invited", "left", "removed", "outsider"])
def test_people_without_active_membership_cannot_create(classes, name) -> None:
    client, identities, data = classes
    act_as(client, identities[name])

    response = client.post(f"/classes/{data['main']}/quizzes", json=QUIZ_PAYLOAD)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "class_not_found"


def test_unknown_class_is_not_found(classes) -> None:
    client, _, _ = classes

    response = client.post("/classes/9999/quizzes", json=QUIZ_PAYLOAD)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "class_not_found"


def test_archived_class_cannot_get_new_quizzes(classes) -> None:
    client, _, data = classes

    response = client.post(f"/classes/{data['archived']}/quizzes", json=QUIZ_PAYLOAD)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "class_archived"


def test_the_global_create_route_is_gone(classes) -> None:
    client, _, _ = classes

    assert client.post("/quizzes", json=QUIZ_PAYLOAD).status_code == 405


def test_no_quiz_creation_permission_flag_exists() -> None:
    assert "can_create_quiz" not in Account.__table__.c
    assert "can_create_quiz" not in ClassMembership.__table__.c


# Listing a class's quizzes


def test_organizer_lists_every_quiz_in_the_class(classes) -> None:
    client, identities, data = classes
    create(client, data["main"], "Amy's quiz")
    create(client, data["other"], "Amy's other-class quiz")
    act_as(client, identities["prof"])
    create(client, data["main"], "Prof's quiz")

    body = client.get(f"/classes/{data['main']}/quizzes").json()

    assert [item["title"] for item in body["items"]] == ["Prof's quiz", "Amy's quiz"]
    assert [item["author_name"] for item in body["items"]] == ["Prof", "Amy"]
    assert body["items"][0]["question_count"] == 2
    assert body["items"][0]["version_number"] == 1
    assert body["pagination"] == {
        "page": 1,
        "page_size": 25,
        "total_items": 2,
        "total_pages": 1,
    }


def test_members_list_only_their_own_quizzes(classes) -> None:
    client, identities, data = classes
    create(client, data["main"], "Amy's quiz")
    act_as(client, identities["prof"])
    create(client, data["main"], "Prof's quiz")

    act_as(client, identities["amy"])
    amy = client.get(f"/classes/{data['main']}/quizzes").json()
    act_as(client, identities["zoe"])
    zoe = client.get(f"/classes/{data['main']}/quizzes").json()

    assert [item["title"] for item in amy["items"]] == ["Amy's quiz"]
    assert zoe["items"] == []
    assert zoe["pagination"]["total_items"] == 0


def test_class_quiz_list_pages(classes) -> None:
    client, _, data = classes
    for title in ("First", "Second", "Third"):
        create(client, data["main"], title)

    first = client.get(f"/classes/{data['main']}/quizzes?page=1&page_size=2").json()
    second = client.get(f"/classes/{data['main']}/quizzes?page=2&page_size=2").json()

    assert [item["title"] for item in first["items"]] == ["Third", "Second"]
    assert [item["title"] for item in second["items"]] == ["First"]
    assert first["pagination"]["total_pages"] == 2


@pytest.mark.parametrize("name", ["invited", "left", "removed", "outsider"])
def test_people_without_active_membership_cannot_list(classes, name) -> None:
    client, identities, data = classes
    act_as(client, identities[name])

    response = client.get(f"/classes/{data['main']}/quizzes")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "class_not_found"


# Reading one quiz


@pytest.mark.parametrize("name", ["amy", "prof"])
def test_owner_and_organizer_can_read_the_quiz(classes, name) -> None:
    client, identities, data = classes
    quiz = create(client, data["main"])
    act_as(client, identities[name])

    by_class = client.get(f"/classes/{data['main']}/quizzes/{quiz['quiz_id']}")
    direct = client.get(f"/quizzes/{quiz['quiz_id']}")

    assert by_class.status_code == 200
    assert by_class.json()["version"]["title"] == "MVP Quiz"
    assert direct.status_code == 200


def test_classmate_cannot_read_someone_elses_quiz(classes) -> None:
    client, identities, data = classes
    quiz = create(client, data["main"])
    act_as(client, identities["zoe"])

    by_class = client.get(f"/classes/{data['main']}/quizzes/{quiz['quiz_id']}")
    direct = client.get(f"/quizzes/{quiz['quiz_id']}")

    assert by_class.status_code == 404
    assert by_class.json()["error"]["code"] == "quiz_not_found"
    assert direct.status_code == 404


@pytest.mark.parametrize("name", ["invited", "left", "removed", "outsider"])
def test_people_outside_the_class_cannot_read(classes, name) -> None:
    client, identities, data = classes
    quiz = create(client, data["main"])
    act_as(client, identities[name])

    by_class = client.get(f"/classes/{data['main']}/quizzes/{quiz['quiz_id']}")
    direct = client.get(f"/quizzes/{quiz['quiz_id']}")

    assert by_class.status_code == 404
    assert by_class.json()["error"]["code"] == "class_not_found"
    assert direct.status_code == 404
    assert direct.json()["error"]["code"] == "quiz_not_found"


def test_quiz_is_not_reachable_through_another_class(classes) -> None:
    client, _, data = classes
    quiz = create(client, data["main"])

    # Amy is in both classes, but the quiz belongs to CS 440 only.
    response = client.get(f"/classes/{data['other']}/quizzes/{quiz['quiz_id']}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "quiz_not_found"


# The caller's own quizzes: GET /quizzes


def test_my_quizzes_cover_every_active_class(classes) -> None:
    client, _, data = classes
    create(client, data["main"], "In CS 440")
    create(client, data["other"], "In Other")

    titles = [item["title"] for item in client.get("/quizzes").json()]

    assert titles == ["In Other", "In CS 440"]


def test_leaving_a_class_hides_its_quizzes_from_the_owner(classes) -> None:
    client, identities, data = classes
    quiz = create(client, data["main"])
    with client.app.state.database.session_factory() as db:
        membership = (
            db.query(ClassMembership)
            .filter_by(class_id=data["main"], account_id=identities["amy"].account_id)
            .one()
        )
        membership.status = MembershipStatus.REMOVED
        db.commit()

    assert client.get("/quizzes").json() == []
    assert client.get(f"/quizzes/{quiz['quiz_id']}").status_code == 404


def test_quiz_from_before_classes_is_visible_only_to_its_owner(classes) -> None:
    client, identities, data = classes
    with client.app.state.database.session_factory() as db:
        legacy = Quiz(
            author_id=identities["amy"].account_id,
            status=QuizStatus.PUBLISHED,
            visibility=QuizVisibility.PUBLIC,
            versions=[
                QuizVersion(
                    version_number=1,
                    title="Legacy",
                    published_at=datetime.now(UTC).replace(tzinfo=None),
                )
            ],
        )
        db.add(legacy)
        db.commit()
        quiz_id = legacy.quiz_id

    mine = client.get(f"/quizzes/{quiz_id}")
    act_as(client, identities["prof"])
    theirs = client.get(f"/quizzes/{quiz_id}")

    assert mine.status_code == 200
    assert mine.json()["class_id"] is None
    assert theirs.status_code == 404


# No app-wide Admin authority (V3)


def as_admin(identity: CurrentAccount) -> CurrentAccount:
    return CurrentAccount(identity.account_id, AccountRole.ADMIN, True)


def test_admin_outside_the_class_gets_nothing(classes) -> None:
    client, identities, data = classes
    quiz = create(client, data["main"])
    act_as(client, as_admin(identities["outsider"]))

    created = client.post(f"/classes/{data['main']}/quizzes", json=QUIZ_PAYLOAD)
    listing = client.get(f"/classes/{data['main']}/quizzes")
    by_class = client.get(f"/classes/{data['main']}/quizzes/{quiz['quiz_id']}")
    direct = client.get(f"/quizzes/{quiz['quiz_id']}")

    assert [r.status_code for r in (created, listing, by_class, direct)] == [404] * 4
    assert listing.json()["error"]["code"] == "class_not_found"


def test_admin_who_is_a_plain_member_sees_only_their_own(classes) -> None:
    client, identities, data = classes
    quiz = create(client, data["main"])
    act_as(client, as_admin(identities["zoe"]))

    listing = client.get(f"/classes/{data['main']}/quizzes").json()
    detail = client.get(f"/quizzes/{quiz['quiz_id']}")

    assert listing["items"] == []
    assert detail.status_code == 404


def test_only_the_owner_can_archive(classes) -> None:
    client, identities, data = classes
    quiz = create(client, data["main"])
    act_as(client, as_admin(identities["prof"]))

    denied = client.patch(f"/quizzes/{quiz['quiz_id']}/archive")
    act_as(client, identities["amy"])
    archived = client.patch(f"/quizzes/{quiz['quiz_id']}/archive")

    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "quiz_access_denied"
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
