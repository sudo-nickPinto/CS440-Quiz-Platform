"""Semesters, unarchiving, and the trash (migration 0017)."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.classes import Class, ClassMembership, ClassRole, JoinedVia
from app.models.quiz import QuizVersion
from app.models.quiz_submission import QuizSubmission, SubmissionStatus
from app.models.session import (
    LiveSession,
    LiveSessionStatus,
    Result,
    SessionParticipant,
)
from tests.class_quiz_helpers import approve_quiz, publish_quiz
from tests.test_quiz_api import QUIZ_PAYLOAD

FACULTY = {"prof", "coprof", "stranger"}


@pytest.fixture
def lifecycle() -> Iterator[tuple[TestClient, dict[str, CurrentAccount], int]]:
    """CS 440 run by Prof and Coprof, with Amy and Zoe as students."""
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
                    auth0_sub=f"test|lifecycle-{name}",
                    email=f"{name}@test.invalid",
                    display_name=name.title(),
                    account_type="ADMINISTRATOR" if name in FACULTY else None,
                )
                for name in ("prof", "coprof", "amy", "zoe", "stranger")
            }
            db.add_all(accounts.values())
            db.flush()
            class_ = Class(
                name="CS 440",
                semester="Fall 2026",
                created_by_id=accounts["prof"].account_id,
                join_code="LIFE2345",
                memberships=[
                    ClassMembership(
                        account_id=accounts[name].account_id,
                        role=role,
                        joined_via=JoinedVia.CREATOR,
                    )
                    for name, role in (
                        ("prof", ClassRole.ORGANIZER),
                        ("coprof", ClassRole.ORGANIZER),
                        ("amy", ClassRole.MEMBER),
                        ("zoe", ClassRole.MEMBER),
                    )
                ],
            )
            db.add(class_)
            db.commit()
            identities = {
                name: CurrentAccount(
                    account_id=model.account_id,
                    role=AccountRole.ADMIN if name in FACULTY else AccountRole.USER,
                    is_active=True,
                )
                for name, model in accounts.items()
            }
            class_id = class_.class_id

        act_as(client, identities["prof"])
        yield client, identities, class_id
        client.app.dependency_overrides.clear()


def act_as(client: TestClient, identity: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: identity


def error_code(response) -> str:
    return response.json()["error"]["code"]


def create_quiz(client: TestClient, class_id: int, title: str = "Week 1") -> int:
    response = client.post(
        f"/classes/{class_id}/quizzes", json={**QUIZ_PAYLOAD, "title": title}
    )
    assert response.status_code == 201, response.json()
    return response.json()["quiz_id"]


def add_session(
    client: TestClient,
    quiz_id: int,
    host: CurrentAccount,
    class_id: int,
    scores: dict[CurrentAccount, int],
    status: LiveSessionStatus = LiveSessionStatus.COMPLETED,
    code: str = "100001",
) -> int:
    """A session of the quiz's first version, with a final result per player."""
    now = datetime.now(UTC).replace(tzinfo=None)
    ended = status in (LiveSessionStatus.COMPLETED, LiveSessionStatus.CANCELLED)
    with client.app.state.database.session_factory() as db:
        version = db.query(QuizVersion).filter_by(quiz_id=quiz_id).first()
        session = LiveSession(
            quiz_version_id=version.quiz_version_id,
            host_id=host.account_id,
            class_id=class_id,
            join_code=code,
            status=status,
            started_at=now,
            ended_at=now if ended else None,
        )
        db.add(session)
        db.flush()
        for rank, (player, score) in enumerate(scores.items(), start=1):
            participant = SessionParticipant(
                session_id=session.session_id, account_id=player.account_id
            )
            db.add(participant)
            db.flush()
            db.add(
                Result(
                    session_participant_id=participant.session_participant_id,
                    total_score=score,
                    correct_count=1,
                    final_rank=rank,
                )
            )
        db.commit()
        return session.session_id


# -- Semesters -------------------------------------------------------------


def test_new_class_takes_an_optional_semester(lifecycle) -> None:
    client, _, _ = lifecycle

    labelled = client.post("/classes", json={"name": "CS 440", "semester": " Spring 2027 "})
    blank = client.post("/classes", json={"name": "CS 216", "semester": "  "})
    missing = client.post("/classes", json={"name": "CS 111"})

    assert labelled.status_code == 201
    assert labelled.json()["semester"] == "Spring 2027"
    assert blank.json()["semester"] is None
    assert missing.json()["semester"] is None


