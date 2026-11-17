"""Roster import, join requests that need approval, the email service and
the "+ Add student" suggestions (app/services/class_roster.py)."""

from collections.abc import Iterator
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select

from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import Base
from app.emails import EmailService, MemoryTransport
from app.errors import APIError
from app.main import create_app
from app.models.account import Account, AccountRole
from app.models.classes import (
    Class,
    ClassMembership,
    ClassRole,
    ClassRosterEntry,
    JoinedVia,
    MembershipStatus,
)
from app.services.class_roster import (
    claim_roster_invitations,
    names_match,
    normalize_name,
    parse_roster,
    split_roster_name,
)

# Same columns as the registrar's class list export; the people are made up.
HEADER = "Select,ID,Name,Grade Basis,Units,Program and Plan,Level,Exp. Grad Term"
ROSTER_CSV = "\n".join(
    [
        HEADER,
        ',6100001,"Rivera,Maya",Graded,1,"Liberal Arts and Sciences - Computer Science- BS/Bachelor of Science",Senior,"Spring, 2027"',
        ',6100002,"Chen,Lin Mei",Graded,1,"Liberal Arts and Sciences - Computer Science/Bachelor of Arts",Senior,"Spring, 2027"',
        ',6100003,"Okafor,Tunde",Graded,1,"Liberal Arts and Sciences - Computer Science- BS/Physics",Senior,"Fall, 2026"',
        ',6100004,"Kim,Jae",Graded,1,"Liberal Arts and Sciences - Computer Science- BS",Junior,"Spring, 2028"',
        ',6100005,"Novak,Ivana",Graded,1,"Liberal Arts and Sciences - Computer Science- BS",Senior,"Spring, 2027"',
        "",
    ]
).encode()

PEOPLE = {
    # name: (email, first, last, display, faculty)
    "organizer": ("organizer@gettysburg.edu", "Olive", "Organizer", "Olive Organizer", True),
    "maya": ("riverma01@gettysburg.edu", "Maya", "Rivera", "Maya Rivera", False),
    # Never filled in the profile: only a display name.
    "lin": ("chenli01@gettysburg.edu", None, None, "Lin Chen", False),
    "tunde": ("okaftu01@gettysburg.edu", "Tunde", "Okafor", "Tunde Okafor", False),
    # Two accounts with the same name: the roster can't tell them apart.
    "jae_a": ("kimja01@gettysburg.edu", "Jae", "Kim", "Jae Kim", False),
    "jae_b": ("kimja02@gettysburg.edu", "Jae", "Kim", "Jae Kim", False),
    "outsider": ("doepa01@gettysburg.edu", "Pat", "Doe", "Pat Doe", False),
}


@pytest.fixture
def roster_client() -> Iterator[tuple[TestClient, dict[str, CurrentAccount], int]]:
    app = create_app(
        Settings(
            database_url="sqlite://",
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
            email_backend="memory",
            app_base_url="https://quizburg.example",
        )
    )
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.database.engine)
        with app.state.database.session_factory() as db:
            accounts = {
                name: Account(
                    auth0_sub=f"auth0|{name}",
                    email=email,
                    first_name=first,
                    last_name=last,
                    display_name=display,
                    account_type="ADMINISTRATOR" if faculty else None,
                )
                for name, (email, first, last, display, faculty) in PEOPLE.items()
            }
            db.add_all(accounts.values())
            db.flush()
            class_ = Class(
                name="CS 440 Fall 2026",
                created_by_id=accounts["organizer"].account_id,
                join_code="ABCDEFGH",
            )
            db.add(class_)
            db.flush()
            db.add(
                ClassMembership(
                    class_id=class_.class_id,
                    account_id=accounts["organizer"].account_id,
                    role=ClassRole.ORGANIZER,
                    joined_via=JoinedVia.CREATOR,
                )
            )
            db.commit()
            class_id = class_.class_id
            identities = {
                name: CurrentAccount(
                    model.account_id,
                    AccountRole.ADMIN if PEOPLE[name][4] else AccountRole.USER,
                    True,
                )
                for name, model in accounts.items()
            }
        act_as(client, identities["organizer"])
        yield client, identities, class_id


