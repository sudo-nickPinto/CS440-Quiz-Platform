from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models import (
    Account,
    AccountRole,
    AnswerChoice,
    Class,
    ClassMembership,
    ClassRole,
    LiveSession,
    LiveSessionStatus,
    MembershipStatus,
    Question,
    Quiz,
    QuizVersion,
    Response,
    Result,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)

BASE_TIME = datetime(2026, 10, 1, 12, 0)

# name -> (display name, class role, membership status); None = no membership.
PEOPLE = {
    "owner": ("Owner", ClassRole.ORGANIZER, MembershipStatus.ACTIVE),
    "coorg": ("Co Organizer", ClassRole.ORGANIZER, MembershipStatus.ACTIVE),
    "amy": ("Amy Student", ClassRole.MEMBER, MembershipStatus.ACTIVE),
    "zoe": ("Zoe Student", ClassRole.MEMBER, MembershipStatus.ACTIVE),
    "member": ("Member", ClassRole.MEMBER, MembershipStatus.ACTIVE),
    "rex": ("Rex Removed", ClassRole.MEMBER, MembershipStatus.REMOVED),
    "invited": ("Invited", ClassRole.MEMBER, MembershipStatus.INVITED),
    "nonmember": ("Nonmember", None, None),
    "global": ("Global Admin", None, None),
}


def add_session(db, version, host_id, *, class_id, day, status, code):
    session = LiveSession(
        quiz_version_id=version.quiz_version_id,
        host_id=host_id,
        class_id=class_id,
        join_code=code,
        status=status,
        started_at=BASE_TIME + timedelta(days=day),
        ended_at=BASE_TIME + timedelta(days=day, minutes=10),
    )
    db.add(session)
    db.flush()
    return session


def play(db, session, questions, ids, answers):
    """answers: name -> one (choice index or None, points) per question."""
    closed = []
    for question in questions:
        sq = SessionQuestion(
            session_id=session.session_id,
            question_id=question.question_id,
            status=SessionQuestionStatus.CLOSED,
            opened_at=session.started_at,
            closed_at=session.started_at,
        )
        db.add(sq)
        closed.append(sq)
    db.flush()

    totals = {
        name: (sum(p for _, p in picks), sum(1 for c, _ in picks if c == 0))
        for name, picks in answers.items()
    }
    ordered = sorted(totals, key=lambda name: -totals[name][0])
    for rank, name in enumerate(ordered, start=1):
        participant = SessionParticipant(
            session_id=session.session_id, account_id=ids[name]
        )
        db.add(participant)
        db.flush()
        for question, sq, (choice, points) in zip(
            questions, closed, answers[name], strict=True
        ):
            if choice is None:
                continue
            db.add(
                Response(
                    session_participant_id=participant.session_participant_id,
                    session_question_id=sq.session_question_id,
                    choice_id=question.choices[choice].choice_id,
                    submitted_at=session.started_at,
                    response_time_ms=2000,
                    is_correct=choice == 0,
                    points_awarded=points,
                )
            )
        db.add(
            Result(
                session_participant_id=participant.session_participant_id,
                total_score=totals[name][0],
                correct_count=totals[name][1],
                final_rank=rank,
            )
        )


