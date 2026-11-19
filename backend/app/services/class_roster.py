"""Class rosters, join requests and the "Add student" suggestions.

Roster files
    Organizers upload the registrar's class list (CSV, or the .xlsx the
    registrar exports). The file has columns like ``ID``, ``Name`` ("Last,First
    Middle"), ``Grade Basis``, ... and usually no email. Each row is saved as a
    ``class_roster_entry`` and matched to an account by email (when the file
    has an email column) or by first and last name:

    - matched: the account is invited, and gets a roster invitation email;
      a pending join request from them is approved instead;
    - not matched yet: the row waits. When that person later asks to join with
      the class code, their request is approved automatically. If the row had
      an email, the invitation email goes to that address now, and the
      invitation appears as soon as they create an account with it.

Join requests
    Joining with the class code or link no longer makes someone a student
    right away: their membership is REQUESTED until an organizer approves or
    rejects it (Approvals -> Students). Accepted invitations and roster matches
    skip the queue.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.auth import CurrentAccount
from app.emails import EmailService, OutgoingEmail
from app.errors import APIError
from app.models.account import Account
from app.models.classes import (
    Class,
    ClassMembership,
    ClassRole,
    ClassRosterEntry,
    JoinedVia,
    MembershipStatus,
)
from app.services.class_access import leave_class_sessions
from app.schemas.class_roster import (
    JoinRequestDecisionResponse,
    JoinRequestResponse,
    RosterEntryResponse,
    RosterImportResponse,
    RosterImportRow,
    RosterRemoval,
    RosterNameHint,
    RosterRowOutcome,
    StudentSuggestion,
)
from app.services.class_authorization import require_class_organizer

MAX_ROSTER_BYTES = 2 * 1024 * 1024
MAX_ROSTER_ROWS = 2000
# How far down the file the header row may be (exports sometimes add a title).
HEADER_SEARCH_ROWS = 10
SUGGESTION_LIMIT = 8
XLSX_MAGIC = b"PK\x03\x04"

# Header names we understand, after lowercasing and dropping everything that
# isn't a letter or digit ("Student ID" -> "studentid").
ID_HEADERS = {"id", "studentid", "studentnumber", "emplid", "idnumber"}
NAME_HEADERS = {"name", "studentname", "fullname"}
FIRST_HEADERS = {"first", "firstname", "givenname", "preferredfirstname"}
LAST_HEADERS = {"last", "lastname", "surname", "familyname"}
EMAIL_HEADERS = {
    "email",
    "emailaddress",
    "campusemail",
    "preferredemail",
    "studentemail",
}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _now() -> datetime:
    now = datetime.now(UTC).replace(tzinfo=None)
    # Millisecond precision, like the DATETIME(3) columns.
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def _commit(db: Session, code: str, message: str) -> None:
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise APIError(500, code, message) from exc


def _load_class(db: Session, class_id: int, *, lock: bool = False) -> Class:
    statement = select(Class).where(Class.class_id == class_id)
    if lock:
        statement = statement.with_for_update()
    class_ = db.scalar(statement)
    if class_ is None:
        raise APIError(404, "class_not_found", "Class not found.")
    return class_


def _require_organizer(
    db: Session, account: CurrentAccount, class_id: int, *, lock: bool = False
) -> Class:
    # Class first, then membership: the same lock order as the roster routes.
    class_ = _load_class(db, class_id, lock=lock)
    require_class_organizer(db, account, class_id)
    return class_


def _require_open_class(class_: Class) -> None:
    if class_.archived_at is not None:
        raise APIError(409, "class_archived", "This class is archived.")


def _invite_code(class_: Class) -> str | None:
    if class_.archived_at is not None or not class_.joining_open:
        return None
    code = class_.join_code
    return f"{code[:4]}-{code[4:]}" if code else None


# -- Names ----------------------------------------------------------------


def normalize_name(value: str | None) -> str:
    """Lowercase, drop accents and punctuation: "  Ngọc-Anh " -> "ngoc anh"."""
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^0-9a-z]+", " ", plain.casefold()).split())


def split_roster_name(value: str) -> tuple[str, str]:
    """ "Last,First Middle" -> ("First Middle", "Last"). Without a comma the
    last word is the last name."""
    text = " ".join(value.split())
    if "," in text:
        last, first = text.split(",", 1)
        return first.strip(), last.strip()
    words = text.split(" ")
    if len(words) == 1:
        return "", words[0]
    return " ".join(words[:-1]), words[-1]


def _account_names(account: Account) -> list[tuple[str, str]]:
    """(first, last) pairs an account may go by, normalized."""
    if account.first_name and account.last_name:
        return [(normalize_name(account.first_name), normalize_name(account.last_name))]
    words = normalize_name(account.display_name).split()
    if len(words) < 2:
        return []
    # "Mary Ann Smith" may be first "Mary Ann" or last "Ann Smith".
    return [(" ".join(words[:-1]), words[-1]), (words[0], " ".join(words[1:]))]


def names_match(first: str, last: str, account: Account) -> bool:
    """True when the account's name is this roster name.

    The last names must be equal and the account's first name must be the
    roster's given names or their first word ("Sunny" for "Sunny Thi Ngoc").
    """
    roster_last = normalize_name(last)
    roster_first = normalize_name(first)
    if not roster_last or not roster_first:
        return False
    roster_given = roster_first.split()[0]
    for account_first, account_last in _account_names(account):
        if account_last != roster_last or not account_first:
            continue
        if account_first == roster_first or account_first.split()[0] == roster_given:
            return True
    return False


# -- Reading the file -----------------------------------------------------


@dataclass(slots=True)
class ParsedRow:
    row_number: int
    student_number: str | None
    first_name: str | None
    last_name: str | None
    email: str | None
    error: str | None = None


@dataclass(slots=True)
class ParsedRoster:
    rows: list[ParsedRow] = field(default_factory=list)


def _header_key(value) -> str:
    return re.sub(r"[^0-9a-z]", "", str(value or "").casefold())


def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        # Excel stores the student ID 6140064 as 6140064.0.
        return str(int(value))
    return " ".join(str(value).split())


def _read_rows(content: bytes) -> list[list]:
    if content.startswith(XLSX_MAGIC):
        try:
            from openpyxl import load_workbook

            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            try:
                sheet = workbook.worksheets[0]
                rows = []
                for row in sheet.iter_rows(values_only=True):
                    rows.append(list(row))
                    if len(rows) > MAX_ROSTER_ROWS + HEADER_SEARCH_ROWS:
                        break
                return rows
            finally:
                workbook.close()
        except Exception as exc:
            raise APIError(
                422,
                "roster_file_unreadable",
                "That Excel file could not be read. Save it again as .xlsx or CSV.",
            ) from exc

    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - cp1252 decodes almost anything
        raise APIError(422, "roster_file_unreadable", "The roster file could not be read.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)]


def _find_columns(rows: list[list]) -> tuple[int, dict[str, int]]:
    for index, row in enumerate(rows[:HEADER_SEARCH_ROWS]):
        columns: dict[str, int] = {}
        for position, value in enumerate(row):
            key = _header_key(value)
            for kind, names in (
                ("id", ID_HEADERS),
                ("name", NAME_HEADERS),
                ("first", FIRST_HEADERS),
                ("last", LAST_HEADERS),
                ("email", EMAIL_HEADERS),
            ):
                if key in names and kind not in columns:
                    columns[kind] = position
        has_name = "name" in columns or {"first", "last"} <= columns.keys()
        if "id" in columns and has_name:
            return index, columns
    raise APIError(
        422,
        "roster_columns_missing",
        "The roster needs an ID column and a Name column "
        '("Last,First"), or First name and Last name columns.',
    )


def parse_roster(content: bytes) -> ParsedRoster:
    """Read a roster CSV or .xlsx into rows. Raises APIError 422 if unusable."""
    if not content:
        raise APIError(422, "roster_file_empty", "The roster file is empty.")
    if len(content) > MAX_ROSTER_BYTES:
        raise APIError(413, "roster_file_too_large", "The roster file is larger than 2 MB.")

    rows = _read_rows(content)
    header_index, columns = _find_columns(rows)

    def cell(row: list, kind: str) -> str:
        position = columns.get(kind)
        if position is None or position >= len(row):
            return ""
        return _cell_text(row[position])

    parsed = ParsedRoster()
    seen_ids: set[str] = set()
    for offset, row in enumerate(rows[header_index + 1 :], start=header_index + 2):
        if not any(_cell_text(value) for value in row):
            continue
        if len(parsed.rows) >= MAX_ROSTER_ROWS:
            raise APIError(
                413,
                "roster_too_many_rows",
                f"A roster can have at most {MAX_ROSTER_ROWS} students.",
            )

        student_number = cell(row, "id") or None
        if "name" in columns:
            first, last = split_roster_name(cell(row, "name"))
        else:
            first, last = cell(row, "first"), cell(row, "last")
        email = cell(row, "email").lower() or None

        item = ParsedRow(
            row_number=offset,
            student_number=student_number,
            first_name=first or None,
            last_name=last or None,
            email=email,
        )
        if not student_number:
            item.error = "No student ID."
        elif len(student_number) > 20:
            item.error = "The student ID is longer than 20 characters."
        elif not first or not last:
            item.error = 'The name should look like "Last,First".'
        elif len(first) > 100 or len(last) > 100:
            item.error = "The name is longer than 100 characters."
        elif student_number in seen_ids:
            item.error = "This student ID is already earlier in the file."
        elif email and (len(email) > 320 or not EMAIL_PATTERN.match(email)):
            item.error = f"{email} is not an email address."
        if student_number:
            seen_ids.add(student_number)
        parsed.rows.append(item)

    if not parsed.rows:
        raise APIError(422, "roster_file_empty", "The roster has no students in it.")
    return parsed


# -- Importing ------------------------------------------------------------


def _class_memberships(db: Session, class_id: int) -> dict[int, ClassMembership]:
    return {
        membership.account_id: membership
        for membership in db.scalars(
            select(ClassMembership)
            .where(ClassMembership.class_id == class_id)
            .with_for_update()
        )
    }


def _activate(membership: ClassMembership, organizer_id: int, now: datetime) -> None:
    membership.status = MembershipStatus.ACTIVE
    membership.role = ClassRole.MEMBER
    membership.decided_by_id = organizer_id
    membership.decided_at = now


def _add(
    db: Session,
    class_id: int,
    account_id: int,
    membership: ClassMembership | None,
    invited_by_id: int | None,
    now: datetime,
) -> ClassMembership:
    """Make the account a student because of a roster row. The organizer
    chose them, so there is no invitation to accept. ``joined_via`` is
    ROSTER, so a corrected roster email can later tell this access apart
    from an accepted invitation or "+ Add student" (both INVITE)."""
    if membership is None:
        membership = ClassMembership(class_id=class_id, account_id=account_id)
        db.add(membership)
    membership.role = ClassRole.MEMBER
    membership.status = MembershipStatus.ACTIVE
    membership.joined_via = JoinedVia.ROSTER
    membership.invited_by_id = invited_by_id
    membership.decided_by_id = invited_by_id
    membership.decided_at = now
    return membership


def _note_moved_link(row: RosterImportRow, previous: Account | None) -> None:
    """Tell the organizer a corrected email moved this row off an account
    whose membership is kept (they joined some other way)."""
    if previous is None:
        return
    note = (
        f"This row was linked to {previous.display_name} ({previous.email}) "
        "until its email changed. They joined the class another way, so they "
        "keep their access; remove them from their report if that's wrong."
    )
    row.message = f"{row.message} {note}" if row.message else note


def _removable(membership: ClassMembership | None) -> bool:
    """Access a roster row gave: an active student whose membership a roster
    import created (joined_via ROSTER). Accepted invitations, "+ Add
    student", code joins and organizers are kept (review of #173)."""
    return (
        membership is not None
        and membership.status == MembershipStatus.ACTIVE
        and membership.role == ClassRole.MEMBER
        and membership.joined_via == JoinedVia.ROSTER
    )