def act_as(client: TestClient, identity: CurrentAccount) -> None:
    client.app.dependency_overrides[get_active_account] = lambda: identity


def make_student(client: TestClient, class_id: int, identity: CurrentAccount) -> None:
    with client.app.state.database.session_factory() as db:
        db.add(ClassMembership(class_id=class_id, account_id=identity.account_id))
        db.commit()


def outbox(client: TestClient):
    return client.app.state.email.outbox


def membership(client: TestClient, class_id: int, account_id: int):
    with client.app.state.database.session_factory() as db:
        return db.scalar(
            select(ClassMembership).where(
                ClassMembership.class_id == class_id,
                ClassMembership.account_id == account_id,
            )
        )


def upload(client: TestClient, class_id: int, content: bytes, *, dry_run=False):
    return client.post(
        f"/classes/{class_id}/roster/import",
        params={"dry_run": str(dry_run).lower()},
        content=content,
        headers={"Content-Type": "text/csv"},
    )


# -- Reading the file -------------------------------------------------------


def test_split_roster_name_reads_last_comma_first() -> None:
    assert split_roster_name("Chen,Lin Mei") == ("Lin Mei", "Chen")
    assert split_roster_name(" Rivera , Maya ") == ("Maya", "Rivera")
    assert split_roster_name("Maya Rivera") == ("Maya", "Rivera")


def test_normalize_name_ignores_case_accents_and_punctuation() -> None:
    assert normalize_name("  Ngọc-Ánh  O'Neil ") == "ngoc anh o neil"


def test_names_match_first_given_name_or_display_name() -> None:
    lin = Account(email="x", auth0_sub="x", display_name="Lin Chen")
    assert names_match("Lin Mei", "Chen", lin)
    assert not names_match("Mei", "Chen", lin)
    maya = Account(email="y", auth0_sub="y", display_name="M R", first_name="maya", last_name="RIVERA")
    assert names_match("Maya", "Rivera", maya)
    assert not names_match("Maya", "Rivers", maya)


def test_parse_registrar_csv() -> None:
    parsed = parse_roster(ROSTER_CSV)

    assert [(row.student_number, row.first_name, row.last_name) for row in parsed.rows] == [
        ("6100001", "Maya", "Rivera"),
        ("6100002", "Lin Mei", "Chen"),
        ("6100003", "Tunde", "Okafor"),
        ("6100004", "Jae", "Kim"),
        ("6100005", "Ivana", "Novak"),
    ]
    assert all(row.error is None and row.email is None for row in parsed.rows)


def test_parse_registrar_xlsx_with_numeric_ids() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(HEADER.split(","))
    sheet.append([None, 6100001, "Rivera,Maya", "Graded", 1, "CS", "Senior", "Spring, 2027"])
    sheet.append([None, 6100002.0, "Chen,Lin Mei", "Graded", 1, "CS", "Senior", "Spring, 2027"])
    buffer = BytesIO()
    workbook.save(buffer)

    parsed = parse_roster(buffer.getvalue())

    assert [row.student_number for row in parsed.rows] == ["6100001", "6100002"]
    assert parsed.rows[1].first_name == "Lin Mei"


def test_parse_optional_email_column_and_bad_rows() -> None:
    content = (
        "Student ID,Last Name,First Name,Email\n"
        "1,Rivera,Maya,RiverMa01@Gettysburg.edu\n"
        ",Chen,Lin,\n"
        "1,Okafor,Tunde,\n"
        "3,Kim,,\n"
        "4,Doe,Pat,not-an-email\n"
    ).encode()

    rows = parse_roster(content).rows

    assert rows[0].email == "riverma01@gettysburg.edu" and rows[0].error is None
    assert rows[1].error == "No student ID."
    assert rows[2].error == "This student ID is already earlier in the file."
    assert rows[3].error == 'The name should look like "Last,First".'
    assert "not an email" in rows[4].error


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (b"", "roster_file_empty"),
        (b"Name,Units\nRivera,1\n", "roster_columns_missing"),
        ((HEADER + "\n").encode(), "roster_file_empty"),
        (b"PK\x03\x04not really a workbook", "roster_file_unreadable"),
    ],
)
def test_parse_refuses_unusable_files(content, code) -> None:
    with pytest.raises(APIError) as error:
        parse_roster(content)
    assert error.value.code == code


# -- Importing --------------------------------------------------------------


def test_import_invites_matches_and_saves_the_rest(roster_client) -> None:
    client, identities, class_id = roster_client

    response = upload(client, class_id, ROSTER_CSV)

    assert response.status_code == 200
    body = response.json()
    outcomes = {row["student_number"]: row["outcome"] for row in body["rows"]}
    assert outcomes == {
        "6100001": "invited",
        "6100002": "invited",  # matched by display name "Lin Chen"
        "6100003": "invited",
        "6100004": "ambiguous",
        "6100005": "expected",
    }
    assert body["counts"] == {"invited": 3, "ambiguous": 1, "expected": 1}
    assert body["emails_sent"] == 3
    for name in ("maya", "lin", "tunde"):
        stored = membership(client, class_id, identities[name].account_id)
        assert stored.status == MembershipStatus.INVITED
        assert stored.joined_via == JoinedVia.INVITE
    assert membership(client, class_id, identities["jae_a"].account_id) is None

    sent = {message.to: message for message in outbox(client)}
    assert set(sent) == {PEOPLE[name][0] for name in ("maya", "lin", "tunde")}
    invitation = sent[PEOPLE["maya"][0]]
    assert invitation.subject == "You're invited to CS 440 Fall 2026 on QuizBurg"
    assert "https://quizburg.example/app/classes" in invitation.body
    assert "https://quizburg.example/app/join/class/ABCD-EFGH" in invitation.body

    roster = client.get(f"/classes/{class_id}/roster").json()
    assert [entry["last_name"] for entry in roster] == [
        "Chen",
        "Kim",
        "Novak",
        "Okafor",
        "Rivera",
    ]
    assert {entry["last_name"]: entry["membership_status"] for entry in roster}["Novak"] is None


def test_dry_run_saves_and_sends_nothing(roster_client) -> None:
    client, identities, class_id = roster_client

    response = upload(client, class_id, ROSTER_CSV, dry_run=True)

    assert response.status_code == 200
    assert response.json()["dry_run"] is True
    assert response.json()["counts"]["invited"] == 3
    assert response.json()["emails_sent"] == 0
    assert outbox(client) == []
    assert membership(client, class_id, identities["maya"].account_id) is None
    assert client.get(f"/classes/{class_id}/roster").json() == []


def test_importing_again_updates_rows_without_resending(roster_client) -> None:
    client, _, class_id = roster_client
    upload(client, class_id, ROSTER_CSV)
    outbox(client).clear()

    again = upload(client, class_id, ROSTER_CSV).json()

    assert again["counts"] == {"already_invited": 3, "ambiguous": 1, "expected": 1}
    assert outbox(client) == []
    assert len(client.get(f"/classes/{class_id}/roster").json()) == 5


def test_import_approves_pending_request_and_skips_members(roster_client) -> None:
    client, identities, class_id = roster_client
    act_as(client, identities["maya"])
    assert client.post("/classes/join", json={"code": "ABCD-EFGH"}).json()[
        "membership_status"
    ] == "REQUESTED"
    act_as(client, identities["organizer"])
    with client.app.state.database.session_factory() as db:
        db.add(
            ClassMembership(
                class_id=class_id,
                account_id=identities["tunde"].account_id,
                status=MembershipStatus.REMOVED,
            )
        )
        db.commit()

    rows = {
        row["student_number"]: row
        for row in upload(client, class_id, ROSTER_CSV).json()["rows"]
    }

    assert rows["6100001"]["outcome"] == "approved"
    assert membership(client, class_id, identities["maya"].account_id).status == (
        MembershipStatus.ACTIVE
    )
    assert rows["6100003"]["outcome"] == "removed"
    assert membership(client, class_id, identities["tunde"].account_id).status == (
        MembershipStatus.REMOVED
    )
    approved = [m for m in outbox(client) if m.to == PEOPLE["maya"][0]]
    assert approved[0].subject == "You're in CS 440 Fall 2026"


