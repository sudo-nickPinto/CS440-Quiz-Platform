from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Enum as SqlEnum, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.mysql import DATETIME, INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccountRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"


def effective_role(account_type: str | None) -> AccountRole:
    """Translate persisted account metadata into the two MVP roles."""
    return AccountRole.ADMIN if account_type == "ADMINISTRATOR" else AccountRole.USER


class Account(Base):
    """Persisted account data used to derive an MVP User or Admin."""

    __tablename__ = "account"

    account_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    auth0_sub: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # NULL until the person fills in the profile setup screen (migration 0011).
    first_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # A preset such as "owl.sky" from app/avatars.py; NULL shows initials.
    avatar_key: Mapped[str | None] = mapped_column(String(32), nullable=True)
    account_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("TRUE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )


# account.account_type value that makes an account faculty (see effective_role).
FACULTY_ACCOUNT_TYPE = "ADMINISTRATOR"


class FacultyAccessAction(str, Enum):
    GRANTED = "GRANTED"
    REVOKED = "REVOKED"


class FacultyAccessEvent(Base):
    """Append-only history of faculty status changed in the app (0014)."""

    __tablename__ = "faculty_access_event"
    __table_args__ = (
        Index(
            "idx_faculty_access_event_account",
            "account_id",
            "occurred_at",
            "event_id",
        ),
        Index("idx_faculty_access_event_time", "occurred_at", "event_id"),
    )

    event_id: Mapped[int] = mapped_column(INTEGER(unsigned=True), primary_key=True)
    account_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("account.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    action: Mapped[FacultyAccessAction] = mapped_column(
        SqlEnum(
            FacultyAccessAction,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=False,
    )
    actor_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True),
        ForeignKey("account.account_id", ondelete="RESTRICT"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )
