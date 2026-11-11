"""V3 task 6: class dashboards show the caller's own and shared quizzes,
sort and page them, and never mix in another class's data."""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.quiz import Quiz, QuizVersion
from app.models.session import (
    LiveSession,
    LiveSessionStatus,
    Result,
    SessionParticipant,
)
from tests.class_quiz_helpers import publish_quiz
from tests.test_class_quizzes_api import (  # noqa: F401
    act_as,
    as_admin,
    classes,
    create,
)

BASE_TIME = datetime(2026, 11, 1, 12, tzinfo=UTC).replace(tzinfo=None)


def share(client, class_id: int, quiz_id: int, name: str) -> None:
    response = client.post(
        f"/classes/{class_id}/quizzes/{quiz_id}/collaborators",
        json={"email": f"{name}@gettysburg.edu", "permission": "EDITOR"},
    )
    assert response.status_code == 201, response.json()


def set_updated_at(client, quiz_id: int, when: datetime) -> None:
    with client.app.state.database.session_factory() as db:
        db.get(Quiz, quiz_id).updated_at = when
        db.commit()


def titles(body: dict) -> list[str]:
    return [item["title"] for item in body["items"]]


@pytest.fixture
def shared_quizzes(classes):
    """Amy owns one quiz, Zoe shares another with Amy and keeps a third
    private, and Amy owns a quiz in the Other class."""
    client, identities, data = classes
    main = data["main"]
    act_as(client, identities["amy"])
    amys = create(client, main, "Amy's quiz")
    other_class = create(client, data["other"], "Other class quiz")
    act_as(client, identities["zoe"])
    shared = create(client, main, "Zoe's shared quiz")
    private = create(client, main, "Zoe's private quiz")
    share(client, main, shared["quiz_id"], "amy")
    return client, identities, data, {
        "amy": amys,
        "shared": shared,
        "private": private,
        "other": other_class,
    }


def test_member_list_tags_owned_and_shared_quizzes(shared_quizzes) -> None:
    client, identities, data, _ = shared_quizzes
    act_as(client, identities["amy"])

    body = client.get(f"/classes/{data['main']}/quizzes?sort=title&order=asc").json()

    assert [(item["title"], item["my_access"]) for item in body["items"]] == [
        ("Amy's quiz", "OWNER"),
        ("Zoe's shared quiz", "EDITOR"),
    ]
    assert body["pagination"]["total_items"] == 2


def test_organizer_sees_all_but_mine_narrows_to_own_and_shared(
    shared_quizzes,
) -> None:
    client, identities, data, quizzes = shared_quizzes
    act_as(client, identities["zoe"])
    share(client, data["main"], quizzes["private"]["quiz_id"], "prof")
    act_as(client, identities["prof"])
    own = create(client, data["main"], "Prof's quiz")

    everything = client.get(f"/classes/{data['main']}/quizzes").json()
    mine = client.get(f"/classes/{data['main']}/quizzes?mine=true").json()

    assert everything["pagination"]["total_items"] == 4
    access = {item["title"]: item["my_access"] for item in everything["items"]}
    assert access["Amy's quiz"] is None
    assert {item["quiz_id"] for item in mine["items"]} == {
        own["quiz_id"],
        quizzes["private"]["quiz_id"],
    }


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("sort=title&order=asc", ["A", "B", "C"]),
        ("sort=title&order=desc", ["C", "B", "A"]),
        ("sort=updated_at&order=desc", ["B", "C", "A"]),
        ("sort=updated_at&order=asc", ["A", "C", "B"]),
    ],
)
def test_class_quiz_list_sorts(classes, query, expected) -> None:
    client, _, data = classes
    created = {title: create(client, data["main"], title) for title in "ACB"}
    for offset, title in enumerate("ACB"):
        set_updated_at(
            client, created[title]["quiz_id"], BASE_TIME + timedelta(hours=offset)
        )

    body = client.get(f"/classes/{data['main']}/quizzes?{query}").json()

    assert titles(body) == expected


def test_sorted_pages_do_not_overlap(classes) -> None:
    client, _, data = classes
    for title in ("Same", "Same", "Same"):
        create(client, data["main"], title)

    pages = [
        client.get(
            f"/classes/{data['main']}/quizzes?sort=title&page={page}&page_size=2"
        ).json()
        for page in (1, 2)
    ]

    ids = [item["quiz_id"] for page in pages for item in page["items"]]
    assert len(ids) == len(set(ids)) == 3
    assert pages[0]["pagination"]["total_pages"] == 2