def test_the_same_course_can_run_in_several_semesters(lifecycle) -> None:
    client, _, class_id = lifecycle

    spring = client.post("/classes", json={"name": "CS 440", "semester": "Spring 2027"})
    listing = client.get("/classes").json()

    assert spring.status_code == 201
    assert spring.json()["class_id"] != class_id
    assert spring.json()["join_code"] is not None
    assert sorted((c["name"], c["semester"]) for c in listing) == [
        ("CS 440", "Fall 2026"),
        ("CS 440", "Spring 2027"),
    ]


def test_organizer_changes_or_clears_the_semester(lifecycle) -> None:
    client, _, class_id = lifecycle

    changed = client.patch(f"/classes/{class_id}", json={"semester": "Fall 2027"})
    cleared = client.patch(f"/classes/{class_id}", json={"semester": None})
    too_long = client.patch(f"/classes/{class_id}", json={"semester": "x" * 31})

    assert changed.json()["semester"] == "Fall 2027"
    assert cleared.json()["semester"] is None
    assert cleared.json()["name"] == "CS 440"
    assert too_long.status_code == 422


def test_students_cannot_change_the_semester(lifecycle) -> None:
    client, identities, class_id = lifecycle
    act_as(client, identities["amy"])

    response = client.patch(f"/classes/{class_id}", json={"semester": "Spring 2027"})

    assert response.status_code == 403
    assert error_code(response) == "not_class_organizer"


# -- Unarchiving -----------------------------------------------------------


def test_unarchive_reactivates_the_class_with_a_new_code(lifecycle) -> None:
    client, _, class_id = lifecycle
    client.post(f"/classes/{class_id}/archive")

    response = client.post(f"/classes/{class_id}/unarchive")

    assert response.status_code == 200
    body = response.json()
    assert body["archived_at"] is None
    assert body["joining_open"] is True
    assert body["join_code"] not in (None, "LIFE-2345")
    # The class works again: new quizzes are allowed.
    act_as(client, lifecycle[1]["amy"])
    assert client.post(f"/classes/{class_id}/quizzes", json=QUIZ_PAYLOAD).status_code == 201


def test_unarchiving_an_active_class_changes_nothing(lifecycle) -> None:
    client, _, class_id = lifecycle

    response = client.post(f"/classes/{class_id}/unarchive")

    assert response.status_code == 200
    assert response.json()["join_code"] == "LIFE-2345"


def test_only_organizers_unarchive(lifecycle) -> None:
    client, identities, class_id = lifecycle
    client.post(f"/classes/{class_id}/archive")

    act_as(client, identities["amy"])
    student = client.post(f"/classes/{class_id}/unarchive")
    act_as(client, identities["stranger"])
    outsider = client.post(f"/classes/{class_id}/unarchive")

    assert student.status_code == 403
    assert outsider.status_code == 404


# -- Trash: classes --------------------------------------------------------


def test_trashed_class_disappears_and_restores(lifecycle) -> None:
    client, identities, class_id = lifecycle

    assert client.post(f"/classes/{class_id}/trash").status_code == 204

    assert client.get("/classes").json() == []
    assert client.get(f"/classes/{class_id}").status_code == 404
    act_as(client, identities["amy"])
    assert client.get("/classes").json() == []
    assert client.get(f"/classes/{class_id}/dashboard").status_code == 404
    joined = client.post("/classes/join", json={"code": "LIFE-2345"})
    assert error_code(joined) == "class_code_not_found"
    # Students have nothing to restore; every organizer does.
    assert client.get("/trash").json()["classes"] == []
    act_as(client, identities["coprof"])
    trash = client.get("/trash").json()
    assert [(c["class_id"], c["semester"]) for c in trash["classes"]] == [
        (class_id, "Fall 2026")
    ]

    assert client.post(f"/classes/{class_id}/restore").status_code == 204

    assert client.get(f"/classes/{class_id}").json()["join_code"] == "LIFE-2345"
    assert client.get("/trash").json()["classes"] == []
    act_as(client, identities["amy"])
    assert [c["class_id"] for c in client.get("/classes").json()] == [class_id]


def test_trashing_and_restoring_twice_is_harmless(lifecycle) -> None:
    client, _, class_id = lifecycle

    assert client.post(f"/classes/{class_id}/trash").status_code == 204
    assert client.post(f"/classes/{class_id}/trash").status_code == 204
    assert client.post(f"/classes/{class_id}/restore").status_code == 204
    assert client.post(f"/classes/{class_id}/restore").status_code == 204
    assert client.get(f"/classes/{class_id}").status_code == 200


def test_only_organizers_trash_or_restore_a_class(lifecycle) -> None:
    client, identities, class_id = lifecycle

    act_as(client, identities["amy"])
    assert client.post(f"/classes/{class_id}/trash").status_code == 403
    act_as(client, identities["stranger"])
    assert client.post(f"/classes/{class_id}/trash").status_code == 404

    act_as(client, identities["prof"])
    client.post(f"/classes/{class_id}/trash")
    act_as(client, identities["amy"])
    assert client.post(f"/classes/{class_id}/restore").status_code == 403


def test_a_class_with_a_live_session_cannot_be_trashed(lifecycle) -> None:
    client, identities, class_id = lifecycle
    quiz_id = create_quiz(client, class_id)
    add_session(
        client, quiz_id, identities["prof"], class_id, {}, LiveSessionStatus.LOBBY
    )

    response = client.post(f"/classes/{class_id}/trash")

    assert response.status_code == 409
    assert error_code(response) == "class_has_live_session"


def test_quizzes_in_a_trashed_class_are_hidden_too(lifecycle) -> None:
    client, identities, class_id = lifecycle
    act_as(client, identities["amy"])
    quiz_id = create_quiz(client, class_id)
    assert [q["quiz_id"] for q in client.get("/quizzes").json()] == [quiz_id]

    act_as(client, identities["prof"])
    client.post(f"/classes/{class_id}/trash")
    act_as(client, identities["amy"])

    assert client.get("/quizzes").json() == []
    assert client.get(f"/quizzes/{quiz_id}").status_code == 404


# -- Trash: quizzes --------------------------------------------------------


def test_owner_trashes_and_restores_a_quiz(lifecycle) -> None:
    client, identities, class_id = lifecycle
    act_as(client, identities["amy"])
    quiz_id = create_quiz(client, class_id, "Amy's quiz")

    assert client.post(f"/quizzes/{quiz_id}/trash").status_code == 204

    assert client.get(f"/quizzes/{quiz_id}").status_code == 404
    assert client.get(f"/classes/{class_id}/quizzes").json()["items"] == []
    assert client.get("/quizzes").json() == []
    trash = client.get("/trash").json()["quizzes"]
    assert [(q["quiz_id"], q["title"], q["class_name"]) for q in trash] == [
        (quiz_id, "Amy's quiz", "CS 440")
    ]
    act_as(client, identities["prof"])
    assert client.get(f"/classes/{class_id}/quizzes").json()["items"] == []

    act_as(client, identities["amy"])
    assert client.post(f"/quizzes/{quiz_id}/restore").status_code == 204

    assert client.get(f"/quizzes/{quiz_id}").status_code == 200
    assert client.get("/trash").json()["quizzes"] == []


def test_only_the_owner_trashes_a_quiz(lifecycle) -> None:
    client, identities, class_id = lifecycle
    act_as(client, identities["amy"])
    quiz_id = create_quiz(client, class_id)

    for name in ("prof", "zoe", "stranger"):
        act_as(client, identities[name])
        response = client.post(f"/quizzes/{quiz_id}/trash")
        assert response.status_code == 404, name

    act_as(client, identities["amy"])
    assert client.get(f"/quizzes/{quiz_id}").status_code == 200


def test_trashed_quiz_cannot_be_hosted_or_edited(lifecycle) -> None:
    client, _, class_id = lifecycle
    quiz_id = create_quiz(client, class_id)
    publish_quiz(client, quiz_id)
    approve_quiz(client, quiz_id)
    client.post(f"/quizzes/{quiz_id}/trash")

    hosted = client.post(f"/classes/{class_id}/quizzes/{quiz_id}/sessions")
    edited = client.put(
        f"/classes/{class_id}/quizzes/{quiz_id}",
        json={**QUIZ_PAYLOAD, "expected_revision": 1},
    )
    approved = client.get(f"/classes/{class_id}/dashboard/approved-quizzes")

    assert hosted.status_code == 404
    assert edited.status_code == 404
    assert approved.json()["items"] == []
    assert client.get(f"/classes/{class_id}/dashboard").json()["approved_quiz_count"] == 0


