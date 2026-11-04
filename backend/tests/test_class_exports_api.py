"""Excel exports of the class reports (task 9).

Uses the same class as test_class_reports_api.py: two completed sessions
of "Week 1", plus a cancelled, an open and another class's session that
must never appear. Every test opens the workbook and checks its cells.
"""

from datetime import datetime
from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.models import Account, Question, QuizVersion
from tests.test_class_reports_api import (  # noqa: F401 (reports is a fixture)
    act_as,
    quiz_url,
    reports,
    session_url,
    student_url,
)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def export_url(report_url: str) -> str:
    return report_url.removesuffix("/results") + "/export.xlsx"


def workbook(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == XLSX
    assert response.headers["cache-control"] == "no-store"
    return load_workbook(BytesIO(response.content))


def rows(sheet) -> list[list]:
    return [list(row) for row in sheet.iter_rows(min_row=2, values_only=True)]


def summary(book) -> dict:
    return {field: value for field, value in rows(book["Summary"])}


# Session export


def test_organizer_session_export_matches_the_report(reports) -> None:
    client, identities, data = reports
    act_as(client, identities["coorg"])
    report = client.get(session_url(data, "first")).json()

    response = client.get(export_url(session_url(data, "first")))
    book = workbook(response)

    assert response.headers["content-disposition"] == (
        "attachment; "
        f'filename="class-{data["class_id"]}-session-{data["first"]}-results.xlsx"'
    )
    assert book.sheetnames == ["Summary", "Scores", "Answers"]

    info = summary(book)
    assert info["Quiz"] == "Week 1"
    assert info["Session ID"] == data["first"]
    assert info["Participants"] == report["total_participants"]
    assert info["Questions played"] == 2
    assert info["High points"] == 900
    assert isinstance(info["Started (UTC)"], datetime)

    assert rows(book["Scores"]) == [
        [player["rank"], player["name"], player["points"], player["correct"]]
        for player in report["players"]
    ]

    answers = rows(book["Answers"])
    assert len(answers) == len(report["players"]) * len(report["questions"])
    zoe_second = next(
        row for row in answers if row[0] == "Zoe Student" and row[1] == 2
    )
    assert zoe_second[2:6] == ["Question 2?", "Wrong", "Wrong", "Right"]
    assert zoe_second[7] == 0


@pytest.mark.parametrize("session", ["cancelled", "open", "elsewhere"])
def test_session_export_outside_the_class_history_is_missing(reports, session) -> None:
    client, _, data = reports

    response = client.get(export_url(session_url(data, session)))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "session_not_found"


# Quiz export


def test_quiz_export_lists_every_completed_presentation(reports) -> None:
    client, _, data = reports
    report = client.get(quiz_url(data)).json()

    response = client.get(export_url(quiz_url(data)))
    book = workbook(response)

    assert response.headers["content-disposition"] == (
        "attachment; "
        f'filename="class-{data["class_id"]}-quiz-{data["quiz_id"]}-results.xlsx"'
    )
    info = summary(book)
    assert info["Quiz"] == "Week 1"
    assert info["Completed presentations"] == 2
    assert info["Total participations"] == report["participant_count"]
    assert info["Average points"] == report["average_score"]

    presentations = rows(book["Presentations"])
    assert [row[1] for row in presentations] == [
        session["session_id"] for session in report["sessions"]
    ]
    assert {row[1] for row in presentations} == {data["first"], data["second"]}

    assert [row[1:] for row in rows(book["Results"])] == [
        [
            session["session_id"],
            result["rank"],
            result["name"],
            result["points"],
            result["correct"],
        ]
        for session in report["sessions"]
        for result in session["results"]
    ]


# Student export


def test_organizer_student_export_includes_email_and_class_average(reports) -> None:
    client, _, data = reports
    report = client.get(student_url(data, "zoe")).json()

    book = workbook(client.get(export_url(student_url(data, "zoe"))))

    info = summary(book)
    assert info["Student"] == "Zoe Student"
    assert info["Email"] == "zoe@gettysburg.edu"
    assert info["Class average"] == report["class_average"]
    assert info["Total points"] == report["total_points"]
    assert info["Sessions played"] == 1
    assert info["Class sessions"] == 2

    sessions = rows(book["Sessions"])
    assert [row[1] for row in sessions] == [
        session["session_id"] for session in report["sessions"]
    ]
    # Zoe missed the second session and played the first.
    assert [row[3] for row in sessions] == ["No", "Yes"]


def test_member_can_export_only_their_own_results(reports) -> None:
    client, identities, data = reports
    act_as(client, identities["amy"])

    info = summary(workbook(client.get(export_url(student_url(data, "amy")))))
    assert info["Student"] == "Amy Student"
    assert "Email" not in info
    assert "Class average" not in info

    response = client.get(export_url(student_url(data, "zoe")))
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_class_organizer"


# Access


def test_members_cannot_export_class_wide_reports(reports) -> None:
    client, identities, data = reports
    act_as(client, identities["amy"])

    for url in (session_url(data, "first"), quiz_url(data)):
        response = client.get(export_url(url))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "not_class_organizer"


@pytest.mark.parametrize("name", ["nonmember", "invited", "rex", "global"])
def test_people_without_active_membership_cannot_export(reports, name) -> None:
    client, identities, data = reports
    act_as(client, identities[name])

    for url in (
        session_url(data, "first"),
        quiz_url(data),
        student_url(data, "amy"),
    ):
        response = client.get(export_url(url))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "class_not_found"


# Spreadsheet safety


def test_exports_keep_formula_text_as_plain_text(reports) -> None:
    client, _, data = reports
    attack = '=HYPERLINK("http://example.com","click")'
    with client.app.state.database.session_factory() as db:
        db.get(Account, data["ids"]["amy"]).display_name = attack
        # A control character openpyxl would refuse to write.
        db.get(Account, data["ids"]["zoe"]).display_name = "Zoe\x07 Student"
        first_question = db.scalars(
            select(Question).order_by(Question.question_id)
        ).first()
        first_question.question_text = "+1"
        # Only a formula once the control character is dropped.
        db.scalars(select(QuizVersion)).one().title = "\x01=1+1"
        db.commit()

    books = [
        workbook(client.get(export_url(url)))
        for url in (
            session_url(data, "first"),
            quiz_url(data),
            student_url(data, "amy"),
        )
    ]

    for book in books:
        for sheet in book.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    assert cell.data_type != "f", (sheet.title, cell.coordinate)

    session_book, quiz_book, student_book = books
    assert rows(session_book["Scores"])[0][1] == "'" + attack
    assert {row[1] for row in rows(session_book["Scores"])} >= {"Zoe Student"}
    assert any(row[2] == "'+1" for row in rows(session_book["Answers"]))
    assert rows(quiz_book["Results"])[0][3] == "'" + attack
    assert summary(student_book)["Student"] == "'" + attack
    assert summary(session_book)["Quiz"] == "'=1+1"
    assert summary(quiz_book)["Quiz"] == "'=1+1"
    assert rows(student_book["Sessions"])[0][2] == "'=1+1"