@pytest.mark.parametrize(
    "query", ["sort=popularity", "order=sideways", "page=0", "page_size=101"]
)
def test_invalid_quiz_list_params_are_rejected(classes, query) -> None:
    client, _, data = classes

    response = client.get(f"/classes/{data['main']}/quizzes?{query}")

    assert response.status_code == 422


def test_dashboard_lists_my_quizzes_from_this_class_only(shared_quizzes) -> None:
    client, identities, data, quizzes = shared_quizzes
    act_as(client, identities["amy"])
    set_updated_at(client, quizzes["amy"]["quiz_id"], BASE_TIME)
    set_updated_at(client, quizzes["shared"]["quiz_id"], BASE_TIME + timedelta(1))

    body = client.get(f"/classes/{data['main']}/dashboard").json()

    assert [(item["title"], item["my_access"]) for item in body["my_quizzes"]] == [
        ("Zoe's shared quiz", "EDITOR"),
        ("Amy's quiz", "OWNER"),
    ]
    assert body["my_quiz_count"] == 2
    assert "is_global_admin" not in body

    other = client.get(f"/classes/{data['other']}/dashboard").json()
    assert titles({"items": other["my_quizzes"]}) == ["Other class quiz"]


def test_revoked_collaborator_drops_from_dashboard(shared_quizzes) -> None:
    client, identities, data, quizzes = shared_quizzes
    act_as(client, identities["zoe"])
    revoked = client.delete(
        f"/classes/{data['main']}/quizzes/{quizzes['shared']['quiz_id']}"
        f"/collaborators/{identities['amy'].account_id}"
    )
    assert revoked.status_code in (200, 204)

    act_as(client, identities["amy"])
    body = client.get(f"/classes/{data['main']}/dashboard").json()

    assert titles({"items": body["my_quizzes"]}) == ["Amy's quiz"]
    assert body["my_quiz_count"] == 1


def seed_session(client, class_id: int, host_id: int, player_id: int, code: str):
    """A completed session in class_id that player_id scored 700 in."""
    with client.app.state.database.session_factory() as db:
        quiz = Quiz(author_id=host_id, class_id=class_id)
        db.add(quiz)
        db.flush()
        version = QuizVersion(
            quiz_id=quiz.quiz_id, version_number=1, title=f"Played {code}"
        )
        db.add(version)
        db.flush()
        session = LiveSession(
            quiz_version_id=version.quiz_version_id,
            host_id=host_id,
            class_id=class_id,
            join_code=code,
            status=LiveSessionStatus.COMPLETED,
            started_at=BASE_TIME,
            ended_at=BASE_TIME + timedelta(minutes=10),
        )
        db.add(session)
        db.flush()
        participant = SessionParticipant(
            session_id=session.session_id, account_id=player_id
        )
        db.add(participant)
        db.flush()
        db.add(
            Result(
                session_participant_id=participant.session_participant_id,
                total_score=700,
                correct_count=1,
                final_rank=1,
            )
        )
        db.commit()


def test_dashboards_never_mix_sessions_or_results_across_classes(classes) -> None:
    client, identities, data = classes
    ids = data["ids"]
    seed_session(client, data["main"], ids["prof"], ids["amy"], "111111")
    seed_session(client, data["other"], ids["outsider"], ids["amy"], "222222")
    act_as(client, identities["amy"])

    main = client.get(f"/classes/{data['main']}/dashboard").json()
    sessions = client.get(f"/classes/{data['main']}/sessions").json()
    presented = client.get(f"/classes/{data['main']}/presented-quizzes").json()

    assert [s["quiz_title"] for s in main["completed_sessions"]] == ["Played 111111"]
    assert [s["quiz_title"] for s in sessions["items"]] == ["Played 111111"]
    assert titles(presented) == ["Played 111111"]
    assert main["completed_session_count"] == 1


@pytest.mark.parametrize(
    "path",
    [
        "dashboard",
        "sessions",
        "presented-quizzes",
        "students",
        "grades/export.csv",
        "quizzes",
        "dashboard/submissions",
        "dashboard/approved-quizzes",
    ],
)
@pytest.mark.parametrize("name", ["outsider", "invited", "left", "removed"])
def test_other_classes_people_get_class_not_found(classes, path, name) -> None:
    client, identities, data = classes
    act_as(client, identities[name])

    response = client.get(f"/classes/{data['main']}/{path}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "class_not_found"


@pytest.mark.parametrize("path", ["students", "grades/export.csv"])
def test_members_cannot_read_roster_wide_grades(classes, path) -> None:
    client, identities, data = classes
    act_as(client, identities["amy"])

    response = client.get(f"/classes/{data['main']}/{path}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_class_organizer"


# Approval queue on the dashboard (Task 4 submissions, Task 6 views)


def submit(client, class_id: int, quiz: dict) -> dict:
    publish_quiz(client, quiz["quiz_id"])
    response = client.post(
        f"/classes/{class_id}/quiz-submissions",
        json={"quiz_version_id": quiz["version"]["quiz_version_id"]},
    )
    assert response.status_code == 201, response.json()
    return response.json()


def decide(client, class_id: int, submission: dict, status: str) -> None:
    response = client.patch(
        f"/classes/{class_id}/quiz-submissions/{submission['submission_id']}",
        json={"status": status},
    )
    assert response.status_code == 200, response.json()


@pytest.fixture
def queue(classes):
    """Amy and Zoe each submit a quiz to the main class; Amy also submits
    one to the Other class."""
    client, identities, data = classes
    identities = {**identities, "prof": as_admin(identities["prof"])}
    main = data["main"]
    act_as(client, identities["amy"])
    amys = create(client, main, "Amy's quiz")
    amy_sub = submit(client, main, amys)
    elsewhere = create(client, data["other"], "Other class quiz")
    submit(client, data["other"], elsewhere)
    act_as(client, identities["zoe"])
    zoes = create(client, main, "Zoe's quiz")
    zoe_sub = submit(client, main, zoes)
    return client, identities, data, {
        "amy": (amys, amy_sub),
        "zoe": (zoes, zoe_sub),
    }


def test_organizer_sees_pending_submissions_with_submitter_and_version(
    queue,
) -> None:
    client, identities, data, _ = queue
    act_as(client, identities["prof"])

    body = client.get(
        f"/classes/{data['main']}/dashboard/submissions"
        "?status=PENDING&sort=title&order=asc"
    ).json()

    assert [
        (item["quiz_title"], item["submitter_name"], item["version_number"])
        for item in body["items"]
    ] == [("Amy's quiz", "Amy", 1), ("Zoe's quiz", "Zoe", 1)]
    assert all(item["question_count"] == 2 for item in body["items"])
    assert all(item["is_current_version"] for item in body["items"])
    assert body["pagination"]["total_items"] == 2


def test_members_see_only_their_own_submission_status(queue) -> None:
    client, identities, data, quizzes = queue
    act_as(client, identities["prof"])
    decide(client, data["main"], quizzes["zoe"][1], "REJECTED")
    act_as(client, identities["zoe"])

    body = client.get(f"/classes/{data['main']}/dashboard/submissions").json()
    mine = client.get(f"/classes/{data['main']}/quizzes").json()["items"]

    assert [(i["quiz_title"], i["status"]) for i in body["items"]] == [
        ("Zoe's quiz", "REJECTED")
    ]
    assert body["items"][0]["decided_by_name"] == "Prof"
    assert [(i["title"], i["approval_status"]) for i in mine] == [
        ("Zoe's quiz", "REJECTED")
    ]


def test_my_quizzes_show_approval_state_of_newest_published_version(
    queue,
) -> None:
    client, identities, data, quizzes = queue
    act_as(client, identities["amy"])
    draft = create(client, data["main"], "Amy's draft")

    items = {
        item["title"]: item
        for item in client.get(f"/classes/{data['main']}/quizzes").json()["items"]
    }

    amys, amy_sub = quizzes["amy"]
    assert items["Amy's quiz"]["approval_status"] == "PENDING"
    assert items["Amy's quiz"]["approval_submission_id"] == amy_sub["submission_id"]
    assert (
        items["Amy's quiz"]["published_version_id"]
        == amys["version"]["quiz_version_id"]
    )
    assert items[draft["version"]["title"]]["published_version_id"] is None
    assert items[draft["version"]["title"]]["approval_status"] is None


def test_approved_quizzes_are_listed_for_members_and_say_who_can_host(
    queue,
) -> None:
    client, identities, data, quizzes = queue
    act_as(client, identities["prof"])
    decide(client, data["main"], quizzes["amy"][1], "APPROVED")
    path = f"/classes/{data['main']}/dashboard/approved-quizzes"

    def hostable(name):
        act_as(client, identities[name])
        body = client.get(path).json()
        return [(item["title"], item["can_host"]) for item in body["items"]]

    assert hostable("amy") == [("Amy's quiz", True)]
    assert hostable("zoe") == [("Amy's quiz", False)]
    assert hostable("prof") == [("Amy's quiz", True)]

    act_as(client, identities["zoe"])
    dashboard = client.get(f"/classes/{data['main']}/dashboard").json()
    assert dashboard["approved_quiz_count"] == 1
    assert dashboard["pending_submission_count"] == 1  # Zoe's own

    act_as(client, identities["prof"])
    dashboard = client.get(f"/classes/{data['main']}/dashboard").json()
    assert dashboard["pending_submission_count"] == 1  # Zoe's, still pending


def test_approval_queue_never_shows_another_class(queue) -> None:
    client, identities, data, _ = queue
    act_as(client, identities["amy"])

    main = client.get(f"/classes/{data['main']}/dashboard/submissions").json()
    other = client.get(f"/classes/{data['other']}/dashboard/submissions").json()

    assert [item["quiz_title"] for item in main["items"]] == ["Amy's quiz"]
    assert [item["quiz_title"] for item in other["items"]] == ["Other class quiz"]

    act_as(client, as_admin(identities["outsider"]))
    other = client.get(f"/classes/{data['other']}/dashboard/submissions").json()
    assert [item["submitter_name"] for item in other["items"]] == ["Amy"]


def test_submission_pages_do_not_overlap(queue) -> None:
    client, identities, data, _ = queue
    act_as(client, identities["prof"])
    path = f"/classes/{data['main']}/dashboard/submissions?page_size=1&sort=submitter"

    first = client.get(path + "&page=1").json()
    second = client.get(path + "&page=2").json()

    assert first["pagination"]["total_pages"] == 2
    names = [first["items"][0]["submitter_name"], second["items"][0]["submitter_name"]]
    assert names == ["Zoe", "Amy"]


@pytest.mark.parametrize(
    "query", ["sort=nope", "order=up", "status=MAYBE", "page=0", "page_size=101"]
)
def test_invalid_submission_params_are_rejected(classes, query) -> None:
    client, _, data = classes

    response = client.get(f"/classes/{data['main']}/dashboard/submissions?{query}")

    assert response.status_code == 422


def test_archived_class_lists_approved_quizzes_without_hosting(queue) -> None:
    client, identities, data, quizzes = queue
    act_as(client, identities["prof"])
    decide(client, data["main"], quizzes["amy"][1], "APPROVED")
    assert client.post(f"/classes/{data['main']}/archive").status_code == 200
    act_as(client, identities["amy"])

    body = client.get(f"/classes/{data['main']}/dashboard/approved-quizzes").json()

    assert [(item["title"], item["can_host"]) for item in body["items"]] == [
        ("Amy's quiz", False)
    ]


def test_approved_list_hosting_matches_start_session_checks(queue) -> None:
    """An approved quiz with unpublished edits stays listed but can't be
    hosted, and the list says why, same as starting a session would."""
    client, identities, data, quizzes = queue
    act_as(client, identities["prof"])
    decide(client, data["main"], quizzes["amy"][1], "APPROVED")
    amys = quizzes["amy"][0]
    with client.app.state.database.session_factory() as db:
        db.add(
            QuizVersion(
                quiz_id=amys["quiz_id"],
                version_number=amys["version"]["version_number"] + 1,
                title="Unpublished draft",
                published_at=None,
            )
        )
        db.commit()
    path = f"/classes/{data['main']}/dashboard/approved-quizzes"

    def hosting(name):
        act_as(client, identities[name])
        (item,) = client.get(path).json()["items"]
        return item["can_host"], item["hosting"]["reason"]

    assert hosting("amy") == (False, "unpublished_changes")
    assert hosting("zoe") == (False, "not_host")

    act_as(client, identities["amy"])
    started = client.post(f"/classes/{data['main']}/quizzes/{amys['quiz_id']}/sessions")
    assert started.status_code == 409
    assert started.json()["error"]["details"]["reason"] == "unpublished_changes"
