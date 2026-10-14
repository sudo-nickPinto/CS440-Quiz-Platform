from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, Enum as SqlEnum, String, func, text
from sqlalchemy.dialects.mysql import DATETIME, INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccountRole(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class AccountStatus(str, Enum):
    """PENDING: signed up, waiting for an Admin. ACTIVE: can use the app.
    DISABLED: turned off on purpose; the approval endpoints never touch it."""

    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


def effective_role(account_type: str | None) -> AccountRole:
    """Translate persisted account metadata into the two MVP roles."""
    return AccountRole.ADMIN if account_type == "ADMINISTRATOR" else AccountRole.USER


def _enum_values(enum_class: type[Enum]) -> list[str]:
    return [member.value for member in enum_class]


class Account(Base):
    """Persisted account data used to derive an MVP User or Admin."""

    __tablename__ = "account"
    # is_active is kept for existing readers; it is always status = 'ACTIVE'.
    __table_args__ = (
        CheckConstraint(
            "is_active = (status = 'ACTIVE')", name="chk_account_status_active"
        ),
    )

    account_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    auth0_sub: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[AccountStatus] = mapped_column(
        SqlEnum(AccountStatus, values_callable=_enum_values),
        nullable=False,
        default=AccountStatus.ACTIVE,
        server_default=AccountStatus.ACTIVE.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("TRUE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )
