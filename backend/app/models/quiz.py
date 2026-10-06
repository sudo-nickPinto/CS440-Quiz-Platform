from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum as SqlEnum,
    ForeignKey,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME, INTEGER, SMALLINT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class QuizStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class QuizVisibility(str, Enum):
    PRIVATE = "PRIVATE"
    PUBLIC = "PUBLIC"


class QuestionType(str, Enum):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    FILL_IN_BLANK = "FILL_IN_BLANK"


def enum_values(enum_class: type[Enum]) -> list[str]:
    return [member.value for member in enum_class]


class Quiz(Base):
    __tablename__ = "quiz"

    quiz_id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    author_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), ForeignKey("account.account_id"), nullable=False
    )
    status: Mapped[QuizStatus] = mapped_column(
        SqlEnum(QuizStatus, values_callable=enum_values),
        nullable=False,
        default=QuizStatus.PUBLISHED,
        server_default=QuizStatus.DRAFT.value,
    )
    visibility: Mapped[QuizVisibility] = mapped_column(
        SqlEnum(QuizVisibility, values_callable=enum_values),
        nullable=False,
        default=QuizVisibility.PUBLIC,
        server_default=QuizVisibility.PRIVATE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=func.now(),
        server_onupdate=func.now(),
    )

    versions: Mapped[list[QuizVersion]] = relationship(
        back_populates="quiz",
        cascade="all, delete-orphan",
        order_by="QuizVersion.version_number",
        passive_deletes=True,
    )


class QuizVersion(Base):
    __tablename__ = "quiz_version"
    __table_args__ = (
        UniqueConstraint("quiz_id", "version_number", name="uq_quiz_version_number"),
        CheckConstraint("version_number >= 1", name="ck_quiz_version_number"),
    )

    quiz_version_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    quiz_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("quiz.quiz_id", ondelete="CASCADE"),
        nullable=False,
    )
    version_number: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))

    quiz: Mapped[Quiz] = relationship(back_populates="versions")
    questions: Mapped[list[Question]] = relationship(
        back_populates="quiz_version",
        cascade="all, delete-orphan",
        order_by="Question.question_order",
        passive_deletes=True,
    )


class Question(Base):
    __tablename__ = "question"
    __table_args__ = (
        UniqueConstraint(
            "quiz_version_id", "question_order", name="uq_question_order"
        ),
        CheckConstraint("question_order >= 1", name="ck_question_order"),
        CheckConstraint("time_limit_seconds > 0", name="ck_question_time_limit"),
    )

    question_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    quiz_version_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("quiz_version.quiz_version_id", ondelete="CASCADE"),
        nullable=False,
    )
    question_order: Mapped[int] = mapped_column(SMALLINT(unsigned=True), nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(
        SqlEnum(QuestionType, values_callable=enum_values),
        nullable=False,
        default=QuestionType.MULTIPLE_CHOICE,
        server_default=QuestionType.MULTIPLE_CHOICE.value,
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    time_limit_seconds: Mapped[int] = mapped_column(
        SMALLINT(unsigned=True), nullable=False, default=20, server_default="20"
    )
    base_points: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), nullable=False, default=1000, server_default="1000"
    )
    locked_by_id: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True), ForeignKey("account.account_id", ondelete="SET NULL")
    )
    locked_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=func.now(),
        server_onupdate=func.now(),
    )

    quiz_version: Mapped[QuizVersion] = relationship(back_populates="questions")
    choices: Mapped[list[AnswerChoice]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="AnswerChoice.choice_order",
        passive_deletes=True,
    )


class AnswerChoice(Base):
    __tablename__ = "answer_choice"
    __table_args__ = (
        UniqueConstraint("question_id", "choice_order", name="uq_answer_choice_order"),
        CheckConstraint("choice_order >= 1", name="ck_answer_choice_order"),
    )

    choice_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    question_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("question.question_id", ondelete="CASCADE"),
        nullable=False,
    )
    # The migration owns the MySQL TINYINT UNSIGNED storage detail. Using the
    # portable SQLAlchemy type keeps isolated SQLite API tests representative.
    choice_order: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    choice_text: Mapped[str] = mapped_column(String(500), nullable=False)
    is_correct: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("FALSE")
    )

    question: Mapped[Question] = relationship(back_populates="choices")
