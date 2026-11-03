"""Excel exports of the detailed class reports (task 9).

Each export is built from the matching report in class_reports.py, so a
workbook always shows the same numbers as the report page. Session and
quiz exports cover the whole class and are for active faculty organizers
only. A member can export only their own student report, which leaves out
the email and the class-wide average, as the report does.

Times are UTC.
"""

from fastapi import Response
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.services.class_authorization import require_class_organizer
from app.services.class_reports import (
    get_class_quiz_results,
    get_class_session_results,
    get_class_student_results,
)
from app.services.spreadsheet import (
    add_key_value_sheet,
    add_sheet,
    excel_datetime,
    new_workbook,
    xlsx_response,
)

RESULT_LABELS = {
    "correct": "Correct",
    "wrong": "Wrong",
    "missed": "No answer",
    "not_played": "Not played",
}


def _blank(value):
    """None becomes an empty cell rather than the text "None"."""
    return "" if value is None else value


def export_class_session(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    session_id: int,
) -> Response:
    require_class_organizer(db, account, class_id)
    report = get_class_session_results(db, account, class_id, session_id)

    players = report["players"]
    scores = [player["points"] for player in players]
    workbook = new_workbook()

    add_key_value_sheet(
        workbook,
        "Summary",
        [
            ("Quiz", report["quiz_title"]),
            ("Class ID", class_id),
            ("Session ID", session_id),
            ("Started (UTC)", excel_datetime(report["started_at"])),
            ("Ended (UTC)", _blank(excel_datetime(report["ended_at"]))),
            ("Host", _blank(report["host_name"])),
            ("Participants", report["total_participants"]),
            ("Questions played", report["played_count"]),
            ("High points", max(scores, default=0)),
            (
                "Average points",
                round(sum(scores) / len(scores), 2) if scores else 0,
            ),
            ("Low points", min(scores, default=0)),
        ],
    )

    add_sheet(
        workbook,
        "Scores",
        ["Rank", "Participant", "Total points", "Correct answers"],
        (
            [player["rank"], player["name"], player["points"], player["correct"]]
            for player in players
        ),
    )

    answer_rows = []
    for player in players:
        for question, answer in zip(report["questions"], player["answers"], strict=True):
            choices = {choice["id"]: choice["text"] for choice in question["choices"]}
            answer_rows.append(
                [
                    player["name"],
                    question["order"],
                    question["text"],
                    RESULT_LABELS.get(answer["state"], answer["state"]),
                    choices.get(answer["choice_id"], ""),
                    " / ".join(
                        choice["text"]
                        for choice in question["choices"]
                        if choice["correct"]
                    ),
                    (
                        answer["time_ms"] / 1000
                        if answer["time_ms"] is not None
                        else ""
                    ),
                    answer["points"],
                ]
            )

    add_sheet(
        workbook,
        "Answers",
        [
            "Participant",
            "Question",
            "Question text",
            "Result",
            "Selected answer",
            "Correct answer",
            "Time (seconds)",
            "Points",
        ],
        answer_rows,
    )

    return xlsx_response(
        workbook, f"class-{class_id}-session-{session_id}-results.xlsx"
    )


def export_class_quiz(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    quiz_id: int,
) -> Response:
    require_class_organizer(db, account, class_id)
    report = get_class_quiz_results(db, account, class_id, quiz_id)
    workbook = new_workbook()

    add_key_value_sheet(
        workbook,
        "Summary",
        [
            ("Quiz", report["title"]),
            ("Class ID", class_id),
            ("Quiz ID", quiz_id),
            ("Completed presentations", report["session_count"]),
            ("Total participations", report["participant_count"]),
            ("Average points", _blank(report["average_score"])),
        ],
    )

    add_sheet(
        workbook,
        "Presentations",
        [
            "Started (UTC)",
            "Session ID",
            "Host",
            "Participants",
            "Average points",
            "Top score",
        ],
        (
            [
                _blank(excel_datetime(session["started_at"])),
                session["session_id"],
                session["host_name"],
                session["participant_count"],
                _blank(session["average_score"]),
                _blank(session["top_score"]),
            ]
            for session in report["sessions"]
        ),
    )

    add_sheet(
        workbook,
        "Results",
        [
            "Started (UTC)",
            "Session ID",
            "Rank",
            "Participant",
            "Points",
            "Correct answers",
        ],
        (
            [
                _blank(excel_datetime(session["started_at"])),
                session["session_id"],
                result["rank"],
                result["name"],
                result["points"],
                result["correct"],
            ]
            for session in report["sessions"]
            for result in session["results"]
        ),
    )

    return xlsx_response(workbook, f"class-{class_id}-quiz-{quiz_id}-results.xlsx")


def export_class_student(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    account_id: int,
) -> Response:
    # The report itself limits members to their own results.
    report = get_class_student_results(db, account, class_id, account_id)
    organizer = report["view"] == "organizer"
    workbook = new_workbook()

    summary = [("Student", report["display_name"])]
    if organizer:
        summary.append(("Email", _blank(report["email"])))
    summary += [
        ("Role", report["role"]),
        ("Membership", report["status"]),
        ("Class sessions", report["class_session_count"]),
        ("Sessions played", report["session_count"]),
        (
            "Attendance %",
            (
                round(report["attendance_rate"] * 100, 1)
                if report["attendance_rate"] is not None
                else ""
            ),
        ),
        ("Total points", report["total_points"]),
        ("Average points", _blank(report["average_score"])),
        ("Correct answers", report["correct_count"]),
        ("Incorrect answers", report["incorrect_count"]),
    ]
    if organizer:
        summary.append(("Class average", _blank(report["class_average"])))
    add_key_value_sheet(workbook, "Summary", summary)

    add_sheet(
        workbook,
        "Sessions",
        [
            "Started (UTC)",
            "Session ID",
            "Quiz",
            "Played",
            "Points",
            "Rank",
            "Correct",
            "Incorrect",
            "Questions",
        ],
        (
            [
                excel_datetime(session["started_at"]),
                session["session_id"],
                session["quiz_title"],
                "Yes" if session["played"] else "No",
                _blank(session["points"]),
                _blank(session["rank"]),
                _blank(session["correct"]),
                _blank(session["incorrect"]),
                session["question_count"],
            ]
            for session in report["sessions"]
        ),
    )

    return xlsx_response(
        workbook, f"class-{class_id}-student-{account_id}-results.xlsx"
    )
