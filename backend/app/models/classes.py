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
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.mysql import DATETIME, INTEGER
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.account import Account


def enum_values(enum_class: type[Enum]) -> list[str]:
    return [member.value for member in enum_class]


class ClassRole(str, Enum):
    ORGANIZER = "ORGANIZER"
    MEMBER = "MEMBER"


class MembershipStatus(str, Enum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    LEFT = "LEFT"
    REMOVED = "REMOVED"


class JoinedVia(str, Enum):
    CREATOR = "CREATOR"
    CODE = "CODE"
    INVITE = "INVITE"
    ADDED = "ADDED"


class Class(Base):
    """ORM mapping for a class from migration 0006."""

    __tablename__ = "class"
    __table_args__ = (
        UniqueConstraint("join_code", name="uq_class_join_code"),
        CheckConstraint(
            "archived_at IS NULL OR (join_code IS NULL AND joining_open = FALSE)",
            name="ck_class_archived_closed",
        ),
    )

    class_id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("account.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    # Stored without the dash; NULL once the class is archived.
    join_code: Mapped[str | None] = mapped_column(CHAR(8))
    joining_open: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("TRUE")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=func.now(),
        server_onupdate=func.now(),
    )

    memberships: Mapped[list[ClassMembership]] = relationship(
        back_populates="class_"
    )


class ClassMembership(Base):
    """One person's role and status in one class, from migration 0006."""

    __tablename__ = "class_membership"
    __table_args__ = (
        UniqueConstraint("class_id", "account_id", name="uq_class_membership"),
        Index("idx_class_membership_account", "account_id", "status"),
        Index("idx_class_membership_roster", "class_id", "status", "role"),
    )

    membership_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    class_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("class.class_id", ondelete="RESTRICT"),
        nullable=False,
    )
    account_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("account.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    role: Mapped[ClassRole] = mapped_column(
        SqlEnum(ClassRole, values_callable=enum_values),
        nullable=False,
        default=ClassRole.MEMBER,
        server_default=ClassRole.MEMBER.value,
    )
    status: Mapped[MembershipStatus] = mapped_column(
        SqlEnum(MembershipStatus, values_callable=enum_values),
        nullable=False,
        default=MembershipStatus.ACTIVE,
        server_default=MembershipStatus.ACTIVE.value,
    )
    joined_via: Mapped[JoinedVia] = mapped_column(
        SqlEnum(JoinedVia, values_callable=enum_values),
        nullable=False,
        default=JoinedVia.CODE,
        server_default=JoinedVia.CODE.value,
    )
    invited_by_id: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("account.account_id", ondelete="SET NULL"),
    )
    # Who made the most recent removal or role change, and when.
    decided_by_id: Mapped[int | None] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("account.account_id", ondelete="SET NULL"),
    )
    decided_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=3))
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3),
        nullable=False,
        server_default=func.now(),
        server_onupdate=func.now(),
    )

    class_: Mapped[Class] = relationship(back_populates="memberships")
    account: Mapped[Account] = relationship(foreign_keys=[account_id])