def test_import_with_email_invites_people_without_accounts(roster_client) -> None:
    client, _, class_id = roster_client
    content = b"ID,Name,Email\n7,\"Novak,Ivana\",novaiv01@gettysburg.edu\n"

    body = upload(client, class_id, content).json()

    assert body["rows"][0]["outcome"] == "expected"
    assert [message.to for message in outbox(client)] == ["novaiv01@gettysburg.edu"]
    assert "Create your QuizBurg account" in outbox(client)[0].body

    # When they sign up with that email, the invitation is waiting.
    with client.app.state.database.session_factory() as db:
        new = Account(
            auth0_sub="auth0|ivana",
            email="NovaIv01@gettysburg.edu",
            display_name="novaiv01@gettysburg.edu",
        )
        db.add(new)
        db.commit()
        assert claim_roster_invitations(db, new.account_id, new.email) == 1
        new_id = new.account_id
    assert membership(client, class_id, new_id).status == MembershipStatus.INVITED


def test_only_organizers_import_and_archived_classes_refuse(roster_client) -> None:
    client, identities, class_id = roster_client
    # Outsiders get 404 (the class stays hidden); students get 403.
    act_as(client, identities["maya"])
    assert upload(client, class_id, ROSTER_CSV).status_code == 404
    make_student(client, class_id, identities["maya"])
    assert upload(client, class_id, ROSTER_CSV).status_code == 403
    assert client.get(f"/classes/{class_id}/roster").status_code == 403

    act_as(client, identities["organizer"])
    client.post(f"/classes/{class_id}/archive")
    response = upload(client, class_id, ROSTER_CSV)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "class_archived"


def test_unusable_upload_is_a_clear_error(roster_client) -> None:
    client, _, class_id = roster_client

    response = upload(client, class_id, b"Units,Level\n1,Senior\n")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "roster_columns_missing"


# -- Join requests ----------------------------------------------------------


def join(client: TestClient, identity: CurrentAccount):
    act_as(client, identity)
    response = client.post("/classes/join", json={"code": "abcdefgh"})
    return response


def test_code_join_waits_for_approval(roster_client) -> None:
    client, identities, class_id = roster_client

    first = join(client, identities["outsider"])
    again = join(client, identities["outsider"])
    detail = client.get(f"/classes/{class_id}")

    assert first.status_code == 200
    assert first.json()["membership_status"] == "REQUESTED"
    assert again.status_code == 200
    assert again.json()["membership_status"] == "REQUESTED"
    # Not a member yet: no access to the class.
    assert detail.status_code in {403, 404}

    act_as(client, identities["organizer"])
    pending = client.get(f"/classes/{class_id}/join-requests").json()
    assert [item["email"] for item in pending] == [PEOPLE["outsider"][0]]
    dashboard = client.get(f"/classes/{class_id}/dashboard").json()
    assert dashboard["pending_join_request_count"] == 1


def test_roster_name_match_is_approved_automatically(roster_client) -> None:
    client, identities, class_id = roster_client
    # Ivana has no account at import time.
    upload(client, class_id, ROSTER_CSV)
    with client.app.state.database.session_factory() as db:
        ivana = Account(
            auth0_sub="auth0|ivana",
            email="novaiv01@gettysburg.edu",
            first_name="Ivana",
            last_name="Novak",
            display_name="Ivana Novak",
        )
        db.add(ivana)
        db.commit()
        identity = CurrentAccount(ivana.account_id, AccountRole.USER, True)

    response = join(client, identity)

    assert response.json()["membership_status"] == "ACTIVE"
    with client.app.state.database.session_factory() as db:
        entry = db.scalar(
            select(ClassRosterEntry).where(ClassRosterEntry.student_number == "6100005")
        )
        assert entry.account_id == identity.account_id


def test_approve_reject_and_accept_all_send_emails(roster_client) -> None:
    client, identities, class_id = roster_client
    for name in ("outsider", "jae_a", "jae_b"):
        join(client, identities[name])
    act_as(client, identities["organizer"])

    rejected = client.post(
        f"/classes/{class_id}/join-requests/{identities['outsider'].account_id}/reject"
    )
    approved_all = client.post(f"/classes/{class_id}/join-requests/approve-all")
    missing = client.post(
        f"/classes/{class_id}/join-requests/{identities['outsider'].account_id}/approve"
    )

    assert rejected.json() == {"approved": 0, "rejected": 1}
    assert approved_all.json() == {"approved": 2, "rejected": 0}
    assert missing.status_code == 404
    assert membership(client, class_id, identities["outsider"].account_id).status == (
        MembershipStatus.REJECTED
    )
    for name in ("jae_a", "jae_b"):
        stored = membership(client, class_id, identities[name].account_id)
        assert stored.status == MembershipStatus.ACTIVE
        assert stored.decided_by_id == identities["organizer"].account_id
    subjects = {message.to: message.subject for message in outbox(client)}
    assert subjects[PEOPLE["outsider"][0]] == "Your request to join CS 440 Fall 2026"
    assert subjects[PEOPLE["jae_a"][0]] == "You're in CS 440 Fall 2026"
    assert client.get(f"/classes/{class_id}/join-requests").json() == []

    # A rejected person may ask again.
    assert join(client, identities["outsider"]).json()["membership_status"] == "REQUESTED"


def test_single_approve_and_member_cannot_decide(roster_client) -> None:
    client, identities, class_id = roster_client
    join(client, identities["outsider"])

    make_student(client, class_id, identities["maya"])
    act_as(client, identities["maya"])
    refused = client.post(f"/classes/{class_id}/join-requests/approve-all")
    act_as(client, identities["organizer"])
    approved = client.post(
        f"/classes/{class_id}/join-requests/{identities['outsider'].account_id}/approve"
    )

    assert refused.status_code == 403
    assert approved.json() == {"approved": 1, "rejected": 0}
    members = client.get(f"/classes/{class_id}/members").json()
    assert identities["outsider"].account_id in {item["account_id"] for item in members}


def test_single_invite_sends_the_roster_invitation(roster_client) -> None:
    client, _, class_id = roster_client

    response = client.post(
        f"/classes/{class_id}/invites", json={"email": PEOPLE["outsider"][0]}
    )

    assert response.status_code == 201
    assert [message.to for message in outbox(client)] == [PEOPLE["outsider"][0]]


# -- Suggestions ------------------------------------------------------------


def test_suggestions_search_names_and_emails_across_the_app(roster_client) -> None:
    client, identities, class_id = roster_client
    client.post(f"/classes/{class_id}/invites", json={"email": PEOPLE["maya"][0]})

    by_name = client.get(
        f"/classes/{class_id}/student-suggestions", params={"q": "jae"}
    ).json()
    by_last = client.get(
        f"/classes/{class_id}/student-suggestions", params={"q": "riv"}
    ).json()
    by_email = client.get(
        f"/classes/{class_id}/student-suggestions", params={"q": "okaftu"}
    ).json()
    short = client.get(f"/classes/{class_id}/student-suggestions", params={"q": "j"})
    wildcard = client.get(f"/classes/{class_id}/student-suggestions", params={"q": "%%"})

    assert [item["email"] for item in by_name] == [PEOPLE["jae_a"][0], PEOPLE["jae_b"][0]]
    assert by_last[0]["display_name"] == "Maya Rivera"
    assert by_last[0]["membership_status"] == "INVITED"
    assert by_email[0]["account_id"] == identities["tunde"].account_id
    assert short.json() == []
    assert wildcard.json() == []

    make_student(client, class_id, identities["tunde"])
    act_as(client, identities["tunde"])
    assert (
        client.get(f"/classes/{class_id}/student-suggestions", params={"q": "jae"}).status_code
        == 403
    )


# -- Email service ----------------------------------------------------------


def test_email_service_logs_failures_instead_of_raising() -> None:
    class Broken:
        def send(self, message):
            raise OSError("mail server down")

    service = EmailService(Broken(), "https://quizburg.example/")
    service.send_all([service.join_rejected("a@b.edu", "CS 440")])  # no exception

    memory = EmailService(MemoryTransport(), "https://quizburg.example/")
    message = memory.join_approved("a@b.edu", "CS 440", 7)
    memory.send_all([message])
    assert memory.outbox == [message]
    assert "https://quizburg.example/app/classes/7" in message.body


def test_unknown_email_backend_is_refused() -> None:
    with pytest.raises(ValueError):
        EmailService.from_settings(Settings(email_backend="pigeon"))
    with pytest.raises(ValueError):
        EmailService.from_settings(Settings(email_backend="smtp", smtp_host=""))
