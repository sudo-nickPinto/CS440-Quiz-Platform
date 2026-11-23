"""Guest players for the capstone live demo (temporary, demo branch only).

A guest types a session's join code and a nickname, with no Auth0 account.
Joining creates a throwaway account named after the nickname, makes it an
active member of the session's class, and joins the session the usual way.
From then on the guest is an ordinary class member: the lobby, live play and
results all run through the existing code.

The guest's browser keeps a random token. Only its SHA-256 is stored, in the
account's auth0_sub column ("guest|<hash>"), so no migration is needed and a
real Auth0 sub (which never starts with "guest|") can't collide with it.
"""

import hashlib
import secrets
import unicodedata

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.accounts import COLUMNS
from app.auth import CurrentAccount
from app.errors import APIError
from app.models import (
    Account,
    ClassMembership,
    JoinedVia,
    MembershipStatus,
    QuizVersion,
    SessionParticipant,
)
from app.models.account import effective_role
from app.models.classes import ClassRole
from app.schemas.session import SessionJoinResponse

TOKEN_PREFIX = "guest_"
SUB_PREFIX = "guest|"
NICKNAME_MAX_LENGTH = 30
GUEST_EMAIL_DOMAIN = "guest.quizburg.invalid"


def is_guest_token(token: str | None) -> bool:
    return bool(token) and token.startswith(TOKEN_PREFIX)


def _sub_for(token: str) -> str:
    return SUB_PREFIX + hashlib.sha256(token.encode("utf-8")).hexdigest()


def guest_account_record(db: Session, token: str) -> dict | None:
    """The account row for a guest token, shaped like accounts.get_or_create_account."""
    row = db.execute(
        text(f"SELECT {COLUMNS} FROM account WHERE auth0_sub = :sub"),
        {"sub": _sub_for(token)},
    ).mappings().first()
    return dict(row) if row else None


def guest_current_account(db: Session, token: str) -> CurrentAccount | None:
    record = guest_account_record(db, token)
    if record is None:
        return None
    return CurrentAccount(
        account_id=record["account_id"],
        role=effective_role(record["account_type"]),
        is_active=bool(record["is_active"]),
    )


def clean_nickname(value: str) -> str:
    nickname = " ".join(value.split())
    if not nickname:
        raise APIError(422, "invalid_nickname", "Please enter a nickname.")
    if len(nickname) > NICKNAME_MAX_LENGTH:
        raise APIError(
            422,
            "invalid_nickname",
            f"Nicknames can be at most {NICKNAME_MAX_LENGTH} characters.",
        )
    if any(unicodedata.category(char) in ("Cc", "Cf") for char in nickname):
        raise APIError(422, "invalid_nickname", "Your nickname contains invalid characters.")
    return nickname


def _joinable_session(db: Session, join_code: str):
    # Same lookup as joining with an account, so both see the same sessions.
    from app.services.sessions import _active_session_for_code

    session = _active_session_for_code(db, join_code)
    if session is None or session.class_id is None:
        raise APIError(404, "join_code_not_found", "No active session uses this code.")
    return session


def check_join_code(db: Session, join_code: str) -> dict:
    """Step one of the guest flow: is there a game with this code?"""
    session = _joinable_session(db, join_code)
    title = db.scalar(
        select(QuizVersion.title).where(
            QuizVersion.quiz_version_id == session.quiz_version_id
        )
    )
    return {"session_id": session.session_id, "quiz_title": title}


def _nickname_taken(db: Session, session_id: int, nickname: str) -> bool:
    return (
        db.scalar(
            select(SessionParticipant.session_participant_id)
            .join(Account, Account.account_id == SessionParticipant.account_id)
            .where(
                SessionParticipant.session_id == session_id,
                SessionParticipant.left_at.is_(None),
                func.lower(Account.display_name) == nickname.lower(),
            )
            .limit(1)
        )
        is not None
    )


def join_as_guest(db: Session, join_code: str, nickname: str) -> tuple[str, SessionJoinResponse]:
    """Create a guest for this session and join it. Returns (token, join response)."""
    from app.services.sessions import _join

    nickname = clean_nickname(nickname)
    session = _joinable_session(db, join_code)
    if _nickname_taken(db, session.session_id, nickname):
        raise APIError(
            409,
            "nickname_taken",
            "Someone in this game already uses that nickname. Please pick another.",
        )

    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    sub = _sub_for(token)
    try:
        account = Account(
            auth0_sub=sub,
            email=f"guest-{secrets.token_hex(12)}@{GUEST_EMAIL_DOMAIN}",
            display_name=nickname,
        )
        db.add(account)
        db.flush()
        # No account_identity row: guests are looked up by account.auth0_sub,
        # so the Auth0 sign-in path can never resolve to a guest.
        db.add(
            ClassMembership(
                class_id=session.class_id,
                account_id=account.account_id,
                role=ClassRole.MEMBER,
                status=MembershipStatus.ACTIVE,
                joined_via=JoinedVia.CODE,
            )
        )
        db.commit()
    except (IntegrityError, SQLAlchemyError) as exc:
        db.rollback()
        raise APIError(500, "guest_join_failed", "Could not join the game.") from exc

    current = CurrentAccount(
        account_id=account.account_id,
        role=effective_role(None),
        is_active=True,
    )
    return token, _join(db, current, session)


# ---------------------------------------------------------------------------
# Quick host: start any of your quizzes without going through a class.
#
# The rest of the app expects every session to belong to a class whose
# members may play. Quick host puts the session in the host's own
# "Live demo" class (created on first use), so guests land there and never
# in a real class's roster. Class approval is skipped for these sessions.

DEMO_CLASS_NAME = "Live demo (guests)"


def _hostable_quizzes(db: Session, account_id: int):
    """Quizzes the account wrote or collaborates on, with their newest
    published version, newest first."""
    from app.models import Quiz, QuizCollaborator
    from app.services.hosting import _latest_published_versions

    collaborating = select(QuizCollaborator.quiz_id).where(
        QuizCollaborator.account_id == account_id,
        QuizCollaborator.revoked_at.is_(None),
    )
    quizzes = list(
        db.scalars(
            select(Quiz)
            .where(
                (Quiz.author_id == account_id) | Quiz.quiz_id.in_(collaborating),
                Quiz.deleted_at.is_(None),
            )
            .order_by(Quiz.updated_at.desc(), Quiz.quiz_id.desc())
        )
    )
    versions = _latest_published_versions(db, {quiz.quiz_id for quiz in quizzes})
    return [
        (quiz, versions[quiz.quiz_id][0])
        for quiz in quizzes
        if quiz.quiz_id in versions
    ]


def list_quick_host_quizzes(db: Session, account: CurrentAccount) -> list[dict]:
    from app.models import Class, Question

    rows = _hostable_quizzes(db, account.account_id)
    if not rows:
        return []
    version_ids = [version.quiz_version_id for _, version in rows]
    counts = dict(
        db.execute(
            select(Question.quiz_version_id, func.count(Question.question_id))
            .where(Question.quiz_version_id.in_(version_ids))
            .group_by(Question.quiz_version_id)
        ).all()
    )
    class_names = dict(
        db.execute(
            select(Class.class_id, Class.name).where(
                Class.class_id.in_({quiz.class_id for quiz, _ in rows if quiz.class_id})
            )
        ).all()
    )
    return [
        {
            "quiz_id": quiz.quiz_id,
            "title": version.title,
            "question_count": int(counts.get(version.quiz_version_id, 0)),
            "class_name": class_names.get(quiz.class_id),
        }
        for quiz, version in rows
        if counts.get(version.quiz_version_id)
    ]


def _demo_class_id(db: Session, account_id: int) -> int:
    from app.models import Class

    class_id = db.scalar(
        select(Class.class_id)
        .join(ClassMembership, ClassMembership.class_id == Class.class_id)
        .where(
            Class.created_by_id == account_id,
            Class.name == DEMO_CLASS_NAME,
            Class.deleted_at.is_(None),
            Class.archived_at.is_(None),
            ClassMembership.account_id == account_id,
            ClassMembership.status == MembershipStatus.ACTIVE,
        )
        .order_by(Class.class_id)
        .limit(1)
    )
    if class_id is not None:
        return class_id
    demo = Class(
        name=DEMO_CLASS_NAME,
        created_by_id=account_id,
        join_code=None,
        joining_open=False,
        memberships=[
            ClassMembership(
                account_id=account_id,
                role=ClassRole.ORGANIZER,
                status=MembershipStatus.ACTIVE,
                joined_via=JoinedVia.CREATOR,
            )
        ],
    )
    db.add(demo)
    db.flush()
    return demo.class_id


def quick_host(db: Session, account: CurrentAccount, quiz_id: int):
    from app.models import LiveSession, LiveSessionStatus
    from app.services.sessions import (
        JOIN_CODE_ATTEMPTS,
        _active_session_for_code,
        _generate_join_code,
        _load_session,
        _to_session_response,
    )

    version = next(
        (v for quiz, v in _hostable_quizzes(db, account.account_id) if quiz.quiz_id == quiz_id),
        None,
    )
    if version is None:
        raise APIError(
            404,
            "quiz_not_found",
            "Quiz not found, or it has no published version you can host.",
        )

    for _ in range(JOIN_CODE_ATTEMPTS):
        join_code = _generate_join_code()
        if _active_session_for_code(db, join_code) is not None:
            continue
        try:
            session = LiveSession(
                quiz_version_id=version.quiz_version_id,
                host_id=account.account_id,
                group_id=None,
                class_id=_demo_class_id(db, account.account_id),
                join_code=join_code,
                status=LiveSessionStatus.LOBBY,
            )
            db.add(session)
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        except SQLAlchemyError as exc:
            db.rollback()
            raise APIError(500, "session_creation_failed", "Could not create the session.") from exc
        session_id = session.session_id
        db.expire_all()
        return _to_session_response(db, _load_session(db, session_id))

    raise APIError(503, "join_code_unavailable", "Could not allocate a join code. Please try again.")
