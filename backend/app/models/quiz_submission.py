from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Computed,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import DATETIME, INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SubmissionStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


def enum_values(enum_class: type[Enum]) -> list[str]:
    return [member.value for member in enum_class]


class QuizSubmission(Base):
    """Audit record for submitting one immutable quiz version to a class.

    ``quiz.class_id`` remains authoritative. This row repeats the class only
    so class-scoped listings and active-submission uniqueness stay indexed.
    """

    __tablename__ = "quiz_submission"
    __table_args__ = (
        UniqueConstraint(
            "class_id",
            "active_version_id",
            name="uq_quiz_submission_active",
        ),
        CheckConstraint(
            "(status = 'PENDING' AND decided_by_id IS NULL AND decided_at IS NULL) "
            "OR (status IN ('APPROVED', 'REJECTED', 'WITHDRAWN') "
            "AND decided_by_id IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_quiz_submission_decision",
        ),
        Index(
            "idx_quiz_submission_class_status_newest",
            "class_id",
            "status",
            "submitted_at",
            "submission_id",
        ),
        Index(
            "idx_quiz_submission_member_newest",
            "class_id",
            "submitted_by_id",
            "submitted_at",
            "submission_id",
        ),
    )

    submission_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    class_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("class.class_id", ondelete="RESTRICT"),
        nullable=False,
    )
    quiz_version_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("quiz_version.quiz_version_id", ondelete="RESTRICT"),
        nullable=False,
    )
    submitted_by_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("account.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        SqlEnum(SubmissionStatus, values_callable=enum_values),
        nullable=False,
        default=SubmissionStatus.PENDING,
        server_default=SubmissionStatus.PENDING.value,
    )
    decided_by_id: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("account.account_id", ondelete="RESTRICT"),
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )
    decided_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    # Private ORM detail used only by the database uniqueness rule. NULLs do
    # not collide, so rejected and withdrawn versions may be submitted again.
    _active_version_id: Mapped[int | None] = mapped_column(
        "active_version_id",
        INTEGER(unsigned=True),
        Computed(
            "CASE WHEN status IN ('PENDING', 'APPROVED') "
            "THEN quiz_version_id ELSE NULL END",
            persisted=True,
        ),
        nullable=True,
    )
