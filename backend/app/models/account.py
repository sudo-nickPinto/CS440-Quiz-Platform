from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, String, func, text
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
    account_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("TRUE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=func.now()
    )
