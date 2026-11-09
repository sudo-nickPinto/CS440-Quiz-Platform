"""Joining a class by code and reading its reports, on migrated MySQL.

A faculty account makes a class, students join it with the code (PR #69),
and real games are played over REST and the host's socket. The dashboard,
gradebook CSV (PR #69), JSON reports and Excel exports (PR #79) are then
checked against the Result rows those games stored. Every request carries
a real signed token, so the account lookup runs too.
"""

import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO, StringIO
from threading import Barrier

from openpyxl import load_workbook
from sqlalchemy import func, select

from app.errors import APIError
from app.models import (
    Account,
    ClassMembership,
    LiveSession,
    LiveSessionStatus,
    MembershipStatus,
    Result,
    SessionParticipant,
)
from app.schemas.classes import ClassJoin
from app.services.classes import join_class
from tests.class_quiz_helpers import add_member, approve_quiz, publish_quiz
from tests.integration.live_support import (  # noqa: F401
    bearer,
    mysql_live,
    stored_session,
)
from tests.test_live_host_controls import connect, open_question, receive_until

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
QUIZ = {
    "title": "Reports Quiz",
    "questions": [
        {
            "question_text": f"Question {n}?",
            "time_limit_seconds": 30,
            "choices": [
                {"choice_text": "Right", "is_correct": True},
                {"choice_text": "Wrong", "is_correct": False},
            ],
        }
        for n in (1, 2)
    ],
}
# The first game is moved back to a fixed day so the two games have a known
# order and the gradebook column has a known date.
FIRST_GAME_STARTED = datetime(2025, 9, 2, 14, 0)


def get(client, name: str, url: str, **params):
    return client.get(url, params=params, headers=bearer(name))


def error_code(response) -> str:
    return response.json()["error"]["code"]


def join_by_code(client, name: str, code: str):
    return client.post("/classes/join", json={"code": code}, headers=bearer(name))


def create_class(client) -> dict:
    created = client.post(
        "/classes", json={"name": "CS 440 Reports"}, headers=bearer("faculty")
    )
    assert created.status_code == 201, created.text
    return created.json()


def create_quiz(client, class_id: int) -> int:
    created = client.post(
        f"/classes/{class_id}/quizzes", json=QUIZ, headers=bearer("faculty")
    )
    assert created.status_code == 201, created.text
    quiz_id = created.json()["quiz_id"]
    publish_quiz(client, quiz_id)
    approve_quiz(client, quiz_id)
    return quiz_id


def play_game(client, class_id: int, quiz_id: int, picks: dict[str, list[bool]]) -> int:
    """The faculty account hosts one game; each player answers over REST.

    picks maps a player to right/wrong per question, and the game ends after
    as many questions as the lists hold.
    """
    started = client.post(
        f"/classes/{class_id}/quizzes/{quiz_id}/sessions", headers=bearer("faculty")
    )
    assert started.status_code == 201, started.text
    session_id = started.json()["session_id"]
    for name in picks:
        joined = client.post(
            "/sessions/join",
            json={"join_code": started.json()["join_code"]},
            headers=bearer(name),
        )
        assert joined.status_code == 201, joined.text

    host_cm, host, _ = connect(client, session_id, "faculty")
    for index in range(len(next(iter(picks.values())))):
        opened = open_question(host, index + 1)
        for name, right in picks.items():
            choice = opened["choices"][0 if right[index] else 1]["choice_id"]
            sent = client.post(
                f"/sessions/{session_id}/questions/"
                f"{opened['session_question_id']}/responses",
                json={"choice_id": choice},
                headers=bearer(name),
            )
            assert sent.status_code == 201, sent.text
        # The last answer closes the question for everyone.
        assert receive_until(host, "question_results")
    host.send_json({"type": "end_session"})
    assert receive_until(host, "session_ended")[-1]["reason"] == "COMPLETED"
    host_cm.__exit__(None, None, None)
    return session_id


def stored_results(client, session_id: int) -> dict[str, tuple[int, int, int]]:
    """Each player's (points, correct, rank) from the Result rows."""
    with client.app.state.database.session_factory() as db:
        rows = db.execute(
            select(
                Account.display_name,
                Result.total_score,
                Result.correct_count,
                Result.final_rank,
            )
            .join(
                SessionParticipant,
                SessionParticipant.session_participant_id
                == Result.session_participant_id,
            )
            .join(Account, Account.account_id == SessionParticipant.account_id)
            .where(SessionParticipant.session_id == session_id)
        ).all()
    return {name: (points, correct, rank) for name, points, correct, rank in rows}