@pytest.fixture
def reports() -> Iterator[tuple[TestClient, dict, dict]]:
    """A class with two completed sessions of one quiz.

    Day 0: Amy 900 (2 right), Zoe 300 (1 right, 1 wrong), Rex 100.
    Day 1: Amy 500 (1 right, 1 unanswered).
    Rex was removed after playing. A cancelled class session, an open
    session and another class's session must never show up.
    """
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
                    display_name=display,
                )
                for name, (display, _, _) in PEOPLE.items()
            }
            db.add_all(accounts.values())
            db.flush()
            ids = {name: model.account_id for name, model in accounts.items()}

            class_ = Class(
                name="CS 440", created_by_id=ids["owner"], join_code="REPT0001"
            )
            other = Class(
                name="Other", created_by_id=ids["owner"], join_code="REPT0002"
            )
            db.add_all([class_, other])
            db.flush()
            for name, (_, role, status) in PEOPLE.items():
                if role is not None:
                    db.add(
                        ClassMembership(
                            class_id=class_.class_id,
                            account_id=ids[name],
                            role=role,
                            status=status,
                        )
                    )

            quiz = Quiz(author_id=ids["owner"])
            db.add(quiz)
            db.flush()
            version = QuizVersion(
                quiz_id=quiz.quiz_id, version_number=1, title="Week 1"
            )
            db.add(version)
            db.flush()
            questions = []
            for order in (1, 2):
                question = Question(
                    quiz_version_id=version.quiz_version_id,
                    question_order=order,
                    question_text=f"Question {order}?",
                    time_limit_seconds=20,
                )
                question.choices = [
                    AnswerChoice(choice_order=1, choice_text="Right", is_correct=True),
                    AnswerChoice(choice_order=2, choice_text="Wrong", is_correct=False),
                ]
                db.add(question)
                questions.append(question)
            db.flush()

            first = add_session(
                db,
                version,
                ids["owner"],
                class_id=class_.class_id,
                day=0,
                status=LiveSessionStatus.COMPLETED,
                code="100000",
            )
            play(
                db,
                first,
                questions,
                ids,
                {
                    "amy": [(0, 500), (0, 400)],
                    "zoe": [(0, 300), (1, 0)],
                    "rex": [(0, 100), (1, 0)],
                },
            )
            second = add_session(
                db,
                version,
                ids["owner"],
                class_id=class_.class_id,
                day=1,
                status=LiveSessionStatus.COMPLETED,
                code="100001",
            )
            play(db, second, questions, ids, {"amy": [(0, 500), (None, 0)]})
            cancelled = add_session(
                db,
                version,
                ids["owner"],
                class_id=class_.class_id,
                day=2,
                status=LiveSessionStatus.CANCELLED,
                code="100002",
            )
            open_session = add_session(
                db,
                version,
                ids["owner"],
                class_id=None,
                day=3,
                status=LiveSessionStatus.COMPLETED,
                code="100003",
            )
            elsewhere = add_session(
                db,
                version,
                ids["owner"],
                class_id=other.class_id,
                day=4,
                status=LiveSessionStatus.COMPLETED,
                code="100004",
            )
            play(db, open_session, questions, ids, {"amy": [(1, 0), (1, 0)]})
            play(db, elsewhere, questions, ids, {"amy": [(1, 0), (1, 0)]})
            db.commit()

            data = {
                "class_id": class_.class_id,
                "quiz_id": quiz.quiz_id,
                "first": first.session_id,
                "second": second.session_id,
                "cancelled": cancelled.session_id,
                "open": open_session.session_id,
                "elsewhere": elsewhere.session_id,
                "ids": ids,
            }

        identities = {
            name: CurrentAccount(
                ids[name],
                AccountRole.ADMIN if name == "global" else AccountRole.USER,
                True,
            )
            for name in PEOPLE
        }
        act_as(client, identities["owner"])
        yield client, identities, data


