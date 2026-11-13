from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.account import FacultyAccessAction


class FacultyGrantRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Generous limit only stops huge bodies; the account lookup does the rest.
    email: str = Field(min_length=3, max_length=320)


class FacultyMember(BaseModel):
    account_id: int
    display_name: str
    email: str
    is_me: bool
    # Null when faculty status was set up directly in the database (before
    # this page existed), so there is no record of who granted it.
    granted_at: datetime | None
    granted_by_name: str | None


class FacultyAccessHistoryItem(BaseModel):
    event_id: int
    action: FacultyAccessAction
    account_id: int
    account_name: str
    account_email: str
    actor_name: str
    occurred_at: datetime


class FacultyAccessPage(BaseModel):
    faculty: list[FacultyMember]
    # Newest first, most recent HISTORY_LIMIT changes.
    history: list[FacultyAccessHistoryItem]
