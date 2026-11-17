from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from app.models.classes import MembershipStatus


class RosterRowOutcome(str, Enum):
    # Matched an account that has now been invited (an email goes out).
    INVITED = "invited"
    # Matched an account that was waiting on a join request; it is approved.
    APPROVED = "approved"
    # Matched an account that is already a student or organizer.
    ALREADY_IN_CLASS = "already_in_class"
    # Matched an account that already has an invitation waiting.
    ALREADY_INVITED = "already_invited"
    # No account yet. Saved; their join request will be approved automatically.
    EXPECTED = "expected"
    # More than one account has this name. Saved like EXPECTED.
    AMBIGUOUS = "ambiguous"
    # Matched an account an organizer removed; left alone.
    REMOVED = "removed"
    # The row could not be read (no ID, no name, or a repeated ID).
    SKIPPED = "skipped"


class RosterImportRow(BaseModel):
    row_number: int
    student_number: str | None
    first_name: str | None
    last_name: str | None
    email: str | None
    outcome: RosterRowOutcome
    account_id: int | None = None
    account_name: str | None = None
    message: str | None = None


class RosterImportResponse(BaseModel):
    dry_run: bool
    rows: list[RosterImportRow]
    # How many rows ended with each outcome, by outcome value.
    counts: dict[str, int]
    emails_sent: int


class RosterEntryResponse(BaseModel):
    entry_id: int
    student_number: str
    first_name: str
    last_name: str
    email: str | None
    account_id: int | None
    # The matched account's membership in this class, if any.
    membership_status: MembershipStatus | None
    updated_at: datetime


class JoinRequestResponse(BaseModel):
    account_id: int
    email: str
    display_name: str
    requested_at: datetime


class JoinRequestDecisionResponse(BaseModel):
    approved: int = 0
    rejected: int = 0


class StudentSuggestion(BaseModel):
    account_id: int
    email: str
    display_name: str
    # This person's membership in the class, if any (ACTIVE, INVITED, ...).
    membership_status: MembershipStatus | None