def test_pending_approval_leaves_the_queue_with_the_quiz(lifecycle) -> None:
    client, identities, class_id = lifecycle
    act_as(client, identities["amy"])
    quiz_id = create_quiz(client, class_id)
    publish_quiz(client, quiz_id)
    with client.app.state.database.session_factory() as db:
        version = db.query(QuizVersion).filter_by(quiz_id=quiz_id).first()
        db.add(
            QuizSubmission(
                class_id=class_id,
                quiz_version_id=version.quiz_version_id,
                submitted_by_id=identities["amy"].account_id,
                status=SubmissionStatus.PENDING,
            )
        )
        db.commit()
    act_as(client, identities["prof"])
    assert client.get(f"/classes/{class_id}/dashboard").json()["pending_submission_count"] == 1

    act_as(client, identities["amy"])
    client.post(f"/quizzes/{quiz_id}/trash")
    act_as(client, identities["prof"])

    assert client.get(f"/classes/{class_id}/dashboard").json()["pending_submission_count"] == 0
    assert client.get(f"/classes/{class_id}/dashboard/submissions").json()["items"] == []

    act_as(client, identities["amy"])
    client.post(f"/quizzes/{quiz_id}/restore")
    act_as(client, identities["prof"])
    assert client.get(f"/classes/{class_id}/dashboard").json()["pending_submission_count"] == 1


def test_a_quiz_being_played_cannot_be_trashed(lifecycle) -> None:
    client, identities, class_id = lifecycle
    quiz_id = create_quiz(client, class_id)
    add_session(
        client, quiz_id, identities["prof"], class_id, {}, LiveSessionStatus.ACTIVE
    )

    response = client.post(f"/quizzes/{quiz_id}/trash")

    assert response.status_code == 409
    assert error_code(response) == "quiz_has_live_session"


def test_restore_the_class_before_its_quiz(lifecycle) -> None:
    client, identities, class_id = lifecycle
    act_as(client, identities["amy"])
    quiz_id = create_quiz(client, class_id)
    client.post(f"/quizzes/{quiz_id}/trash")
    act_as(client, identities["prof"])
    client.post(f"/classes/{class_id}/trash")
    act_as(client, identities["amy"])

    trash = client.get("/trash").json()["quizzes"]
    blocked = client.post(f"/quizzes/{quiz_id}/restore")

    assert trash[0]["class_in_trash"] is True
    assert blocked.status_code == 409
    assert error_code(blocked) == "class_in_trash"


# -- Trash: hosted sessions ------------------------------------------------


def test_host_trashes_a_mistaken_session_from_history_and_grades(lifecycle) -> None:
    client, identities, class_id = lifecycle
    quiz_id = create_quiz(client, class_id)
    amy, zoe = identities["amy"], identities["zoe"]
    real = add_session(client, quiz_id, identities["prof"], class_id, {amy: 800, zoe: 600})
    mistake = add_session(
        client, quiz_id, identities["prof"], class_id, {amy: 100}, code="100002"
    )
    history = f"/quizzes/{quiz_id}/history"
    assert len(client.get(history).json()["items"]) == 2

    assert client.post(f"/sessions/{mistake}/trash").status_code == 204

    assert [s["session_id"] for s in client.get(history).json()["items"]] == [real]
    dashboard = client.get(f"/classes/{class_id}/dashboard").json()
    assert dashboard["completed_session_count"] == 1
    students = {
        s["display_name"]: s for s in client.get(f"/classes/{class_id}/students").json()["items"]
    }
    assert students["Amy"]["average_score"] == 800
    assert students["Zoe"]["attendance_rate"] == 1
    report = client.get(f"/classes/{class_id}/sessions/{mistake}/results")
    assert report.status_code == 404
    for path_ in (
        f"/sessions/{mistake}",
        f"/sessions/{mistake}/participants",
        f"/sessions/{mistake}/results",
        f"/sessions/{mistake}/report",
        f"/sessions/{mistake}/results/export.csv",
    ):
        direct = client.get(path_)
        assert direct.status_code == 404, path_
        assert error_code(direct) == "session_not_found"
    act_as(client, amy)
    assert [s["session_id"] for s in client.get("/me/sessions/taken").json()["items"]] == [real]

    act_as(client, identities["prof"])
    trash = client.get("/trash").json()["sessions"]
    assert [(s["session_id"], s["quiz_title"]) for s in trash] == [(mistake, "Week 1")]
    assert client.post(f"/sessions/{mistake}/restore").status_code == 204
    assert len(client.get(history).json()["items"]) == 2
    assert client.get(f"/classes/{class_id}/dashboard").json()["completed_session_count"] == 2


