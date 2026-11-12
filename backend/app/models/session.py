from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    CHAR,
    CheckConstraint,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    JSON,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import DATETIME, INTEGER, SMALLINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.quiz import AnswerChoice, Question


def enum_values(enum_class: type[Enum]) -> list[str]:
    return [member.value for member in enum_class]


class LiveSessionStatus(str, Enum):
    LOBBY = "LOBBY"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class SessionQuestionStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class SessionCorrectionMode(str, Enum):
    REPLACE = "REPLACE"
    ADD = "ADD"


class LiveSession(Base):
    """ORM mapping for a hosted quiz session from migration 0003."""

    __tablename__ = "live_session"
    __table_args__ = (
        CheckConstraint(
            "score_revision >= 0", name="ck_live_session_score_revision"
        ),
    )

    session_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    quiz_version_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("quiz_version.quiz_version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    host_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("account.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Migration 0005 makes the course group optional for the one-class MVP. The
    # relationship stays out of this feature until class management is in scope.
    group_id: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True), nullable=True
    )
    # Migration 0007: the class the session belongs to. Every new session has
    # one. NULL only on old pre-V3 sessions, which are read-only history.
    class_id: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("class.class_id", ondelete="RESTRICT"),
        nullable=True,
    )
    join_code: Mapped[str] = mapped_column(CHAR(6), nullable=False)
    status: Mapped[LiveSessionStatus] = mapped_column(
        SqlEnum(LiveSessionStatus, values_callable=enum_values),
        nullable=False,
        default=LiveSessionStatus.LOBBY,
        server_default=LiveSessionStatus.LOBBY.value,
    )
    current_question_order: Mapped[int | None] = mapped_column(
        SMALLINT(unsigned=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    ended_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    score_revision: Mapped[int] = mapped_column(
        SMALLINT(unsigned=True), nullable=False, default=0, server_default="0"
    )
    rescored_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    rescored_by_id: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("account.account_id", ondelete="RESTRICT"),
    )

    participants: Mapped[list[SessionParticipant]] = relationship(
        back_populates="session", passive_deletes=True
    )
    questions: Mapped[list[SessionQuestion]] = relationship(
        back_populates="session", passive_deletes=True
    )


class SessionParticipant(Base):
    """One account that joined a live session."""

    __tablename__ = "session_participant"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "account_id", name="uq_session_participant"
        ),
    )

    session_participant_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    session_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("live_session.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("account.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )
    left_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))

    session: Mapped[LiveSession] = relationship(back_populates="participants")
    responses: Mapped[list[Response]] = relationship(
        back_populates="participant", passive_deletes=True
    )


class SessionQuestion(Base):
    """One question as it is played, including the server deadline."""

    __tablename__ = "session_question"
    __table_args__ = (
        UniqueConstraint("session_id", "question_id", name="uq_session_question"),
    )

    session_question_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    session_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("live_session.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    question_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("question.question_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[SessionQuestionStatus] = mapped_column(
        SqlEnum(SessionQuestionStatus, values_callable=enum_values),
        nullable=False,
        default=SessionQuestionStatus.PENDING,
        server_default=SessionQuestionStatus.PENDING.value,
    )
    opened_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    closes_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    closed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))

    session: Mapped[LiveSession] = relationship(back_populates="questions")
    question: Mapped[Question] = relationship()
    corrected_choices: Mapped[list[SessionQuestionCorrectChoice]] = relationship(
        back_populates="session_question", passive_deletes=True
    )
    responses: Mapped[list[Response]] = relationship(
        back_populates="session_question", passive_deletes=True
    )


class SessionQuestionCorrectChoice(Base):
    """One accepted choice in a completed session's corrected answer set."""

    __tablename__ = "session_question_correct_choice"

    session_question_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("session_question.session_question_id", ondelete="CASCADE"),
        primary_key=True,
    )
    choice_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("answer_choice.choice_id", ondelete="RESTRICT"),
        primary_key=True,
    )

    session_question: Mapped[SessionQuestion] = relationship(
        back_populates="corrected_choices"
    )
    choice: Mapped[AnswerChoice] = relationship()


class Response(Base):
    """One server-evaluated participant response to a played question."""

    __tablename__ = "response"
    __table_args__ = (
        UniqueConstraint(
            "session_participant_id",
            "session_question_id",
            name="uq_response_once_per_question",
        ),
        CheckConstraint(
            "(choice_id IS NULL) <> (text_answer IS NULL)",
            name="ck_response_answer",
        ),
        CheckConstraint(
            "is_correct OR points_awarded = 0", name="ck_response_points"
        ),
    )

    response_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    session_participant_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey(
            "session_participant.session_participant_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    session_question_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("session_question.session_question_id", ondelete="CASCADE"),
        nullable=False,
    )
    choice_id: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("answer_choice.choice_id", ondelete="RESTRICT"),
    )
    text_answer: Mapped[str | None] = mapped_column(String(255))
    submitted_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )
    response_time_ms: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), nullable=False
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    points_awarded: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), nullable=False, default=0, server_default="0"
    )

    participant: Mapped[SessionParticipant] = relationship(
        back_populates="responses"
    )
    session_question: Mapped[SessionQuestion] = relationship(
        back_populates="responses"
    )
    choice: Mapped[AnswerChoice | None] = relationship()


class Result(Base):
    """One participant's final standing, written once when the session ends."""

    __tablename__ = "result"
    __table_args__ = (
        UniqueConstraint("session_participant_id", name="uq_result_participant"),
        CheckConstraint("final_rank >= 1", name="ck_result_rank"),
    )

    result_id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    session_participant_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey(
            "session_participant.session_participant_id", ondelete="CASCADE"
        ),
        nullable=False,
    )
    total_score: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), nullable=False, default=0, server_default="0"
    )
    correct_count: Mapped[int] = mapped_column(
        SMALLINT(unsigned=True), nullable=False, default=0, server_default="0"
    )
    final_rank: Mapped[int] = mapped_column(SMALLINT(unsigned=True), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )


class SessionAnswerCorrection(Base):
    """Append-only audit record for one completed-session answer correction."""

    __tablename__ = "session_answer_correction"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "score_revision",
            name="uq_session_answer_correction_revision",
        ),
        CheckConstraint(
            "score_revision >= 1",
            name="ck_session_answer_correction_revision",
        ),
        Index(
            "idx_session_answer_correction_question",
            "session_question_id",
            "corrected_at",
        ),
    )

    correction_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    session_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("live_session.session_id", ondelete="CASCADE"),
        nullable=False,
    )
    session_question_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("session_question.session_question_id", ondelete="CASCADE"),
        nullable=False,
    )
    selected_choice_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("answer_choice.choice_id", ondelete="RESTRICT"),
        nullable=False,
    )
    correction_mode: Mapped[SessionCorrectionMode] = mapped_column(
        SqlEnum(SessionCorrectionMode, values_callable=enum_values), nullable=False
    )
    previous_correct_choice_ids: Mapped[list[int]] = mapped_column(
        JSON, nullable=False
    )
    corrected_choice_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    corrected_by_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("account.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    score_revision: Mapped[int] = mapped_column(
        SMALLINT(unsigned=True), nullable=False
    )
    corrected_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )
