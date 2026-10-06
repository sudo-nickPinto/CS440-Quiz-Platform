from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    CHAR,
    CheckConstraint,
    Enum as SqlEnum,
    ForeignKey,
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


class LiveSession(Base):
    """ORM mapping for a hosted quiz session from migration 0003."""

    __tablename__ = "live_session"

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
    responses: Mapped[list[Response]] = relationship(
        back_populates="session_question", passive_deletes=True
    )


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