def import_roster(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    content: bytes,
    email: EmailService,
    *,
    dry_run: bool,
    confirm_removals: bool = False,
) -> tuple[RosterImportResponse, list[OutgoingEmail], list[tuple[int, list[int]]]]:
    """Save the roster and add or approve everyone it matches.

    With ``dry_run`` nothing is saved or sent; the response shows what an
    import would do, so the organizer can check the file first.

    A corrected email moves a row to another account. If the old account
    is in the class only because it was added, it is removed, but only with
    ``confirm_removals`` (the preview lists them first); otherwise the
    import is refused with 409 ``roster_import_needs_confirmation``.

    Returns the response, the emails to send, and for each removed account
    the live sessions it left (so the route can close its sockets).
    """
    class_ = _require_organizer(db, account, class_id, lock=True)
    _require_open_class(class_)
    parsed = parse_roster(content)

    accounts = list(db.scalars(select(Account).where(Account.is_active.is_(True))))
    by_email = {candidate.email.lower(): candidate for candidate in accounts}
    by_id = {candidate.account_id: candidate for candidate in accounts}
    entries = {
        entry.student_number: entry
        for entry in db.scalars(
            select(ClassRosterEntry)
            .where(ClassRosterEntry.class_id == class_id)
            .with_for_update()
        )
    }
    memberships = _class_memberships(db, class_id)
    now = _now()
    code = _invite_code(class_)
    messages: list[OutgoingEmail] = []
    rows: list[RosterImportRow] = []
    # (row, previous account) for every row a corrected email moved.
    moves: list[tuple[RosterImportRow, Account]] = []

    for item in parsed.rows:
        result = RosterImportRow(
            row_number=item.row_number,
            student_number=item.student_number,
            first_name=item.first_name,
            last_name=item.last_name,
            email=item.email,
            outcome=RosterRowOutcome.SKIPPED,
            message=item.error,
        )
        rows.append(result)
        if item.error:
            continue

        entry = entries.get(item.student_number)

        # Only verifiable matches act on an account: the email in this file,
        # or, when the file has no email for the row, a link made earlier (by
        # email). Sign-in emails are verified; names aren't, since anyone can
        # edit theirs, so a name match is only reported to the organizer
        # (NAME_MATCH) and changes nothing.
        linked_id = entry.account_id if entry is not None else None
        match: Account | None = None
        # The account this row was linked to until this file's email moved
        # it elsewhere (a corrected email). Left as it is, but reported.
        moved_from: Account | None = None
        unlink = False
        if item.email:
            match = by_email.get(item.email)
            if linked_id is not None and (
                match is None or match.account_id != linked_id
            ):
                unlink = True
                moved_from = by_id.get(linked_id)
        elif linked_id is not None:
            match = by_id.get(linked_id)
        name_match: Account | None = None
        ambiguous = False
        if match is None:
            named = [
                candidate
                for candidate in accounts
                if names_match(item.first_name, item.last_name, candidate)
            ]
            if len(named) == 1:
                name_match = named[0]
            ambiguous = len(named) > 1

        new_email = item.email is not None and (
            entry is None or (entry.email or "").lower() != item.email
        )
        if entry is None:
            entry = ClassRosterEntry(
                class_id=class_id,
                student_number=item.student_number,
                first_name=item.first_name,
                last_name=item.last_name,
            )
            db.add(entry)
            entries[item.student_number] = entry
        entry.first_name = item.first_name
        entry.last_name = item.last_name
        if item.email:
            entry.email = item.email
        entry.imported_by_id = account.account_id

        if match is None:
            if unlink:
                entry.account_id = None
            if name_match is not None:
                result.outcome = RosterRowOutcome.NAME_MATCH
                result.account_id = name_match.account_id
                result.account_name = name_match.display_name
                result.message = (
                    f"Same name as {name_match.display_name} ({name_match.email}). "
                    "Names can be changed in a profile, so this isn't matched "
                    "automatically. If it's them, approve their join request or "
                    "add them with + Add student."
                )
            elif ambiguous:
                result.outcome = RosterRowOutcome.AMBIGUOUS
                result.message = (
                    "More than one account has this name. Add them with + Add student."
                )
            else:
                result.outcome = RosterRowOutcome.EXPECTED
                result.message = (
                    "No account yet. They're approved automatically when they "
                    "sign up with this email and join."
                    if entry.email
                    else "No account yet. When they join with the class code, "
                    "you'll see their request under Approvals."
                )
            if new_email and entry.account_id is None:
                messages.append(
                    email.roster_invitation(
                        item.email, class_.name, has_account=False, join_code=code
                    )
                )
            if moved_from is not None:
                moves.append((result, moved_from))
            continue

        entry.account_id = match.account_id
        result.account_id = match.account_id
        result.account_name = match.display_name
        membership = memberships.get(match.account_id)
        status = membership.status if membership is not None else None

        if status == MembershipStatus.ACTIVE:
            result.outcome = RosterRowOutcome.ALREADY_IN_CLASS
            result.message = None
        elif status == MembershipStatus.REMOVED:
            result.outcome = RosterRowOutcome.REMOVED
            result.message = (
                "Removed from this class earlier. Use + Add student to invite them again."
            )
        elif status == MembershipStatus.REQUESTED:
            _activate(membership, account.account_id, now)
            result.outcome = RosterRowOutcome.APPROVED
            result.message = None
            messages.append(email.join_approved(match.email, class_.name, class_id))
        else:
            # No membership, an older pending invitation, or they left or
            # were turned down before: the roster puts them in the class.
            memberships[match.account_id] = _add(
                db, class_id, match.account_id, membership, account.account_id, now
            )
            result.outcome = RosterRowOutcome.ADDED
            result.message = None
            messages.append(email.added_to_class(match.email, class_.name, class_id))
        if moved_from is not None:
            moves.append((result, moved_from))

    # Rows a corrected email moved off an account. If nothing else in the
    # roster still points at that account and the row is the only reason it
    # is in the class, its access goes (with the organizer's confirmation).
    still_linked = {
        entry.account_id for entry in entries.values() if entry.account_id is not None
    }
    removals: list[RosterRemoval] = []
    evictions: list[tuple[int, list[int]]] = []
    for result, previous in moves:
        old = memberships.get(previous.account_id)
        if previous.account_id in still_linked or not _removable(old):
            _note_moved_link(result, previous)
            continue
        removals.append(
            RosterRemoval(
                account_id=previous.account_id,
                display_name=previous.display_name,
                email=previous.email,
                student_number=result.student_number,
            )
        )
        note = (
            f"This row was linked to {previous.display_name} ({previous.email}) "
            "until its email changed. "
            + (
                "They will be removed from the class (past results stay)."
                if dry_run
                else "They were removed from the class (past results stay)."
            )
        )
        result.message = f"{result.message} {note}" if result.message else note
        if not dry_run and confirm_removals:
            old.status = MembershipStatus.REMOVED
            old.decided_by_id = account.account_id
            old.decided_at = now
            evictions.append(
                (
                    previous.account_id,
                    leave_class_sessions(db, class_id, previous.account_id, now),
                )
            )

    if removals and not dry_run and not confirm_removals:
        db.rollback()
        raise APIError(
            409,
            "roster_import_needs_confirmation",
            "Corrected emails in this roster would remove "
            + ", ".join(removal.display_name for removal in removals)
            + " from the class. Check the preview, then import again to confirm.",
            details=[removal.model_dump() for removal in removals],
        )

    if dry_run:
        db.rollback()
        messages = []
    else:
        _commit(db, "roster_import_failed", "Could not import the roster.")

    counts: dict[str, int] = {}
    for row in rows:
        counts[row.outcome.value] = counts.get(row.outcome.value, 0) + 1
    return (
        RosterImportResponse(
            dry_run=dry_run,
            rows=rows,
            counts=counts,
            emails_sent=len(messages),
            removals=removals,
        ),
        messages,
        evictions,
    )


def roster_invitation_email(
    db: Session, email: EmailService, class_id: int, address: str
) -> OutgoingEmail:
    """The email for someone invited one at a time with the older invite
    route (``POST /invites``), which still waits for them to accept."""
    class_ = _load_class(db, class_id)
    return email.roster_invitation(
        address, class_.name, has_account=True, join_code=_invite_code(class_)
    )


def added_email(
    db: Session, email: EmailService, class_id: int, address: str
) -> OutgoingEmail:
    """The email for someone added with + Add student."""
    class_ = _load_class(db, class_id)
    return email.added_to_class(address, class_.name, class_id)


def list_roster(
    db: Session, account: CurrentAccount, class_id: int
) -> list[RosterEntryResponse]:
    _require_organizer(db, account, class_id)
    rows = db.execute(
        select(ClassRosterEntry, ClassMembership.status)
        .outerjoin(
            ClassMembership,
            (ClassMembership.class_id == ClassRosterEntry.class_id)
            & (ClassMembership.account_id == ClassRosterEntry.account_id),
        )
        .where(ClassRosterEntry.class_id == class_id)
        .order_by(ClassRosterEntry.last_name, ClassRosterEntry.first_name)
    ).all()
    return [
        RosterEntryResponse(
            entry_id=entry.entry_id,
            student_number=entry.student_number,
            first_name=entry.first_name,
            last_name=entry.last_name,
            email=entry.email,
            account_id=entry.account_id,
            membership_status=status,
            updated_at=entry.updated_at,
        )
        for entry, status in rows
    ]


def _unclaimed_or_own_entries(
    db: Session, class_id: int, account_id: int
) -> list[ClassRosterEntry]:
    return list(
        db.scalars(
            select(ClassRosterEntry).where(
                ClassRosterEntry.class_id == class_id,
                or_(
                    ClassRosterEntry.account_id.is_(None),
                    ClassRosterEntry.account_id == account_id,
                ),
            )
        ).all()
    )


def find_roster_entry(
    db: Session, class_id: int, account: Account
) -> ClassRosterEntry | None:
    """The roster row that is verifiably this account: already linked to it,
    or listing the account's email (sign-in emails are verified before an
    account exists). Joining with the code approves this account straight
    away, so a name match never counts here: names can be edited in the
    profile; organizers see it as a hint instead (list_join_requests)."""
    entries = _unclaimed_or_own_entries(db, class_id, account.account_id)
    address = account.email.lower()
    for entry in entries:
        if entry.account_id == account.account_id:
            return entry
    for entry in entries:
        if entry.email and entry.email.lower() == address:
            return entry
    return None


def claim_roster_invitations(db: Session, account_id: int, email: str) -> int:
    """Put a new account in every class whose roster lists its email.

    Called once, when an account is created (the email is verified by then).
    Returns how many classes they were added to. Commits.
    """
    entries = db.scalars(
        select(ClassRosterEntry)
        .join(Class, Class.class_id == ClassRosterEntry.class_id)
        .where(
            func.lower(ClassRosterEntry.email) == email.strip().lower(),
            ClassRosterEntry.account_id.is_(None),
            Class.archived_at.is_(None),
        )
    ).all()
    now = _now()
    added = 0
    for entry in entries:
        entry.account_id = account_id
        membership = db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == entry.class_id,
                ClassMembership.account_id == account_id,
            )
        )
        if membership is None:
            _add(db, entry.class_id, account_id, None, entry.imported_by_id, now)
            added += 1
    if entries:
        db.commit()
    return added


# -- Join requests --------------------------------------------------------


def list_join_requests(
    db: Session, account: CurrentAccount, class_id: int
) -> list[JoinRequestResponse]:
    _require_organizer(db, account, class_id)
    memberships = db.scalars(
        select(ClassMembership)
        .where(
            ClassMembership.class_id == class_id,
            ClassMembership.status == MembershipStatus.REQUESTED,
        )
        .options(joinedload(ClassMembership.account))
        .order_by(ClassMembership.decided_at, ClassMembership.membership_id)
    ).all()
    unclaimed = list(
        db.scalars(
            select(ClassRosterEntry).where(
                ClassRosterEntry.class_id == class_id,
                ClassRosterEntry.account_id.is_(None),
            )
        )
    )

    def hint(person: Account) -> RosterNameHint | None:
        named = [
            entry
            for entry in unclaimed
            if names_match(entry.first_name, entry.last_name, person)
        ]
        if len(named) != 1:
            return None
        return RosterNameHint(
            student_number=named[0].student_number,
            first_name=named[0].first_name,
            last_name=named[0].last_name,
        )

    return [
        JoinRequestResponse(
            account_id=membership.account_id,
            email=membership.account.email,
            display_name=membership.account.display_name,
            requested_at=membership.decided_at or membership.updated_at,
            roster_name_match=hint(membership.account),
        )
        for membership in memberships
    ]


def count_join_requests(db: Session, class_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(ClassMembership)
        .where(
            ClassMembership.class_id == class_id,
            ClassMembership.status == MembershipStatus.REQUESTED,
        )
    ) or 0


def _requested(
    db: Session, class_id: int, account_id: int | None = None
) -> list[ClassMembership]:
    statement = (
        select(ClassMembership)
        .where(
            ClassMembership.class_id == class_id,
            ClassMembership.status == MembershipStatus.REQUESTED,
        )
        .options(joinedload(ClassMembership.account))
        .with_for_update()
    )
    if account_id is not None:
        statement = statement.where(ClassMembership.account_id == account_id)
    return list(db.scalars(statement).unique())


def decide_join_requests(
    db: Session,
    account: CurrentAccount,
    class_id: int,
    email: EmailService,
    *,
    approve: bool,
    account_id: int | None = None,
) -> tuple[JoinRequestDecisionResponse, list[OutgoingEmail]]:
    """Approve or reject one request (``account_id``) or, when approving
    with no ``account_id``, every pending request ("Accept all")."""
    class_ = _require_organizer(db, account, class_id, lock=True)
    if approve:
        _require_open_class(class_)
    pending = _requested(db, class_id, account_id)
    if account_id is not None and not pending:
        raise APIError(404, "join_request_not_found", "That join request is gone.")

    now = _now()
    messages: list[OutgoingEmail] = []
    for membership in pending:
        if approve:
            _activate(membership, account.account_id, now)
            messages.append(
                email.join_approved(membership.account.email, class_.name, class_id)
            )
        else:
            membership.status = MembershipStatus.REJECTED
            membership.decided_by_id = account.account_id
            membership.decided_at = now
            messages.append(email.join_rejected(membership.account.email, class_.name))

    _commit(db, "join_request_decide_failed", "Could not save the decision.")
    count = len(pending)
    return (
        JoinRequestDecisionResponse(
            approved=count if approve else 0, rejected=0 if approve else count
        ),
        messages,
    )