def act_as(client: TestClient, identity: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: identity


def session_url(data, session: str) -> str:
    return f"/classes/{data['class_id']}/sessions/{data[session]}/results"


def quiz_url(data) -> str:
    return f"/classes/{data['class_id']}/quizzes/{data['quiz_id']}/results"


def student_url(data, name: str) -> str:
    return f"/classes/{data['class_id']}/students/{data['ids'][name]}/results"


# Session report


def test_organizer_who_did_not_host_sees_every_player(reports) -> None:
    client, identities, data = reports
    act_as(client, identities["coorg"])

    response = client.get(session_url(data, "first"))

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["view"] == "host"
    assert body["class_id"] == data["class_id"]
    assert body["quiz_title"] == "Week 1"
    assert body["started_at"].startswith("2026-10-01T12:00")
    assert [
        (p["name"], p["rank"], p["points"], p["correct"]) for p in body["players"]
    ] == [
        ("Amy Student", 1, 900, 2),
        ("Zoe Student", 2, 300, 1),
        ("Rex Removed", 3, 100, 1),
    ]
    zoe = body["players"][1]
    assert [(a["state"], a["points"]) for a in zoe["answers"]] == [
        ("correct", 300),
        ("wrong", 0),
    ]


def test_unanswered_question_shows_as_missed(reports) -> None:
    client, _, data = reports

    amy = client.get(session_url(data, "second")).json()["players"][0]

    assert [a["state"] for a in amy["answers"]] == ["correct", "missed"]


def test_member_sees_only_their_own_rows(reports) -> None:
    client, identities, data = reports
    act_as(client, identities["zoe"])

    body = client.get(session_url(data, "first")).json()

    assert body["view"] == "participant"
    assert [p["name"] for p in body["players"]] == ["Zoe Student"]


def test_member_who_did_not_play_is_denied(reports) -> None:
    client, identities, data = reports
    act_as(client, identities["zoe"])

    response = client.get(session_url(data, "second"))

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "participant_report_denied"


@pytest.mark.parametrize("session", ["cancelled", "open", "elsewhere"])
def test_sessions_outside_the_class_history_look_missing(reports, session) -> None:
    client, _, data = reports

    response = client.get(session_url(data, session))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session_not_found"


@pytest.mark.parametrize("name", ["nonmember", "invited", "rex"])
def test_people_without_active_membership_cannot_see_reports(reports, name) -> None:
    client, identities, data = reports
    act_as(client, identities[name])

    for url in (
        session_url(data, "first"),
        quiz_url(data),
        student_url(data, name if name != "nonmember" else "amy"),
    ):
        response = client.get(url)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "class_not_found"


# Quiz report


def test_organizer_quiz_report_lists_each_completed_presentation(reports) -> None:
    client, _, data = reports

    body = client.get(quiz_url(data)).json()

    assert body["title"] == "Week 1"
    assert body["session_count"] == 2
    assert body["participant_count"] == 4
    # (900 + 300 + 100 + 500) / 4 players
    assert body["average_score"] == 450.0
    newest, oldest = body["sessions"]
    assert newest["session_id"] == data["second"]
    assert newest["started_at"].startswith("2026-10-02")
    assert [p["name"] for p in newest["results"]] == ["Amy Student"]
    assert (oldest["participant_count"], oldest["average_score"]) == (3, 433.3)
    assert [(p["name"], p["rank"]) for p in oldest["results"]] == [
        ("Amy Student", 1),
        ("Zoe Student", 2),
        ("Rex Removed", 3),
    ]


def test_member_quiz_report_hides_classmates(reports) -> None:
    client, identities, data = reports
    act_as(client, identities["zoe"])

    body = client.get(quiz_url(data)).json()

    assert body["average_score"] is None
    newest, oldest = body["sessions"]
    assert newest["results"] == []
    assert newest["average_score"] is None
    assert [p["name"] for p in oldest["results"]] == ["Zoe Student"]
    assert (oldest["my_score"], oldest["my_rank"]) == (300, 2)


def test_unknown_quiz_is_not_found(reports) -> None:
    client, _, data = reports

    response = client.get(f"/classes/{data['class_id']}/quizzes/9999/results")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "quiz_not_found"


@pytest.mark.parametrize("viewer", ["member", "owner", "global"])
@pytest.mark.parametrize(
    "presentation",
    ["never_presented", "other_class", "cancelled", "active"],
)
def test_quiz_without_completed_class_session_is_not_found(
    reports, viewer, presentation
) -> None:
    client, identities, data = reports

    with client.app.state.database.session_factory() as db:
        quiz = Quiz(author_id=data["ids"]["nonmember"])
        db.add(quiz)
        db.flush()

        version = QuizVersion(
            quiz_id=quiz.quiz_id,
            version_number=1,
            title="Unrelated private quiz",
        )
        db.add(version)
        db.flush()

        if presentation != "never_presented":
            target_class_id = data["class_id"]
            status = LiveSessionStatus.COMPLETED

            if presentation == "other_class":
                other_class = Class(
                    name="Unrelated class",
                    created_by_id=data["ids"]["nonmember"],
                    join_code="HIDE0001",
                )
                db.add(other_class)
                db.flush()
                target_class_id = other_class.class_id
            elif presentation == "cancelled":
                status = LiveSessionStatus.CANCELLED
            else:
                status = LiveSessionStatus.ACTIVE

            add_session(
                db,
                version,
                data["ids"]["nonmember"],
                class_id=target_class_id,
                day=5,
                status=status,
                code="900001",
            )

        quiz_id = quiz.quiz_id
        db.commit()

    act_as(client, identities[viewer])

    response = client.get(f"/classes/{data['class_id']}/quizzes/{quiz_id}/results")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "quiz_not_found"
    assert "Unrelated private quiz" not in response.text


# Student report


def test_organizer_student_report_totals_and_class_average(reports) -> None:
    client, _, data = reports

    body = client.get(student_url(data, "amy")).json()

    assert body["display_name"] == "Amy Student"
    assert body["email"] == "amy@gettysburg.edu"
    assert (body["class_session_count"], body["session_count"]) == (2, 2)
    assert (body["total_points"], body["average_score"]) == (1400, 700.0)
    assert (body["correct_count"], body["incorrect_count"]) == (3, 1)
    assert body["attendance_rate"] == 1.0
    # Mean of student averages: Amy 700, Zoe 300. Rex was removed, so he
    # isn't counted, and Member never played.
    assert body["class_average"] == 500.0
    assert [s["points"] for s in body["sessions"]] == [500, 900]
    assert [(s["correct"], s["incorrect"]) for s in body["sessions"]] == [
        (1, 1),
        (2, 0),
    ]


def test_student_report_marks_missed_sessions(reports) -> None:
    client, _, data = reports

    body = client.get(student_url(data, "zoe")).json()

    assert body["attendance_rate"] == 0.5
    missed, played = body["sessions"]
    assert (missed["played"], missed["points"], missed["correct"]) == (
        False,
        None,
        None,
    )
    assert (played["played"], played["points"], played["rank"]) == (True, 300, 2)


def test_removed_student_history_stays_visible_to_organizers(reports) -> None:
    client, _, data = reports

    body = client.get(student_url(data, "rex")).json()

    assert body["status"] == "REMOVED"
    assert body["total_points"] == 100


def test_member_sees_own_report_without_class_wide_numbers(reports) -> None:
    client, identities, data = reports
    act_as(client, identities["zoe"])

    mine = client.get(student_url(data, "zoe"))
    other = client.get(student_url(data, "amy"))

    assert mine.status_code == 200
    assert mine.json()["total_points"] == 300
    assert mine.json()["email"] is None
    assert mine.json()["class_average"] is None
    assert other.status_code == 403
    assert other.json()["error"]["code"] == "not_class_organizer"


def test_student_outside_the_class_is_not_found(reports) -> None:
    client, _, data = reports

    response = client.get(student_url(data, "nonmember"))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "student_not_found"


def test_global_admin_reads_every_report_without_membership(reports) -> None:
    client, identities, data = reports
    act_as(client, identities["global"])

    session = client.get(session_url(data, "first"))
    quiz = client.get(quiz_url(data))
    student = client.get(student_url(data, "amy"))

    assert session.status_code == 200
    assert len(session.json()["players"]) == 3
    assert quiz.json()["average_score"] == 450.0
    assert student.json()["class_average"] == 500.0
