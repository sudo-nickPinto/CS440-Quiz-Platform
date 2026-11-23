import csv
from io import BytesIO, StringIO

from openpyxl import load_workbook

from app.api.routes import live
from tests.integration.approval_support import approval_class  # noqa: F401
from tests.integration.live_approval_support import (
    answer_question,
    connected,
    create_session,
    end_session,
    join_session,
    open_question,
)


def question(prompt: str) -> dict:
    return {
        "question_text": prompt,
        "choices": [
            {"choice_text": "Yes", "is_correct": True},
            {"choice_text": "No", "is_correct": False},
        ],
    }


def complete_one_question(course, session, player: str, *, correct: bool) -> None:
    join_session(course, player, session)
    with (
        connected(course, "organizer", session) as (host, _),
        connected(course, player, session) as (socket, _),
    ):
        opened = open_question(host, socket, 1)
        answer_question(host, socket, opened, choice_index=0 if correct else 1)
        end_session(host, socket, session["session_id"])


def test_saved_revision_preserves_live_snapshot_search_and_gradebook(
    approval_class, monkeypatch
) -> None:
    course = approval_class
    monkeypatch.setattr(live, "IDLE_TIMEOUT_SECONDS", 15)
    original = {
        "title": "Original review quiz",
        "questions": [question("Original first?"), question("Original second?")],
    }
    updated = {
        "title": "Updated review quiz",
        "questions": [question("Updated first?"), question("Updated second?")],
    }
    approved = course.approve_quiz("owner", original)
    quiz_path = f"{course.path}/quizzes/{approved['quiz_id']}"
    hosted = create_session(course, "owner", approved)
    original_version = approved["version"]
    assert hosted["quiz_version_id"] == original_version["quiz_version_id"]
    join_session(course, "editor", hosted)

    with (
        connected(course, "owner", hosted) as (host, _),
        connected(course, "editor", hosted) as (player, _),
    ):
        first = open_question(host, player, 1)
        assert first["question_text"] == "Original first?"
        answer_question(host, player, first, choice_index=0)

        saved = course.request(
            "owner", "PUT", quiz_path,
            json={**updated, "expected_revision": approved["revision"]},
        ).json()
        publication = course.publish("owner", saved)
        assert publication["version"]["quiz_version_id"] != hosted["quiz_version_id"]
        course.approve(course.submit("owner", publication))

        # The second question is opened only after the new version exists.
        second = open_question(host, player, 2)
        assert second["question_text"] == "Original second?"
        assert [choice["choice_id"] for choice in second["choices"]] == [
            choice["choice_id"] for choice in original_version["questions"][1]["choices"]
        ]
        answer_question(host, player, second, choice_index=0)
        end_session(host, player, hosted["session_id"])

    played = create_session(course, "organizer", publication)
    assert played["quiz_version_id"] == publication["version"]["quiz_version_id"]
    complete_one_question(course, played, "owner", correct=False)
    other = course.approve_quiz("organizer", {
        "title": "Another review quiz", "questions": [question("Another question?")],
    })
    missed = create_session(course, "organizer", other)
    complete_one_question(course, missed, "editor", correct=True)

    hosted_id = hosted["session_id"]
    saved_session = course.request("owner", "GET", f"/sessions/{hosted_id}").json()
    assert saved_session["quiz_version_id"] == original_version["quiz_version_id"]
    assert saved_session["quiz_title"] == original["title"]
    report = course.request(
        "organizer", "GET", f"{course.path}/sessions/{hosted_id}/results"
    ).json()
    assert report["quiz_title"] == original["title"]
    assert [row["text"] for row in report["questions"]] == ["Original first?", "Original second?"]
    assert [row["question_id"] for row in report["questions"]] == [
        row["question_id"] for row in original_version["questions"]
    ]

    history = f"{course.path}/sessions"
    matches = course.request(
        "owner", "GET", history, params={"q": "  ORIGINAL REVIEW  ", "page_size": 1}
    ).json()
    assert matches["pagination"]["total_items"] == 1
    [row] = matches["items"]
    assert (row["session_id"], row["quiz_title"], row["is_host"]) == (
        hosted_id, original["title"], True,
    )
    [new_match] = course.request(
        "owner", "GET", history, params={"q": "updated review"}
    ).json()["items"]
    assert new_match["session_id"] == played["session_id"]

    owner_id = course.accounts["owner"].account_id
    student_path = f"{course.path}/students/{owner_id}"
    student = course.request("organizer", "GET", f"{student_path}/results").json()
    assert (
        student["class_session_count"], student["session_count"],
        student["attendance_session_count"], student["attendance_rate"],
    ) == (3, 1, 2, 0.5)
    by_session = {row["session_id"]: row for row in student["sessions"]}
    assert {
        sid: (row["attendance_status"], row["points"], row["rank"])
        for sid, row in by_session.items()
    } == {
        hosted_id: ("HOSTED", None, None),
        played["session_id"]: ("PLAYED", 0, 1),
        missed["session_id"]: ("ABSENT", None, None),
    }

    csv_response = course.request("organizer", "GET", f"{course.path}/grades/export.csv")
    rows = csv.DictReader(StringIO(csv_response.content.decode("utf-8-sig")))
    owner = next(row for row in rows if row["Email"] == "owner@test.invalid")
    scores = {heading.split(" (")[0]: cell for heading, cell in owner.items() if " (" in heading}
    assert scores == {original["title"]: "Hosted", updated["title"]: "0", other["version"]["title"]: ""}
    assert (owner["Sessions played"], owner["Attendance %"]) == ("1", "50.0")

    xlsx = course.request("organizer", "GET", f"{student_path}/export.xlsx")
    workbook = load_workbook(BytesIO(xlsx.content))
    summary = dict(workbook["Summary"].values)
    assert (summary["Sessions played"], summary["Attendance sessions"], summary["Attendance %"]) == (
        1, 2, 50,
    )
    headers, *exported = workbook["Sessions"].values
    sheets_by_id = {
        row["Session ID"]: row for row in (dict(zip(headers, values, strict=True)) for values in exported)
    }
    assert {
        sid: (row["Attendance"], row["Points"], row["Rank"])
        for sid, row in sheets_by_id.items()
    } == {
        hosted_id: ("Hosted", None, None),
        played["session_id"]: ("Played", 0, 1),
        missed["session_id"]: ("Absent", None, None),
    }
