from datetime import datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import CurrentAccount
from app.live.protocol import CloseCode, LiveCloseError
from app.models import (
    LiveSession,
    LiveSessionStatus,
    Question,
    Response,
    SessionParticipant,
    SessionQuestion,
    SessionQuestionStatus,
)
from app.schemas.results import ClosedQuestionResultsSnapshot
from app.services.live_questions import _opened_event
from app.services.results import get_closed_question_results

LiveRole = Literal["host", "participant"]
LEADERBOARD_SIZE = 5


def resolve_membership(
    db: Session,
    session_id: int,
    account: CurrentAccount,
) -> tuple[LiveRole, int | None]:
    """Work out the caller's role from the database (protocol §2)."""
    session = db.get(LiveSession, session_id)
    if session is None:
        raise LiveCloseError(CloseCode.NOT_FOUND, "session_not_found")
    if session.status in (LiveSessionStatus.COMPLETED, LiveSessionStatus.CANCELLED):
        raise LiveCloseError(CloseCode.SESSION_OVER, "session_over")
    if session.host_id == account.account_id:
        return "host", None

    participant_id = db.scalar(
        select(SessionParticipant.session_participant_id).where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.account_id == account.account_id,
            SessionParticipant.left_at.is_(None),
        )
    )
    if participant_id is None:
        raise LiveCloseError(CloseCode.FORBIDDEN, "session_access_denied")
    return "participant", participant_id


def host_results_view(snapshot: ClosedQuestionResultsSnapshot) -> dict:
    return {"type": "question_results", **snapshot.model_dump()}


def participant_results_view(
    snapshot: ClosedQuestionResultsSnapshot,
    session_participant_id: int | None,
) -> dict:
    """Cut results down to the caller's own row plus the top of the board (§4)."""
    me = next(
        (
            row
            for row in snapshot.participants
            if row.session_participant_id == session_participant_id
        ),
        None,
    )
    return {
        "type": "question_results",
        "session_id": snapshot.session_id,
        "session_question_id": snapshot.session_question_id,
        "correct_choice_ids": snapshot.correct_choice_ids,
        "choices": [choice.model_dump() for choice in snapshot.choices],
        "me": me.model_dump() if me else None,
        "leaderboard": [
            {
                "display_name": row.display_name,
                "cumulative_score": row.cumulative_score,
                "rank": row.rank,
            }
            for row in snapshot.participants[:LEADERBOARD_SIZE]
        ],
    }


def results_view(
    snapshot: ClosedQuestionResultsSnapshot,
    role: LiveRole,
    session_participant_id: int | None,
) -> dict:
    if role == "host":
        return host_results_view(snapshot)
    return participant_results_view(snapshot, session_participant_id)


def active_participant_count(db: Session, session_id: int) -> int:
    return int(
        db.scalar(
            select(func.count(SessionParticipant.session_participant_id)).where(
                SessionParticipant.session_id == session_id,
                SessionParticipant.left_at.is_(None),
            )
        )
        or 0
    )


def build_session_state(
    db: Session,
    session_id: int,
    role: LiveRole,
    session_participant_id: int | None,
    host_connected: bool,
) -> dict:
    """Snapshot sent on every (re)connect; clients render from this alone."""
    session = db.get(LiveSession, session_id)
    if session is None:
        raise LiveCloseError(CloseCode.NOT_FOUND, "session_not_found")

    total_questions = int(
        db.scalar(
            select(func.count(Question.question_id)).where(
                Question.quiz_version_id == session.quiz_version_id
            )
        )
        or 0
    )
    participant_count = active_participant_count(db, session_id)

    current_question = None
    my_answer = None
    last_question = None
    last_results = None
    if session.current_question_order is not None:
        target = db.execute(
            select(SessionQuestion, Question)
            .join(Question, Question.question_id == SessionQuestion.question_id)
            .where(
                SessionQuestion.session_id == session_id,
                Question.question_order == session.current_question_order,
            )
            .options(selectinload(Question.choices))
        ).one_or_none()
        if target is not None:
            session_question, question = target
            if session_question.status == SessionQuestionStatus.OPEN:
                current_question = _opened_event(
                    session_question, question, total_questions
                ).model_dump()
                if session_participant_id is not None:
                    answer = db.execute(
                        select(Response.choice_id, Response.submitted_at).where(
                            Response.session_participant_id
                            == session_participant_id,
                            Response.session_question_id
                            == session_question.session_question_id,
                        )
                    ).one_or_none()
                    if answer is not None:
                        my_answer = {
                            "choice_id": answer.choice_id,
                            "submitted_at": answer.submitted_at,
                        }
            elif session_question.status == SessionQuestionStatus.CLOSED:
                snapshot = get_closed_question_results(
                    db, session_id, session_question.session_question_id
                )
                last_results = results_view(snapshot, role, session_participant_id)
                # Results hold only IDs and counts; the text is needed to draw them.
                last_question = _opened_event(
                    session_question, question, total_questions
                ).model_dump()

    session_block = {
        "session_id": session.session_id,
        "status": session.status,
        "current_question_order": session.current_question_order,
        "total_questions": total_questions,
    }
    if role == "host":
        session_block["join_code"] = session.join_code

    return {
        "type": "session_state",
        "role": role,
        "session": session_block,
        "participant_count": participant_count,
        "host_connected": host_connected,
        "current_question": current_question,
        "my_answer": my_answer,
        "last_question": last_question,
        "last_results": last_results,
    }


def open_question_deadlines(
    db: Session,
    session_id: int | None = None,
) -> list[tuple[int, int, datetime | None]]:
    """(session_id, session_question_id, closes_at) for every OPEN question."""
    query = select(
        SessionQuestion.session_id,
        SessionQuestion.session_question_id,
        SessionQuestion.closes_at,
    ).where(SessionQuestion.status == SessionQuestionStatus.OPEN)
    if session_id is not None:
        query = query.where(SessionQuestion.session_id == session_id)
    return [tuple(row) for row in db.execute(query).all()]
