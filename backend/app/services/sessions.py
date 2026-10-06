import secrets

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    Account,
    LiveSession,
    LiveSessionStatus,
    Quiz,
    QuizStatus,
    QuizVersion,
    SessionParticipant,
)
from app.schemas.session import (
    SessionJoinResponse,
    SessionParticipantResponse,
    SessionResponse,
)

JOIN_CODE_ALPHABET = "0123456789"
JOIN_CODE_LENGTH = 6
JOIN_CODE_ATTEMPTS = 10
JOINABLE_STATUSES = (LiveSessionStatus.LOBBY, LiveSessionStatus.ACTIVE)


def _generate_join_code() -> str:
    return "".join(
        secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH)
    )


def _load_session(db: Session, session_id: int) -> LiveSession:
    session = db.get(LiveSession, session_id)
    if session is None:
        raise APIError(404, "session_not_found", "Session not found.")
    return session


def _active_session_for_code(db: Session, join_code: str) -> LiveSession | None:
    return db.scalar(
        select(LiveSession)
        .where(
            LiveSession.join_code == join_code,
            LiveSession.status.in_(JOINABLE_STATUSES),
        )
        .order_by(LiveSession.session_id.desc())
    )


def _to_session_response(db: Session, session: LiveSession) -> SessionResponse:
    version = db.get(QuizVersion, session.quiz_version_id)
    if version is None:
        raise APIError(
            500,
            "invalid_session",
            "The session does not reference an available quiz version.",
        )
    return SessionResponse(
        session_id=session.session_id,
        quiz_id=version.quiz_id,
        quiz_version_id=session.quiz_version_id,
        quiz_title=version.title,
        host_id=session.host_id,
        join_code=session.join_code,
        status=session.status,
        current_question_order=session.current_question_order,
        created_at=session.created_at,
        started_at=session.started_at,
        ended_at=session.ended_at,
    )


def _participant_response(
    db: Session,
    participant: SessionParticipant,
) -> SessionParticipantResponse:
    display_name = db.scalar(
        select(Account.display_name).where(Account.account_id == participant.account_id)
    )
    if display_name is None:
        raise APIError(
            500,
            "invalid_participant",
            "The participant does not reference an available account.",
        )
    return SessionParticipantResponse(
        session_participant_id=participant.session_participant_id,
        account_id=participant.account_id,
        display_name=display_name,
        joined_at=participant.joined_at,
    )


def create_session(
    db: Session,
    account: CurrentAccount,
    quiz_id: int,
) -> SessionResponse:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise APIError(404, "quiz_not_found", "Quiz not found.")
    if quiz.author_id != account.account_id:
        raise APIError(
            403,
            "session_host_denied",
            "Only the quiz creator can host this quiz.",
        )
    if quiz.status != QuizStatus.PUBLISHED:
        raise APIError(409, "quiz_not_hostable", "Only a published quiz can be hosted.")

    version = db.scalar(
        select(QuizVersion).where(
            QuizVersion.quiz_id == quiz_id,
            QuizVersion.version_number == 1,
            QuizVersion.published_at.is_not(None),
        )
    )
    if version is None:
        raise APIError(
            409,
            "quiz_not_hostable",
            "The quiz does not have a saved MVP version.",
        )

    for _ in range(JOIN_CODE_ATTEMPTS):
        join_code = _generate_join_code()
        if _active_session_for_code(db, join_code) is not None:
            continue
        session = LiveSession(
            quiz_version_id=version.quiz_version_id,
            host_id=account.account_id,
            group_id=None,
            join_code=join_code,
            status=LiveSessionStatus.LOBBY,
        )
        db.add(session)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if _active_session_for_code(db, join_code) is not None:
                continue
            raise APIError(
                500,
                "session_creation_failed",
                "Could not create the session.",
            ) from exc
        except SQLAlchemyError as exc:
            db.rollback()
            raise APIError(
                500,
                "session_creation_failed",
                "Could not create the session.",
            ) from exc

        session_id = session.session_id
        db.expire_all()
        return _to_session_response(db, _load_session(db, session_id))

    raise APIError(
        503,
        "join_code_unavailable",
        "Could not allocate a join code. Please try again.",
    )


def join_session(
    db: Session,
    account: CurrentAccount,
    join_code: str,
) -> SessionJoinResponse:
    session = _active_session_for_code(db, join_code)
    if session is None:
        raise APIError(404, "join_code_not_found", "No active session uses this code.")
    if session.host_id == account.account_id:
        raise APIError(
            409,
            "host_cannot_join",
            "The host cannot join their own session as a participant.",
        )

    existing = db.scalar(
        select(SessionParticipant).where(
            SessionParticipant.session_id == session.session_id,
            SessionParticipant.account_id == account.account_id,
        )
    )
    if existing is not None:
        raise APIError(
            409,
            "session_already_joined",
            "This account has already joined the session.",
        )

    participant = SessionParticipant(
        session_id=session.session_id,
        account_id=account.account_id,
    )
    db.add(participant)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        duplicate = db.scalar(
            select(SessionParticipant.session_participant_id).where(
                SessionParticipant.session_id == session.session_id,
                SessionParticipant.account_id == account.account_id,
            )
        )
        if duplicate is not None:
            raise APIError(
                409,
                "session_already_joined",
                "This account has already joined the session.",
            ) from exc
        raise APIError(
            500,
            "session_join_failed",
            "Could not join the session.",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(
            500,
            "session_join_failed",
            "Could not join the session.",
        ) from exc

    participant_id = participant.session_participant_id
    session_id = session.session_id
    db.expire_all()
    refreshed_session = _load_session(db, session_id)
    refreshed_participant = db.get(SessionParticipant, participant_id)
    if refreshed_participant is None:
        raise APIError(500, "session_join_failed", "Could not load the participant.")
    return SessionJoinResponse(
        session=_to_session_response(db, refreshed_session),
        participant=_participant_response(db, refreshed_participant),
    )


def get_session(
    db: Session,
    account: CurrentAccount,
    session_id: int,
) -> SessionResponse:
    session = _load_session(db, session_id)
    permitted = session.host_id == account.account_id or account.is_admin
    if not permitted:
        permitted = db.scalar(
            select(SessionParticipant.session_participant_id).where(
                SessionParticipant.session_id == session_id,
                SessionParticipant.account_id == account.account_id,
                SessionParticipant.left_at.is_(None),
            )
        ) is not None
    if not permitted:
        raise APIError(
            403,
            "session_access_denied",
            "You cannot access this session.",
        )
    return _to_session_response(db, session)


def list_session_participants(
    db: Session,
    account: CurrentAccount,
    session_id: int,
) -> list[SessionParticipantResponse]:
    session = _load_session(db, session_id)
    if session.host_id != account.account_id and not account.is_admin:
        raise APIError(
            403,
            "session_access_denied",
            "Only the host or an Admin can view the lobby participants.",
        )

    participants = db.scalars(
        select(SessionParticipant)
        .where(
            SessionParticipant.session_id == session_id,
            SessionParticipant.left_at.is_(None),
        )
        .order_by(
            SessionParticipant.joined_at,
            SessionParticipant.session_participant_id,
        )
    ).all()
    return [_participant_response(db, participant) for participant in participants]
