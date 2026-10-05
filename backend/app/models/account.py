from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Enum as SqlEnum, String, text
from sqlalchemy.dialects.mysql import DATETIME, INTEGER
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccountType(str, Enum):
    STUDENT = "STUDENT"
    PROFESSOR = "PROFESSOR"
    ADMINISTRATOR = "ADMINISTRATOR"


class Account(Base):
    """Database mapping for the account table created by migration 0001."""

    __tablename__ = "account"

    account_id: Mapped[int] = mapped_column(
        INTEGER(unsigned=True), primary_key=True
    )
    auth0_sub: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[AccountType | None] = mapped_column(
        SqlEnum(AccountType, values_callable=lambda members: [m.value for m in members])
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("TRUE")
    )
    created_at: Mapped[datetime] = mapped_column(
        DATETIME(fsp=3), nullable=False, server_default=text("CURRENT_TIMESTAMP(3)")
    )
