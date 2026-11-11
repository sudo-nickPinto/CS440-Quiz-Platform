from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

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
    MembershipStatus,
)
from app.models.quiz import Quiz, QuizVersion
from app.models.session import (
    LiveSession,
    LiveSessionStatus,
    Result,
    SessionParticipant,
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
                    account_type="ADMINISTRATOR" if name in {"owner", "global"} else None,
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
                        AccountRole.ADMIN if name in {"owner", "global"} else AccountRole.USER
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
    assert body["completed_session_count"] == 0
    assert body["class_average"] is None


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
        f"/classes/{class_id}/presented-quizzes?page=2&page_size=5&sort=title&order=asc"
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


def test_unrelated_faculty_cannot_access_dashboard_or_students(dashboard_client):
    client, identities, class_id = dashboard_client
    act_as(client, identities["global"])
    for path in (f"/classes/{class_id}/dashboard", f"/classes/{class_id}/students"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "class_not_found"

def test_nonmember_cannot_discover_class(dashboard_client) -> None:
    client, identities, class_id = dashboard_client
    act_as(client, identities["nonmember"])

    for suffix in ("dashboard", "presented-quizzes", "sessions", "students"):
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
        db.flush()
        db.add(
            ClassMembership(
                class_id=archived.class_id,
                account_id=identities["global"].account_id,
                role=ClassRole.ORGANIZER,
                status=MembershipStatus.ACTIVE,
            )
        )
        db.commit()
        archived_id = archived.class_id
    act_as(client, identities["global"])

    dashboard = client.get(f"/classes/{archived_id}/dashboard")
    students = client.get(f"/classes/{archived_id}/students")

    assert dashboard.status_code == 200
    assert dashboard.json()["is_archived"] is True
    assert dashboard.json()["active_member_count"] == 1
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
    assert len(selects) <= 5


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


BASE_TIME = datetime(2026, 10, 1, 12, 0)


def seed_completed_sessions(client: TestClient, identities, class_id: int) -> None:
    """Two completed class sessions: Amy plays both, Zoe only the first."""
    owner = identities["owner"].account_id
    with client.app.state.database.session_factory() as db:
        quiz = Quiz(author_id=owner)
        db.add(quiz)
        db.flush()
        version = QuizVersion(quiz_id=quiz.quiz_id, version_number=1, title="Week 1")
        db.add(version)
        db.flush()
        plays = [
            {"amy": 900, "zoe": 300},
            {"amy": 500},
        ]
        for index, scores in enumerate(plays):
            session = LiveSession(
                quiz_version_id=version.quiz_version_id,
                host_id=owner,
                class_id=class_id,
                join_code=f"10000{index}",
                status=LiveSessionStatus.COMPLETED,
                started_at=BASE_TIME + timedelta(days=index),
                ended_at=BASE_TIME + timedelta(days=index, minutes=10),
            )
            db.add(session)
            db.flush()
            ranked = sorted(scores.items(), key=lambda item: -item[1])
            for rank, (name, score) in enumerate(ranked, start=1):
                participant = SessionParticipant(
                    session_id=session.session_id,
                    account_id=identities[name].account_id,
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
        # Open sessions and other classes' sessions never show up here.
        db.add(
            LiveSession(
                quiz_version_id=version.quiz_version_id,
                host_id=owner,
                join_code="200000",
                status=LiveSessionStatus.COMPLETED,
            )
        )
        db.commit()


def seed_search_history(client: TestClient, identities, class_id: int) -> None:
    """Put two Week 1 sessions behind newer completed history."""
    seed_completed_sessions(client, identities, class_id)
    owner = identities["owner"].account_id
    with client.app.state.database.session_factory() as db:
        for day in range(2, 5):
            quiz = Quiz(author_id=owner)
            db.add(quiz)
            db.flush()
            version = QuizVersion(
                quiz_id=quiz.quiz_id, version_number=1, title=f"Week {day}"
            )
            db.add(version)
            db.flush()
            db.add(
                LiveSession(
                    quiz_version_id=version.quiz_version_id,
                    host_id=owner,
                    class_id=class_id,
                    join_code=f"30000{day}",
                    status=LiveSessionStatus.COMPLETED,
                    started_at=BASE_TIME + timedelta(days=day),
                    ended_at=BASE_TIME + timedelta(days=day, minutes=10),
                )
            )
        # A matching title in an unfinished session must stay out of history.
        active_quiz = Quiz(author_id=owner)
        db.add(active_quiz)
        db.flush()
        active_version = QuizVersion(
            quiz_id=active_quiz.quiz_id,
            version_number=1,
            title="Week 1 Live",
        )
        db.add(active_version)
        db.flush()
        db.add(
            LiveSession(
                quiz_version_id=active_version.quiz_version_id,
                host_id=owner,
                class_id=class_id,
                join_code="399999",
                status=LiveSessionStatus.ACTIVE,
            )
        )
        other_class = Class(
            name="Other Class",
            created_by_id=owner,
            join_code="DASH0002",
        )
        db.add(other_class)
        db.flush()
        db.add(
            ClassMembership(
                class_id=other_class.class_id,
                account_id=owner,
                role=ClassRole.ORGANIZER,
            )
        )
        db.add(
            LiveSession(
                quiz_version_id=active_version.quiz_version_id,
                host_id=owner,
                class_id=other_class.class_id,
                join_code="399998",
                status=LiveSessionStatus.COMPLETED,
                started_at=BASE_TIME + timedelta(days=5),
                ended_at=BASE_TIME + timedelta(days=5, minutes=10),
            )
        )
        db.commit()


def test_session_title_search_finds_older_matches_before_pagination(
    dashboard_client,
) -> None:
    client, identities, class_id = dashboard_client
    seed_search_history(client, identities, class_id)
    path = f"/classes/{class_id}/sessions"

    first_unfiltered_page = client.get(path, params={"page_size": 2}).json()
    assert [item["quiz_title"] for item in first_unfiltered_page["items"]] == [
        "Week 4",
        "Week 3",
    ]
    assert first_unfiltered_page["pagination"]["total_items"] == 5

    first_match = client.get(
        path, params={"q": "wEeK 1", "page_size": 1, "page": 1}
    ).json()
    second_match = client.get(
        path, params={"q": "wEeK 1", "page_size": 1, "page": 2}
    ).json()

    assert first_match["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total_items": 2,
        "total_pages": 2,
    }
    assert second_match["pagination"] == {
        "page": 2,
        "page_size": 1,
        "total_items": 2,
        "total_pages": 2,
    }
    assert [item["quiz_title"] for item in first_match["items"]] == ["Week 1"]
    assert [item["quiz_title"] for item in second_match["items"]] == ["Week 1"]
    assert first_match["items"][0]["started_at"] > second_match["items"][0]["started_at"]


def test_session_title_search_blank_unmatched_and_sorting(dashboard_client) -> None:
    client, identities, class_id = dashboard_client
    seed_search_history(client, identities, class_id)
    path = f"/classes/{class_id}/sessions"

    original = client.get(path, params={"page_size": 2}).json()
    for blank in ("", "   "):
        assert client.get(path, params={"q": blank, "page_size": 2}).json() == original

    unmatched = client.get(path, params={"q": "missing", "page_size": 2}).json()
    assert unmatched["items"] == []
    assert unmatched["pagination"] == {
        "page": 1,
        "page_size": 2,
        "total_items": 0,
        "total_pages": 0,
    }

    by_attendance = client.get(
        path,
        params={"q": "  wEeK 1  ", "sort": "participant_count", "order": "desc"},
    ).json()
    assert [item["participant_count"] for item in by_attendance["items"]] == [2, 1]
    assert by_attendance["pagination"]["total_items"] == 2

    oldest_first = client.get(
        path, params={"q": "Week 1", "sort": "started_at", "order": "asc"}
    ).json()
    assert oldest_first["items"][0]["started_at"] < oldest_first["items"][1]["started_at"]

    by_average = client.get(
        path, params={"q": "Week 1", "sort": "average_score", "order": "desc"}
    ).json()
    assert [item["average_score"] for item in by_average["items"]] == [600.0, 500.0]


def test_session_title_search_limits_query_to_200_characters(dashboard_client) -> None:
    client, identities, class_id = dashboard_client
    seed_search_history(client, identities, class_id)
    path = f"/classes/{class_id}/sessions"

    at_limit = client.get(path, params={"q": " " * 194 + "Week 1"})
    over_limit = client.get(path, params={"q": " " * 195 + "Week 1"})

    assert at_limit.status_code == 200
    assert at_limit.json()["pagination"]["total_items"] == 2
    assert over_limit.status_code == 422
    assert over_limit.json()["error"]["code"] == "request_validation_error"


def test_session_title_search_preserves_member_fields_and_outsider_denial(
    dashboard_client,
) -> None:
    client, identities, class_id = dashboard_client
    seed_search_history(client, identities, class_id)
    path = f"/classes/{class_id}/sessions"

    act_as(client, identities["zoe"])
    response = client.get(path, params={"q": "WEEK 1"})
    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 2
    assert set(items[0]) == {
        "session_id", "quiz_id", "quiz_title", "status", "host_name", "is_host",
        "started_at", "ended_at", "participant_count", "average_score",
        "top_score", "my_score", "my_rank",
    }
    assert [item["my_score"] for item in items] == [None, 300]
    assert [item["my_rank"] for item in items] == [None, 2]
    assert all(item["average_score"] is None and item["top_score"] is None for item in items)

    act_as(client, identities["nonmember"])
    denied = client.get(path, params={"q": "Week 1"})
    assert denied.status_code == 404
    assert denied.json()["error"]["code"] == "class_not_found"


def test_sessions_report_attendance_and_scores(dashboard_client) -> None:
    client, identities, class_id = dashboard_client
    seed_completed_sessions(client, identities, class_id)

    body = client.get(f"/classes/{class_id}/sessions").json()

    assert body["pagination"]["total_items"] == 2
    newest, oldest = body["items"]
    assert newest["quiz_title"] == "Week 1"
    assert newest["is_host"] is True
    assert (newest["participant_count"], newest["average_score"]) == (1, 500.0)
    assert (oldest["participant_count"], oldest["average_score"]) == (2, 600.0)
    assert oldest["top_score"] == 900


def test_member_sees_own_scores_but_not_class_averages(dashboard_client) -> None:
    client, identities, class_id = dashboard_client
    seed_completed_sessions(client, identities, class_id)
    act_as(client, identities["zoe"])

    newest, oldest = client.get(f"/classes/{class_id}/sessions").json()["items"]

    assert (newest["my_score"], newest["my_rank"]) == (None, None)
    assert (oldest["my_score"], oldest["my_rank"]) == (300, 2)
    assert oldest["average_score"] is None
    assert oldest["top_score"] is None


def test_students_and_dashboard_aggregate_class_results(dashboard_client) -> None:
    client, identities, class_id = dashboard_client
    seed_completed_sessions(client, identities, class_id)

    students = client.get(
        f"/classes/{class_id}/students?sort=average_score&order=desc"
    ).json()["items"]
    dashboard = client.get(f"/classes/{class_id}/dashboard").json()
    quizzes = client.get(f"/classes/{class_id}/presented-quizzes").json()["items"]

    amy, zoe, member = students
    assert amy["display_name"] == "Amy Student"
    assert (amy["average_score"], amy["total_points"]) == (700.0, 1400)
    assert amy["recent_scores"] == [500, 900]
    assert zoe["recent_scores"] == [None, 300]
    assert zoe["attendance_rate"] == 0.5
    assert member["session_count"] == 0
    assert member["average_score"] is None
    assert dashboard["completed_session_count"] == 2
    assert dashboard["class_average"] == 500.0
    assert dashboard["attendance_rate"] == 0.5
    assert [quiz["session_count"] for quiz in quizzes] == [2]
    assert quizzes[0]["average_score"] == 566.7


def test_grade_export_is_a_gradebook_for_organizers_only(dashboard_client) -> None:
    client, identities, class_id = dashboard_client
    seed_completed_sessions(client, identities, class_id)
    with client.app.state.database.session_factory() as db:
        zoe = db.get(Account, identities["zoe"].account_id)
        zoe.display_name = "=Zoe"
        db.commit()

    response = client.get(f"/classes/{class_id}/grades/export.csv")
    act_as(client, identities["member"])
    denied = client.get(f"/classes/{class_id}/grades/export.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="cs-440-fall-2026-grades.csv"' in (
        response.headers["content-disposition"]
    )
    lines = response.text.lstrip("﻿").splitlines()
    assert lines[0] == (
        "Student,Email,Week 1 (2026-10-01),Week 1 (2026-10-02),"
        "Sessions played,Attendance %,Average points,Total points"
    )
    assert lines[1] == "'=Zoe,zoe@gettysburg.edu,300,,1,50.0,300.0,300"
    assert lines[2] == "Amy Student,amy@gettysburg.edu,900,500,2,100.0,700.0,1400"
    assert lines[3] == "Member,member@gettysburg.edu,,,0,0.0,,0"
    assert denied.status_code == 403
