import csv
from datetime import UTC
from io import StringIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    Account,
    LiveSession,
    Question,
    QuizVersion,
    Response,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.services.session_end import get_final_results


def get_session_report(
    db: Session,
    account: CurrentAccount,
    session_id: int,
) -> dict:
    # Reuse PR #47's membership checks and ended-session requirement.
    final, viewer_id = get_final_results(db, account, session_id)

    session = db.get(LiveSession, session_id)
    version = db.get(QuizVersion, session.quiz_version_id)

    if version is None:
        raise APIError(
            500,
            "results_incomplete",
            "The quiz version is unavailable.",
        )

    host_name = db.scalar(
        select(Account.display_name).where(
            Account.account_id == session.host_id
        )
    )

    total = db.scalar(
        select(func.count())
        .select_from(SessionParticipant)
        .where(SessionParticipant.session_id == session_id)
    )

    ended_at = final.ended_at
    if ended_at is not None:
        ended_at = (
            ended_at.replace(tzinfo=UTC)
            if ended_at.tzinfo is None
            else ended_at
        )

    report = {
        "session_id": session_id,
        "view": "host" if viewer_id is None else "participant",
        "status": final.status,
        "quiz_title": version.title,
        "host_name": host_name,
        "ended_at": ended_at.isoformat() if ended_at else None,
        "total_participants": int(total or 0),
        "played_count": 0,
        "questions": [],
        "players": [],
    }

    if final.status == "CANCELLED":
        return report

    questions = db.scalars(
        select(Question)
        .where(Question.quiz_version_id == session.quiz_version_id)
        .options(selectinload(Question.choices))
        .order_by(Question.question_order)
    ).all()

    played = {
        row.question_id: row
        for row in db.scalars(
            select(SessionQuestion).where(
                SessionQuestion.session_id == session_id,
                SessionQuestion.status == SessionQuestionStatus.CLOSED,
            )
        ).all()
    }

    report["played_count"] = len(played)

    report["questions"] = [
        {
            "question_id": q.question_id,
            "order": q.question_order,
            "text": q.question_text,
            "explanation": q.explanation,
            "seconds": q.time_limit_seconds,
            "base_points": q.base_points,
            "played": q.question_id in played,
            "choices": [
                {
                    "id": c.choice_id,
                    "text": c.choice_text,
                    "correct": c.is_correct,
                }
                for c in q.choices
            ],
        }
        for q in questions
    ]

    # Participants receive only their own stored responses,
    # including after leaving the session.
    query = (
        select(Response)
        .join(
            SessionQuestion,
            SessionQuestion.session_question_id
            == Response.session_question_id,
        )
        .join(
            SessionParticipant,
            SessionParticipant.session_participant_id
            == Response.session_participant_id,
        )
        .where(
            SessionQuestion.session_id == session_id,
            SessionQuestion.status == SessionQuestionStatus.CLOSED,
            SessionParticipant.session_id == session_id,
        )
    )

    if viewer_id is not None:
        query = query.where(
            Response.session_participant_id == viewer_id
        )

    responses = {
        (r.session_participant_id, r.session_question_id): r
        for r in db.scalars(query).all()
    }

    standings = [
        row
        for row in final.standings
        if viewer_id is None
        or row.session_participant_id == viewer_id
    ]

    for row in standings:
        answers = []

        for q in questions:
            sq = played.get(q.question_id)

            response = (
                responses.get(
                    (
                        row.session_participant_id,
                        sq.session_question_id,
                    )
                )
                if sq
                else None
            )

            state = (
                "not_played"
                if sq is None
                else "missed"
                if response is None
                else "correct"
                if response.is_correct
                else "wrong"
            )

            answers.append(
                {
                    "question_id": q.question_id,
                    "state": state,
                    "choice_id": response.choice_id if response else None,
                    "points": response.points_awarded if response else 0,
                    "time_ms": response.response_time_ms if response else None,
                }
            )

        report["players"].append(
            {
                "id": row.session_participant_id,
                "name": row.display_name,
                "rank": row.final_rank,
                "points": row.total_score,
                "correct": row.correct_count,
                "answers": answers,
            }
        )

    return report


def export_session_report(
    db: Session,
    account: CurrentAccount,
    session_id: int,
) -> str:
    report = get_session_report(db, account, session_id)

    if report["view"] != "host":
        raise APIError(
            403,
            "results_export_denied",
            "Only the host or an Admin can export.",
        )

    def safe(value):
        # Prevent spreadsheet formulas in names and question/answer text.
        if (
            isinstance(value, str)
            and value.lstrip().startswith(("=", "+", "-", "@"))
        ):
            return "'" + value

        return value

    output = StringIO(newline="")
    writer = csv.writer(output)

    def write(row):
        writer.writerow([safe(value) for value in row])

    write(["Quiz", report["quiz_title"], "Session", session_id])

    scores = [p["points"] for p in report["players"]]

    write(
        [
            "High points",
            max(scores, default=0),
            "Average points",
            round(sum(scores) / len(scores), 2) if scores else 0,
            "Low points",
            min(scores, default=0),
        ]
    )

    write([])
    write(["Rank", "Participant", "Total points", "Correct answers"])

    for p in report["players"]:
        write([p["rank"], p["name"], p["points"], p["correct"]])

    write([])
    write(
        [
            "Participant",
            "Question",
            "Question text",
            "State",
            "Selected answer",
            "Correct answer",
            "Time (seconds)",
            "Points",
        ]
    )

    for p in report["players"]:
        for q, answer in zip(
            report["questions"],
            p["answers"],
            strict=True,
        ):
            choices = {c["id"]: c["text"] for c in q["choices"]}

            correct = " / ".join(
                c["text"] for c in q["choices"] if c["correct"]
            )

            write(
                [
                    p["name"],
                    q["order"],
                    q["text"],
                    answer["state"],
                    choices.get(answer["choice_id"], ""),
                    correct,
                    (
                        answer["time_ms"] / 1000
                        if answer["time_ms"] is not None
                        else ""
                    ),
                    answer["points"],
                ]
            )

    return output.getvalue()