def test_cancelled_sessions_can_be_trashed_but_running_ones_cannot(lifecycle) -> None:
    client, identities, class_id = lifecycle
    quiz_id = create_quiz(client, class_id)
    prof = identities["prof"]
    cancelled = add_session(
        client, quiz_id, prof, class_id, {}, LiveSessionStatus.CANCELLED
    )
    running = add_session(
        client, quiz_id, prof, class_id, {}, LiveSessionStatus.ACTIVE, code="100002"
    )

    assert client.post(f"/sessions/{cancelled}/trash").status_code == 204
    response = client.post(f"/sessions/{running}/trash")
    assert response.status_code == 409
    assert error_code(response) == "session_not_ended"


def test_only_the_host_trashes_a_session(lifecycle) -> None:
    client, identities, class_id = lifecycle
    quiz_id = create_quiz(client, class_id)
    session_id = add_session(client, quiz_id, identities["prof"], class_id, {})

    for name in ("coprof", "amy", "stranger"):
        act_as(client, identities[name])
        response = client.post(f"/sessions/{session_id}/trash")
        assert response.status_code == 404, name
        assert client.get("/trash").json()["sessions"] == []


def test_students_cannot_open_an_archived_class(lifecycle) -> None:
    client, identities, class_id = lifecycle
    create_quiz(client, class_id)
    assert client.post(f"/classes/{class_id}/archive").status_code == 200

    act_as(client, identities["amy"])
    assert client.get(f"/classes/{class_id}").status_code == 200
    for path in (
        f"/classes/{class_id}/quizzes",
        f"/classes/{class_id}/dashboard",
    ):
        blocked = client.get(path)
        assert blocked.status_code == 409, path
        assert error_code(blocked) == "class_archived"

    act_as(client, identities["prof"])
    assert client.get(f"/classes/{class_id}/quizzes").status_code == 200


def test_new_semester_is_empty_and_linked_to_the_course(lifecycle) -> None:
    client, identities, class_id = lifecycle
    create_quiz(client, class_id)

    created = client.post(
        f"/classes/{class_id}/semesters", json={"semester": "Spring 2027"}
    )
    assert created.status_code == 201, created.json()
    body = created.json()
    assert body["name"] == "CS 440"
    assert body["semester"] == "Spring 2027"
    assert body["parent_class_id"] == class_id
    assert body["class_id"] != class_id
    assert {item["class_id"] for item in body["semesters"]} == {
        class_id,
        body["class_id"],
    }
    assert client.get(f"/classes/{body['class_id']}/quizzes").json()["items"] == []

    again = client.post(
        f"/classes/{class_id}/semesters", json={"semester": "spring 2027"}
    )
    assert again.status_code == 409
    assert error_code(again) == "semester_exists"

    act_as(client, identities["amy"])
    visible = {item["class_id"] for item in client.get("/classes").json()}
    assert body["class_id"] not in visible
    assert class_id in visible


def test_trash_shows_days_left_and_expires_after_30_days(lifecycle) -> None:
    client, identities, class_id = lifecycle
    quiz_id = create_quiz(client, class_id)
    assert client.post(f"/quizzes/{quiz_id}/trash").status_code == 204

    fresh = client.get("/trash").json()["quizzes"]
    assert fresh[0]["days_left"] == 30
    assert "expires_at" in fresh[0]

    with client.app.state.database.session_factory() as db:
        from app.models.quiz import Quiz

        quiz = db.get(Quiz, quiz_id)
        quiz.deleted_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=31)
        db.commit()

    assert client.get("/trash").json()["quizzes"] == []
    gone = client.post(f"/quizzes/{quiz_id}/restore")
    assert gone.status_code == 404
    assert error_code(gone) == "quiz_not_found"


def test_organizer_can_delete_a_trashed_class_permanently(lifecycle) -> None:
    client, identities, class_id = lifecycle
    assert client.post(f"/classes/{class_id}/trash").status_code == 204
    purged = client.post("/trash/purge", json={"class_ids": [class_id]})
    assert purged.status_code == 204, purged.json()
    assert client.get("/trash").json()["classes"] == []
    restore = client.post(f"/classes/{class_id}/restore")
    assert restore.status_code == 404
    assert error_code(restore) == "class_not_found"