def played_class(client) -> dict:
    """A class joined by code with two finished games of one quiz.

    Alice plays both (2 of 2 right, then 1 of 1); Bob only the first
    (1 of 2 right).
    """
    class_ = create_class(client)
    code = class_["join_code"]
    bare = code.replace("-", "")
    # Students type the code however they like.
    for name, typed in (
        ("alice", f" {code.lower()} "),
        ("bob", f"{bare[:4]} {bare[4:]}"),
    ):
        joined = join_by_code(client, name, typed)
        assert joined.status_code == 200, joined.text

    class_id = class_["class_id"]
    quiz_id = create_quiz(client, class_id)
    first = play_game(
        client, class_id, quiz_id, {"alice": [True, True], "bob": [False, True]}
    )
    second = play_game(client, class_id, quiz_id, {"alice": [True]})

    with client.app.state.database.session_factory() as db:
        session = db.get(LiveSession, first)
        session.started_at = FIRST_GAME_STARTED
        db.commit()

    return {
        "class_id": class_id,
        "code": code,
        "quiz_id": quiz_id,
        "first": first,
        "second": second,
        "second_started": stored_session(client, second).started_at,
        "results": {
            first: stored_results(client, first),
            second: stored_results(client, second),
        },
    }


def workbook(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == XLSX
    assert response.headers["cache-control"] == "no-store"
    return load_workbook(BytesIO(response.content))


def rows(sheet) -> list[list]:
    return [list(row) for row in sheet.iter_rows(min_row=2, values_only=True)]


def summary(book) -> dict:
    return {field: value for field, value in rows(book["Summary"])}


def blank(value) -> bool:
    return value in (None, "")


def test_faculty_class_is_joined_by_code(mysql_live) -> None:
    client, people = mysql_live

    # Only faculty can make a class.
    refused = client.post("/classes", json={"name": "Nope"}, headers=bearer("host"))
    assert refused.status_code == 403
    assert error_code(refused) == "faculty_required"

    class_ = create_class(client)
    class_id, code = class_["class_id"], class_["join_code"]
    assert class_["current_role"] == "ORGANIZER"
    # Shown as ABCD-2345; typed with any case, spacing or hyphen.
    bare = code.replace("-", "")
    assert code == f"{bare[:4]}-{bare[4:]}" and len(bare) == 8

    joined = join_by_code(client, "alice", f" {bare.lower()} ")
    assert joined.status_code == 200, joined.text
    assert joined.json()["class_id"] == class_id
    assert joined.json()["current_role"] == "MEMBER"
    assert joined.json()["membership_status"] == "ACTIVE"

    again = join_by_code(client, "alice", code)
    assert again.status_code == 409
    assert error_code(again) == "already_class_member"
    # Generated codes never use 0, so this one can't exist.
    wrong = join_by_code(client, "outsider", "NOPE0000")
    assert wrong.status_code == 404
    assert error_code(wrong) == "class_code_not_found"

    # A closed class turns the right code away until it reopens.
    closed = client.patch(
        f"/classes/{class_id}", json={"joining_open": False}, headers=bearer("faculty")
    )
    assert closed.status_code == 200, closed.text
    shut_out = join_by_code(client, "bob", code)
    assert shut_out.status_code == 403
    assert error_code(shut_out) == "class_joining_closed"
    client.patch(
        f"/classes/{class_id}", json={"joining_open": True}, headers=bearer("faculty")
    )
    assert join_by_code(client, "bob", code).status_code == 200

    # Leaving and coming back reuses the same membership row.
    left = client.delete(f"/classes/{class_id}/membership", headers=bearer("bob"))
    assert left.status_code == 204
    assert get(client, "bob", f"/classes/{class_id}").status_code == 404
    back = join_by_code(client, "bob", code)
    assert back.status_code == 200, back.text
    assert back.json()["membership_status"] == "ACTIVE"

    # Someone an organizer removed can't let themselves back in.
    add_member(client, class_id, people["alice"].account_id, MembershipStatus.REMOVED)
    removed = join_by_code(client, "alice", code)
    assert removed.status_code == 403
    assert error_code(removed) == "class_member_removed"

    with client.app.state.database.session_factory() as db:
        memberships = db.execute(
            select(Account.display_name, ClassMembership.status)
            .join(Account, Account.account_id == ClassMembership.account_id)
            .where(ClassMembership.class_id == class_id)
            .order_by(Account.display_name)
        ).all()
    assert [tuple(row) for row in memberships] == [
        ("Alice", MembershipStatus.REMOVED),
        ("Bob", MembershipStatus.ACTIVE),
        ("Faculty", MembershipStatus.ACTIVE),
    ]


def test_simultaneous_joins_add_each_person_once(mysql_live) -> None:
    client, people = mysql_live
    class_ = create_class(client)
    # Alice double-submits the form while Bob joins with the same code.
    joiners = [people["alice"], people["alice"], people["bob"]]
    barrier = Barrier(len(joiners))

    def run(account):
        with client.app.state.database.session_factory() as db:
            barrier.wait()
            try:
                joined = join_class(db, account, ClassJoin(code=class_["join_code"]))
                return joined.membership_status.value
            except APIError as exc:
                return exc.code

    with ThreadPoolExecutor(max_workers=len(joiners)) as executor:
        futures = [executor.submit(run, account) for account in joiners]
        outcomes = [future.result(timeout=10) for future in futures]

    assert sorted(outcomes[:2]) == ["ACTIVE", "already_class_member"]
    assert outcomes[2] == "ACTIVE"
    with client.app.state.database.session_factory() as db:
        counts = dict(
            db.execute(
                select(ClassMembership.account_id, func.count())
                .where(ClassMembership.class_id == class_["class_id"])
                .group_by(ClassMembership.account_id)
            ).all()
        )
    assert counts == {
        people["faculty"].account_id: 1,
        people["alice"].account_id: 1,
        people["bob"].account_id: 1,
    }


def test_dashboard_and_gradebook_match_the_stored_results(mysql_live) -> None:
    client, people = mysql_live
    data = played_class(client)
    class_id, first, second = data["class_id"], data["first"], data["second"]
    a1, b1 = data["results"][first]["Alice"][0], data["results"][first]["Bob"][0]
    a2 = data["results"][second]["Alice"][0]
    assert data["results"][first]["Alice"][1:] == (2, 1)
    assert data["results"][first]["Bob"][1:] == (1, 2)
    assert data["results"][second] == {"Alice": (a2, 1, 1)}
    alice_average = round((a1 + a2) / 2, 1)

    dashboard = get(client, "faculty", f"/classes/{class_id}/dashboard")
    assert dashboard.status_code == 200, dashboard.text
    board = dashboard.json()
    assert board["class_name"] == "CS 440 Reports"
    assert board["current_user_role"] == "ORGANIZER"
    assert (
        board["active_member_count"],
        board["student_count"],
        board["completed_session_count"],
    ) == (3, 2, 2)
    assert board["active_sessions"] == []
    assert board["class_average"] == round((alice_average + b1) / 2, 1)
    assert board["attendance_rate"] == 0.75
    # Newest first; the first game was moved back in time.
    assert [s["session_id"] for s in board["completed_sessions"]] == [second, first]
    assert board["completed_sessions"][1]["started_at"].startswith(
        "2025-09-02T14:00:00"
    )
    assert [
        (q["quiz_id"], q["title"], q["session_count"], q["participant_count"])
        for q in board["presented_quizzes"]
    ] == [(data["quiz_id"], "Reports Quiz", 2, 3)]
    assert board["presented_quizzes"][0]["average_score"] == round(
        (a1 + b1 + a2) / 3, 1
    )
    students = {s["display_name"]: s for s in board["students"]}
    assert (
        students["Alice"]["session_count"],
        students["Alice"]["attendance_rate"],
        students["Alice"]["total_points"],
        students["Alice"]["average_score"],
        students["Alice"]["recent_scores"],
    ) == (2, 1.0, a1 + a2, alice_average, [a2, a1])
    assert (
        students["Bob"]["session_count"],
        students["Bob"]["attendance_rate"],
        students["Bob"]["total_points"],
        students["Bob"]["recent_scores"],
    ) == (1, 0.5, b1, [None, b1])

    sessions = get(client, "faculty", f"/classes/{class_id}/sessions").json()
    assert [
        (s["session_id"], s["participant_count"], s["top_score"], s["average_score"])
        for s in sessions["items"]
    ] == [
        (second, 1, a2, float(a2)),
        (first, 2, max(a1, b1), round((a1 + b1) / 2, 1)),
    ]
    assert all(s["host_name"] == "Faculty" for s in sessions["items"])

    # The roster pages through students by sessions played.
    pages = [
        get(
            client,
            "faculty",
            f"/classes/{class_id}/students",
            sort="session_count",
            order="desc",
            page=page,
            page_size=1,
        ).json()
        for page in (1, 2)
    ]
    assert [p["items"][0]["display_name"] for p in pages] == ["Alice", "Bob"]
    assert pages[0]["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total_items": 2,
        "total_pages": 2,
    }

    # The gradebook: one column per game, oldest first; blank means absent.
    export = get(client, "faculty", f"/classes/{class_id}/grades/export.csv")
    assert export.status_code == 200, export.text
    assert export.headers["content-type"] == "text/csv; charset=utf-8"
    assert export.headers["content-disposition"] == (
        'attachment; filename="cs-440-reports-grades.csv"'
    )
    assert export.text.startswith("﻿")
    header, *lines = csv.reader(StringIO(export.text.removeprefix("﻿")))
    assert header == [
        "Student",
        "Email",
        "Reports Quiz (2025-09-02)",
        f"Reports Quiz ({data['second_started']:%Y-%m-%d})",
        "Sessions played",
        "Attendance %",
        "Average points",
        "Total points",
    ]
    assert lines == [
        [
            "Alice",
            "alice@test.invalid",
            str(a1),
            str(a2),
            "2",
            "100.0",
            str(alice_average),
            str(a1 + a2),
        ],
        ["Bob", "bob@test.invalid", str(b1), "", "1", "50.0", str(float(b1)), str(b1)],
    ]

    # A member sees their own numbers but none of the class-wide ones.
    mine = get(client, "alice", f"/classes/{class_id}/dashboard").json()
    assert mine["current_user_role"] == "MEMBER"
    assert mine["students"] is None
    assert mine["class_average"] is None and mine["attendance_rate"] is None
    assert [
        (s["my_score"], s["my_rank"], s["average_score"], s["top_score"])
        for s in mine["completed_sessions"]
    ] == [(a2, 1, None, None), (a1, 1, None, None)]
    for url in ("students", "grades/export.csv"):
        refused = get(client, "alice", f"/classes/{class_id}/{url}")
        assert refused.status_code == 403
        assert error_code(refused) == "not_class_organizer"
    hidden = get(client, "outsider", f"/classes/{class_id}/dashboard")
    assert hidden.status_code == 404
    assert error_code(hidden) == "class_not_found"


def test_spreadsheet_exports_match_the_json_reports(mysql_live) -> None:
    client, people = mysql_live
    data = played_class(client)
    class_id, first, second = data["class_id"], data["first"], data["second"]
    base = f"/classes/{class_id}"

    for session_id, players, played in ((first, 2, 2), (second, 1, 1)):
        report = get(client, "faculty", f"{base}/sessions/{session_id}/results").json()
        assert report["status"] == "COMPLETED"
        assert report["played_count"] == played
        stored = data["results"][session_id]
        assert {
            p["name"]: (p["points"], p["correct"], p["rank"]) for p in report["players"]
        } == stored

        response = get(client, "faculty", f"{base}/sessions/{session_id}/export.xlsx")
        book = workbook(response)
        assert response.headers["content-disposition"] == (
            "attachment; "
            f'filename="class-{class_id}-session-{session_id}-results.xlsx"'
        )
        assert book.sheetnames == ["Summary", "Scores", "Answers"]
        info = summary(book)
        points = [value[0] for value in stored.values()]
        assert (
            info["Quiz"],
            info["Class ID"],
            info["Session ID"],
            info["Host"],
            info["Participants"],
            info["Questions played"],
            info["High points"],
            info["Low points"],
        ) == (
            "Reports Quiz",
            class_id,
            session_id,
            "Faculty",
            players,
            played,
            max(points),
            min(points),
        )
        assert rows(book["Scores"]) == [
            [p["rank"], p["name"], p["points"], p["correct"]]
            for p in report["players"]
        ]
        # One row per player and quiz question, played or not.
        assert len(rows(book["Answers"])) == players * len(QUIZ["questions"])
    # MySQL's naive UTC time comes back out as the same wall-clock time.
    first_book = workbook(get(client, "faculty", f"{base}/sessions/{first}/export.xlsx"))
    assert summary(first_book)["Started (UTC)"] == FIRST_GAME_STARTED

    quiz_url = f"{base}/quizzes/{data['quiz_id']}"
    quiz_report = get(client, "faculty", f"{quiz_url}/results").json()
    assert (quiz_report["session_count"], quiz_report["participant_count"]) == (2, 3)
    book = workbook(get(client, "faculty", f"{quiz_url}/export.xlsx"))
    assert book.sheetnames == ["Summary", "Presentations", "Results"]
    info = summary(book)
    assert (info["Completed presentations"], info["Total participations"]) == (2, 3)
    assert info["Average points"] == quiz_report["average_score"]
    assert [(row[1], row[3]) for row in rows(book["Presentations"])] == [
        (second, 1),
        (first, 2),
    ]
    exported = sorted(
        (row[1], row[3], row[4], row[5], row[2]) for row in rows(book["Results"])
    )
    assert exported == sorted(
        (session_id, name, points, correct, rank)
        for session_id, players in data["results"].items()
        for name, (points, correct, rank) in players.items()
    )

    # Bob's own sheet, as the organizer sees it: he missed the second game.
    bob = people["bob"].account_id
    student_report = get(client, "faculty", f"{base}/students/{bob}/results").json()
    book = workbook(get(client, "faculty", f"{base}/students/{bob}/export.xlsx"))
    assert book.sheetnames == ["Summary", "Sessions"]
    info = summary(book)
    assert info["Email"] == "bob@test.invalid"
    assert (info["Class sessions"], info["Sessions played"], info["Attendance %"]) == (
        2,
        1,
        50.0,
    )
    assert (info["Correct answers"], info["Incorrect answers"]) == (1, 1)
    assert info["Class average"] == student_report["class_average"]
    sessions = rows(book["Sessions"])
    assert [(row[1], row[3]) for row in sessions] == [(second, "No"), (first, "Yes")]
    assert all(blank(value) for value in sessions[0][4:8])
    assert sessions[1][4:] == [data["results"][first]["Bob"][0], 2, 1, 1, 2]


def test_members_export_only_their_own_report(mysql_live) -> None:
    client, people = mysql_live
    data = played_class(client)
    class_id, first, second = data["class_id"], data["first"], data["second"]
    base = f"/classes/{class_id}"
    alice, bob = people["alice"].account_id, people["bob"].account_id

    # Alice's own sheet leaves out other people's details.
    book = workbook(get(client, "alice", f"{base}/students/{alice}/export.xlsx"))
    info = summary(book)
    assert "Email" not in info and "Class average" not in info
    assert (info["Sessions played"], info["Correct answers"]) == (2, 3)
    assert [(row[1], row[3]) for row in rows(book["Sessions"])] == [
        (second, "Yes"),
        (first, "Yes"),
    ]
    mine = get(client, "alice", f"{base}/sessions/{first}/results")
    assert mine.status_code == 200
    assert mine.json()["view"] == "participant"

    for url in (
        f"students/{bob}/export.xlsx",
        f"students/{bob}/results",
        f"sessions/{first}/export.xlsx",
        f"quizzes/{data['quiz_id']}/export.xlsx",
    ):
        refused = get(client, "alice", f"{base}/{url}")
        assert refused.status_code == 403, url
        assert error_code(refused) == "not_class_organizer"
    missed = get(client, "bob", f"{base}/sessions/{second}/results")
    assert missed.status_code == 403
    assert error_code(missed) == "participant_report_denied"
    for url in (f"students/{alice}/export.xlsx", f"sessions/{first}/export.xlsx"):
        hidden = get(client, "outsider", f"{base}/{url}")
        assert hidden.status_code == 404, url
        assert error_code(hidden) == "class_not_found"

    # Bob leaves: off the roster, out of the class pages, history kept.
    assert client.delete(f"{base}/membership", headers=bearer("bob")).status_code == 204
    roster = get(client, "faculty", f"{base}/students").json()
    assert [s["display_name"] for s in roster["items"]] == ["Alice"]
    assert get(client, "bob", f"{base}/dashboard").status_code == 404
    kept = get(client, "faculty", f"{base}/students/{bob}/results").json()
    assert (kept["status"], kept["session_count"]) == ("LEFT", 1)

    # Rejoining with the code brings his old games back with him.
    assert join_by_code(client, "bob", data["code"]).status_code == 200
    roster = get(client, "faculty", f"{base}/students").json()
    assert [(s["display_name"], s["session_count"]) for s in roster["items"]] == [
        ("Alice", 2),
        ("Bob", 1),
    ]
    assert stored_session(client, first).status == LiveSessionStatus.COMPLETED