# -- "Add student" suggestions ---------------------------------------------


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def suggest_students(
    db: Session, account: CurrentAccount, class_id: int, query: str
) -> list[StudentSuggestion]:
    """Accounts anywhere in QuizBurg whose name or email starts with the query.

    Organizer only, because it shows other people's emails. Needs at least two
    characters and returns a handful of results.
    """
    _require_organizer(db, account, class_id)
    needle = " ".join(query.split()).lower()
    if len(needle) < 2:
        return []
    prefix = _escape_like(needle) + "%"
    word = "% " + prefix
    matches = db.scalars(
        select(Account)
        .where(
            Account.is_active.is_(True),
            or_(
                func.lower(Account.email).like(prefix, escape="\\"),
                func.lower(Account.display_name).like(prefix, escape="\\"),
                func.lower(Account.display_name).like(word, escape="\\"),
                func.lower(Account.first_name).like(prefix, escape="\\"),
                func.lower(Account.last_name).like(prefix, escape="\\"),
            ),
        )
        .order_by(Account.display_name, Account.account_id)
        .limit(SUGGESTION_LIMIT)
    ).all()
    statuses = {
        membership.account_id: membership.status
        for membership in db.scalars(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id.in_([match.account_id for match in matches]),
            )
        )
    } if matches else {}
    return [
        StudentSuggestion(
            account_id=match.account_id,
            email=match.email,
            display_name=match.display_name,
            membership_status=statuses.get(match.account_id),
        )
        for match in matches
    ]
