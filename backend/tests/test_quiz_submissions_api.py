from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import CurrentAccount, get_active_account
from app.config import Settings
from app.database import Base
from app.errors import APIError
from app.main import create_app
from app.models import (
    Account,
    AccountRole,
    Class,
    ClassMembership,
    ClassRole,
    JoinedVia,
    MembershipStatus,
    Quiz,
    QuizCollaborator,
    QuizStatus,
    QuizSubmission,
    QuizVersion,
    SubmissionStatus,
)
from app.services.quiz_submissions import require_approved_quiz_version

QUIZ_UPDATE = {
    "title": "Changed title",
    "description": None,
    "expected_revision": 1,
    "questions": [
        {
            "question_text": "Question?",
            "choices": [
                {"choice_text": "Yes", "is_correct": True},
                {"choice_text": "No", "is_correct": False},
            ],
        }
    ],
}


@pytest.fixture
def submissions() -> Iterator[tuple[TestClient, dict, dict, dict]]:
    app = create_app(
        Settings(
            database_url="sqlite://",
            auth0_domain="tenant.example.auth0.com",
            auth0_audience="quiz-api",
        )
    )
    with TestClient(app) as client:
        Base.metadata.create_all(app.state.database.engine)
        with app.state.database.session_factory() as db:
            faculty_names = {"faculty", "unrelated_faculty"}
            accounts = {
                name: Account(
                    auth0_sub=f"auth0|{name}",
                    email=f"{name}@example.edu",
                    display_name=name.replace("_", " ").title(),
                    account_type=("ADMINISTRATOR" if name in faculty_names else None),
                    is_active=True,
                )
                for name in (
                    "faculty",
                    "owner",
                    "collaborator",
                    "classmate",
                    "revoked",
                    "invited",
                    "removed",
                    "outsider",
                    "unrelated_faculty",
                )
            }
            db.add_all(accounts.values())
            db.flush()
            ids = {name: account.account_id for name, account in accounts.items()}

            main = Class(
                name="CS 440",
                created_by_id=ids["faculty"],
                join_code="TASK4001",
            )
            other = Class(
                name="Other",
                created_by_id=ids["owner"],
                join_code="TASK4002",
            )
            db.add_all([main, other])
            db.flush()
            class_ids = {"main": main.class_id, "other": other.class_id}

            memberships = [
                ClassMembership(
                    class_id=main.class_id,
                    account_id=ids["faculty"],
                    role=ClassRole.ORGANIZER,
                    status=MembershipStatus.ACTIVE,
                    joined_via=JoinedVia.CREATOR,
                )
            ]
            for name in ("owner", "collaborator", "classmate", "revoked"):
                memberships.append(
                    ClassMembership(
                        class_id=main.class_id,
                        account_id=ids[name],
                        role=ClassRole.MEMBER,
                        status=MembershipStatus.ACTIVE,
                    )
                )
            memberships.extend(
                [
                    ClassMembership(
                        class_id=main.class_id,
                        account_id=ids["invited"],
                        role=ClassRole.MEMBER,
                        status=MembershipStatus.INVITED,
                    ),
                    ClassMembership(
                        class_id=main.class_id,
                        account_id=ids["removed"],
                        role=ClassRole.MEMBER,
                        status=MembershipStatus.REMOVED,
                    ),
                    ClassMembership(
                        class_id=other.class_id,
                        account_id=ids["owner"],
                        role=ClassRole.ORGANIZER,
                        status=MembershipStatus.ACTIVE,
                    ),
                ]
            )
            db.add_all(memberships)

            published_at = datetime(2026, 11, 3, 12, 0)
            main_quiz = Quiz(
                author_id=ids["owner"],
                class_id=main.class_id,
                status=QuizStatus.PUBLISHED,
            )
            unpublished_quiz = Quiz(
                author_id=ids["owner"],
                class_id=main.class_id,
                status=QuizStatus.DRAFT,
            )
            other_quiz = Quiz(
                author_id=ids["owner"],
                class_id=other.class_id,
                status=QuizStatus.PUBLISHED,
            )
            self_quiz = Quiz(
                author_id=ids["faculty"],
                class_id=main.class_id,
                status=QuizStatus.PUBLISHED,
            )
            db.add_all([main_quiz, unpublished_quiz, other_quiz, self_quiz])
            db.flush()
            versions = {
                "main": QuizVersion(
                    quiz_id=main_quiz.quiz_id,
                    version_number=1,
                    title="Main published quiz",
                    published_at=published_at,
                ),
                "unpublished": QuizVersion(
                    quiz_id=unpublished_quiz.quiz_id,
                    version_number=1,
                    title="Main draft",
                ),
                "other": QuizVersion(
                    quiz_id=other_quiz.quiz_id,
                    version_number=1,
                    title="Other class quiz",
                    published_at=published_at,
                ),
                "self": QuizVersion(
                    quiz_id=self_quiz.quiz_id,
                    version_number=1,
                    title="Faculty quiz",
                    published_at=published_at,
                ),
            }
            db.add_all(versions.values())
            db.flush()
            db.add_all(
                [
                    QuizCollaborator(
                        quiz_id=main_quiz.quiz_id,
                        account_id=ids["collaborator"],
                        shared_by_id=ids["owner"],
                    ),
                    QuizCollaborator(
                        quiz_id=main_quiz.quiz_id,
                        account_id=ids["revoked"],
                        shared_by_id=ids["owner"],
                        revoked_at=published_at,
                        revoked_by_id=ids["owner"],
                    ),
                ]
            )
            db.commit()
            quiz_ids = {
                "main": main_quiz.quiz_id,
                "unpublished": unpublished_quiz.quiz_id,
                "other": other_quiz.quiz_id,
                "self": self_quiz.quiz_id,
            }
            version_ids = {
                name: version.quiz_version_id for name, version in versions.items()
            }

        identities = {
            name: CurrentAccount(
                account_id,
                AccountRole.ADMIN if name in faculty_names else AccountRole.USER,
                True,
            )
            for name, account_id in ids.items()
        }
        actor = {"value": identities["owner"]}
        app.dependency_overrides[get_active_account] = lambda: actor["value"]
        data = {
            "ids": ids,
            "classes": class_ids,
            "quizzes": quiz_ids,
            "versions": version_ids,
        }
        yield client, data, identities, actor
        app.dependency_overrides.clear()


def act_as(actor: dict, identities: dict, name: str) -> None:
    actor["value"] = identities[name]


def post_submission(client: TestClient, class_id: int, version_id: int):
    return client.post(
        f"/classes/{class_id}/quiz-submissions",
        json={"quiz_version_id": version_id},
    )


def decide(client: TestClient, class_id: int, submission_id: int, status: str):
    return client.patch(
        f"/classes/{class_id}/quiz-submissions/{submission_id}",
        json={"status": status},
    )


def assert_error(response, status_code: int, code: str) -> None:
    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code


def test_owner_and_active_collaborator_can_submit_and_lists_are_scoped(
    submissions,
) -> None:
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]
    version_id = data["versions"]["main"]

    owner_submission = post_submission(client, class_id, version_id)
    assert owner_submission.status_code == 201
    assert owner_submission.json()["status"] == "PENDING"
    assert owner_submission.json()["submitted_by_id"] == data["ids"]["owner"]
    assert owner_submission.json()["submitted_at"] is not None

    owner_id = owner_submission.json()["submission_id"]
    assert (
        client.delete(f"/classes/{class_id}/quiz-submissions/{owner_id}").status_code
        == 204
    )

    act_as(actor, identities, "collaborator")
    collaborator_submission = post_submission(client, class_id, version_id)
    assert collaborator_submission.status_code == 201
    own_list = client.get(f"/classes/{class_id}/quiz-submissions").json()
    assert [row["submission_id"] for row in own_list] == [
        collaborator_submission.json()["submission_id"]
    ]

    act_as(actor, identities, "faculty")
    all_rows = client.get(f"/classes/{class_id}/quiz-submissions").json()
    assert [row["submission_id"] for row in all_rows] == [
        collaborator_submission.json()["submission_id"],
        owner_id,
    ]


@pytest.mark.parametrize(
    ("name", "error_code"),
    [
        ("classmate", "quiz_version_not_found"),
        ("revoked", "quiz_version_not_found"),
        ("invited", "class_not_found"),
        ("removed", "class_not_found"),
        ("outsider", "class_not_found"),
        ("unrelated_faculty", "class_not_found"),
    ],
)
def test_ineligible_accounts_cannot_submit(
    submissions, name: str, error_code: str
) -> None:
    client, data, identities, actor = submissions
    act_as(actor, identities, name)

    response = post_submission(
        client, data["classes"]["main"], data["versions"]["main"]
    )

    assert_error(response, 404, error_code)


def test_cross_class_missing_unpublished_and_stale_versions_are_rejected(
    submissions,
) -> None:
    client, data, _, _ = submissions
    class_id = data["classes"]["main"]

    assert_error(
        post_submission(client, class_id, 999999),
        404,
        "quiz_version_not_found",
    )
    assert_error(
        post_submission(client, class_id, data["versions"]["other"]),
        404,
        "quiz_version_not_found",
    )
    assert_error(
        post_submission(client, class_id, data["versions"]["unpublished"]),
        409,
        "quiz_version_not_published",
    )

    with client.app.state.database.session_factory() as db:
        db.add(
            QuizVersion(
                quiz_id=data["quizzes"]["main"],
                version_number=2,
                title="New published version",
                published_at=datetime(2026, 11, 3, 13, 0),
            )
        )
        db.commit()
    assert_error(
        post_submission(client, class_id, data["versions"]["main"]),
        409,
        "quiz_version_stale",
    )


def test_active_duplicate_is_a_conflict_for_pending_and_approved_rows(
    submissions,
) -> None:
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]
    version_id = data["versions"]["main"]
    created = post_submission(client, class_id, version_id)

    assert_error(
        post_submission(client, class_id, version_id),
        409,
        "quiz_submission_conflict",
    )
    act_as(actor, identities, "faculty")
    approved = decide(client, class_id, created.json()["submission_id"], "APPROVED")
    assert approved.status_code == 200

    act_as(actor, identities, "owner")
    assert_error(
        post_submission(client, class_id, version_id),
        409,
        "quiz_submission_conflict",
    )


def test_faculty_organizer_can_approve_reject_and_self_approve(
    submissions,
) -> None:
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]
    owner_submission = post_submission(client, class_id, data["versions"]["main"])

    act_as(actor, identities, "faculty")
    approved = decide(
        client,
        class_id,
        owner_submission.json()["submission_id"],
        "APPROVED",
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["decided_by_id"] == data["ids"]["faculty"]
    assert approved.json()["decided_at"] is not None

    self_submission = post_submission(client, class_id, data["versions"]["self"])
    self_approved = decide(
        client,
        class_id,
        self_submission.json()["submission_id"],
        "APPROVED",
    )
    assert self_approved.status_code == 200
    assert self_approved.json()["submitted_by_id"] == data["ids"]["faculty"]
    assert self_approved.json()["decided_by_id"] == data["ids"]["faculty"]


@pytest.mark.parametrize("lost_access", ["account", "membership", "collaboration"])
def test_approval_rechecks_submitter_eligibility_but_rejection_remains_possible(
    submissions, lost_access: str
) -> None:
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]
    submitter = "collaborator" if lost_access == "collaboration" else "owner"
    act_as(actor, identities, submitter)
    created = post_submission(client, class_id, data["versions"]["main"])

    with client.app.state.database.session_factory() as db:
        if lost_access == "account":
            db.get(Account, data["ids"][submitter]).is_active = False
        elif lost_access == "membership":
            membership = db.scalar(
                select(ClassMembership).where(
                    ClassMembership.class_id == class_id,
                    ClassMembership.account_id == data["ids"][submitter],
                )
            )
            membership.status = MembershipStatus.REMOVED
        else:
            collaborator = db.get(
                QuizCollaborator,
                (data["quizzes"]["main"], data["ids"][submitter]),
            )
            collaborator.revoked_at = datetime.now(UTC).replace(tzinfo=None)
            collaborator.revoked_by_id = data["ids"]["owner"]
        db.commit()

    act_as(actor, identities, "faculty")
    submission_id = created.json()["submission_id"]
    assert_error(
        decide(client, class_id, submission_id, "APPROVED"),
        409,
        "submission_no_longer_eligible",
    )
    rejected = decide(client, class_id, submission_id, "REJECTED")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"


def test_withdrawal_is_soft_audited_and_terminal_transitions_are_protected(
    submissions,
) -> None:
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]
    version_id = data["versions"]["main"]
    created = post_submission(client, class_id, version_id)
    submission_id = created.json()["submission_id"]

    act_as(actor, identities, "faculty")
    assert_error(
        client.delete(f"/classes/{class_id}/quiz-submissions/{submission_id}"),
        403,
        "not_submission_owner",
    )
    act_as(actor, identities, "owner")
    assert (
        client.delete(
            f"/classes/{class_id}/quiz-submissions/{submission_id}"
        ).status_code
        == 204
    )

    with client.app.state.database.session_factory() as db:
        stored = db.get(QuizSubmission, submission_id)
        assert stored is not None
        assert stored.status == SubmissionStatus.WITHDRAWN
        assert stored.decided_by_id == data["ids"]["owner"]
        assert stored.decided_at is not None

    assert_error(
        client.delete(f"/classes/{class_id}/quiz-submissions/{submission_id}"),
        409,
        "invalid_submission_transition",
    )
    replacement = post_submission(client, class_id, version_id)
    assert replacement.status_code == 201

    act_as(actor, identities, "faculty")
    replacement_id = replacement.json()["submission_id"]
    assert decide(client, class_id, replacement_id, "APPROVED").status_code == 200
    assert_error(
        decide(client, class_id, replacement_id, "REJECTED"),
        409,
        "invalid_submission_transition",
    )


def test_submission_visibility_uses_hidden_not_found_responses(submissions) -> None:
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]
    created = post_submission(client, class_id, data["versions"]["main"])
    submission_id = created.json()["submission_id"]

    act_as(actor, identities, "classmate")
    assert client.get(f"/classes/{class_id}/quiz-submissions").json() == []
    assert_error(
        decide(client, class_id, submission_id, "APPROVED"),
        404,
        "submission_not_found",
    )
    assert_error(
        client.delete(f"/classes/{class_id}/quiz-submissions/{submission_id}"),
        404,
        "submission_not_found",
    )

    act_as(actor, identities, "owner")
    assert_error(
        decide(client, class_id, submission_id, "APPROVED"),
        403,
        "not_class_organizer",
    )
    act_as(actor, identities, "unrelated_faculty")
    assert_error(
        client.get(f"/classes/{class_id}/quiz-submissions"),
        404,
        "class_not_found",
    )


def test_archived_class_blocks_submission_approval_and_hostability_but_allows_cleanup(
    submissions,
) -> None:
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]
    main_version_id = data["versions"]["main"]

    approved = post_submission(client, class_id, main_version_id)
    act_as(actor, identities, "faculty")
    assert (
        decide(
            client, class_id, approved.json()["submission_id"], "APPROVED"
        ).status_code
        == 200
    )
    pending_rejection = post_submission(client, class_id, data["versions"]["self"])

    with client.app.state.database.session_factory() as db:
        cleanup_quiz = Quiz(
            author_id=data["ids"]["owner"],
            class_id=class_id,
            status=QuizStatus.PUBLISHED,
        )
        db.add(cleanup_quiz)
        db.flush()
        cleanup_version = QuizVersion(
            quiz_id=cleanup_quiz.quiz_id,
            version_number=1,
            title="Pending cleanup quiz",
            published_at=datetime(2026, 11, 3, 15, 0),
        )
        db.add(cleanup_version)
        db.commit()
        cleanup_version_id = cleanup_version.quiz_version_id

    act_as(actor, identities, "owner")
    pending_withdrawal = post_submission(client, class_id, cleanup_version_id)

    with client.app.state.database.session_factory() as db:
        class_ = db.get(Class, class_id)
        class_.join_code = None
        class_.joining_open = False
        class_.archived_at = datetime(2026, 11, 4, 9, 0)
        db.commit()

    assert_error(
        post_submission(client, class_id, main_version_id),
        409,
        "class_archived",
    )

    act_as(actor, identities, "faculty")
    rejection_id = pending_rejection.json()["submission_id"]
    assert_error(
        decide(client, class_id, rejection_id, "APPROVED"),
        409,
        "class_archived",
    )
    rejected = decide(client, class_id, rejection_id, "REJECTED")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"

    act_as(actor, identities, "owner")
    assert (
        client.delete(
            f"/classes/{class_id}/quiz-submissions/"
            f"{pending_withdrawal.json()['submission_id']}"
        ).status_code
        == 204
    )

    assert_error(
        client.get(f"/classes/{class_id}/approved-quizzes"),
        409,
        "class_archived",
    )
    with client.app.state.database.session_factory() as db:
        with pytest.raises(APIError) as error:
            require_approved_quiz_version(db, class_id, main_version_id)
        assert error.value.code == "class_archived"

    act_as(actor, identities, "faculty")
    statuses = {
        row["status"]
        for row in client.get(f"/classes/{class_id}/quiz-submissions").json()
    }
    assert statuses == {"APPROVED", "REJECTED", "WITHDRAWN"}


def test_approved_list_and_helper_share_current_version_rules(submissions) -> None:
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]
    version_id = data["versions"]["main"]
    created = post_submission(client, class_id, version_id)
    assert client.get(f"/classes/{class_id}/approved-quizzes").json() == []
    with client.app.state.database.session_factory() as db:
        with pytest.raises(APIError) as error:
            require_approved_quiz_version(db, class_id, version_id)
        assert error.value.code == "quiz_version_not_approved"

    act_as(actor, identities, "faculty")
    assert (
        decide(
            client, class_id, created.json()["submission_id"], "APPROVED"
        ).status_code
        == 200
    )
    rejected = post_submission(client, class_id, data["versions"]["self"])
    assert (
        decide(
            client, class_id, rejected.json()["submission_id"], "REJECTED"
        ).status_code
        == 200
    )

    act_as(actor, identities, "classmate")
    approved = client.get(f"/classes/{class_id}/approved-quizzes")
    assert approved.status_code == 200
    assert approved.json()[0] == {
        "submission_id": created.json()["submission_id"],
        "quiz_id": data["quizzes"]["main"],
        "quiz_version_id": version_id,
        "version_number": 1,
        "title": "Main published quiz",
        "author_id": data["ids"]["owner"],
        "approved_at": approved.json()[0]["approved_at"],
        "approved_by_id": data["ids"]["faculty"],
    }
    with client.app.state.database.session_factory() as db:
        assert (
            require_approved_quiz_version(db, class_id, version_id).quiz_version_id
            == version_id
        )
        draft = QuizVersion(
            quiz_id=data["quizzes"]["main"],
            version_number=2,
            title="New draft",
        )
        db.add(draft)
        db.get(Quiz, data["quizzes"]["main"]).status = QuizStatus.DRAFT
        db.commit()

    # A newer draft does not displace the current approved published version.
    assert [
        row["quiz_version_id"]
        for row in client.get(f"/classes/{class_id}/approved-quizzes").json()
    ] == [version_id]

    with client.app.state.database.session_factory() as db:
        draft = db.scalar(
            select(QuizVersion).where(
                QuizVersion.quiz_id == data["quizzes"]["main"],
                QuizVersion.version_number == 2,
            )
        )
        draft.published_at = datetime(2026, 11, 3, 14, 0)
        newer_version_id = draft.quiz_version_id
        db.get(Quiz, data["quizzes"]["main"]).status = QuizStatus.PUBLISHED
        db.commit()

    assert client.get(f"/classes/{class_id}/approved-quizzes").json() == []
    with client.app.state.database.session_factory() as db:
        with pytest.raises(APIError) as error:
            require_approved_quiz_version(db, class_id, version_id)
        assert error.value.code == "quiz_version_not_approved"

    act_as(actor, identities, "owner")
    newer_submission = post_submission(client, class_id, newer_version_id)
    act_as(actor, identities, "faculty")
    assert (
        decide(
            client,
            class_id,
            newer_submission.json()["submission_id"],
            "APPROVED",
        ).status_code
        == 200
    )
    act_as(actor, identities, "classmate")
    assert [
        row["quiz_version_id"]
        for row in client.get(f"/classes/{class_id}/approved-quizzes").json()
    ] == [newer_version_id]

    with client.app.state.database.session_factory() as db:
        db.get(Quiz, data["quizzes"]["main"]).status = QuizStatus.ARCHIVED
        db.commit()
    assert client.get(f"/classes/{class_id}/approved-quizzes").json() == []
    with client.app.state.database.session_factory() as db:
        with pytest.raises(APIError) as error:
            require_approved_quiz_version(db, class_id, newer_version_id)
        assert error.value.code == "quiz_version_not_approved"


def test_approval_grants_no_editing_or_results_permissions(submissions) -> None:
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]
    created = post_submission(client, class_id, data["versions"]["main"])
    act_as(actor, identities, "faculty")
    assert (
        decide(
            client, class_id, created.json()["submission_id"], "APPROVED"
        ).status_code
        == 200
    )

    act_as(actor, identities, "classmate")
    assert client.get(f"/classes/{class_id}/approved-quizzes").status_code == 200
    edit = client.put(
        f"/classes/{class_id}/quizzes/{data['quizzes']['main']}",
        json=QUIZ_UPDATE,
    )
    assert_error(edit, 403, "quiz_edit_denied")
    results = client.get(f"/classes/{class_id}/students/{data['ids']['owner']}/results")
    assert_error(results, 403, "not_class_organizer")


@pytest.mark.parametrize("newer_published", [False, True])
def test_preview_returns_submitted_version_not_latest(submissions, newer_published):
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]
    version_id = data["versions"]["main"]

    created = post_submission(client, class_id, version_id)
    assert created.status_code == 201
    submission_id = created.json()["submission_id"]

    with client.app.state.database.session_factory() as db:
        db.add(
            QuizVersion(
                quiz_id=data["quizzes"]["main"],
                version_number=2,
                title="Different newer content",
                published_at=(
                    datetime(2026, 11, 4, 12, 0) if newer_published else None
                ),
            )
        )
        db.commit()

    act_as(actor, identities, "faculty")

    response = client.get(
        f"/classes/{class_id}/quiz-submissions/" f"{submission_id}/preview"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["version"]["quiz_version_id"] == version_id
    assert body["version"]["title"] == "Main published quiz"
    assert body["version"]["version_number"] == 1
    assert body["can_approve"] is (not newer_published)

    if newer_published:
        assert body["approval_block_reason"]
        rejected = decide(client, class_id, submission_id, "APPROVED")
        assert_error(rejected, 409, "quiz_version_stale")


@pytest.mark.parametrize(
    "name",
    [
        "classmate",
        "collaborator",
        "revoked",
        "invited",
        "removed",
        "outsider",
        "unrelated_faculty",
    ],
)
def test_preview_does_not_expose_another_members_submission(submissions, name):
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]

    created = post_submission(client, class_id, data["versions"]["main"])
    submission_id = created.json()["submission_id"]

    act_as(actor, identities, name)

    response = client.get(
        f"/classes/{class_id}/quiz-submissions/" f"{submission_id}/preview"
    )

    assert response.status_code == 404


def test_original_submitter_can_preview_but_not_approve(submissions):
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]

    created = post_submission(client, class_id, data["versions"]["main"])
    submission_id = created.json()["submission_id"]

    response = client.get(
        f"/classes/{class_id}/quiz-submissions/" f"{submission_id}/preview"
    )

    assert response.status_code == 200
    assert response.json()["can_approve"] is False

    wrong_class = client.get(
        f"/classes/{data['classes']['other']}/quiz-submissions/"
        f"{submission_id}/preview"
    )
    assert wrong_class.status_code == 404


def test_revoked_submitter_loses_preview_access(submissions):
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]

    act_as(actor, identities, "collaborator")
    created = post_submission(client, class_id, data["versions"]["main"])
    assert created.status_code == 201
    submission_id = created.json()["submission_id"]

    with client.app.state.database.session_factory() as db:
        collaborator = db.scalar(
            select(QuizCollaborator).where(
                QuizCollaborator.quiz_id == data["quizzes"]["main"],
                QuizCollaborator.account_id == data["ids"]["collaborator"],
            )
        )
        collaborator.revoked_at = datetime(2026, 11, 5, 12, 0)
        db.commit()

    response = client.get(
        f"/classes/{class_id}/quiz-submissions/" f"{submission_id}/preview"
    )
    assert response.status_code == 404


def test_archived_quiz_preview_remains_read_only(submissions):
    client, data, identities, actor = submissions
    class_id = data["classes"]["main"]

    created = post_submission(client, class_id, data["versions"]["main"])
    submission_id = created.json()["submission_id"]

    with client.app.state.database.session_factory() as db:
        quiz = db.get(Quiz, data["quizzes"]["main"])
        quiz.status = QuizStatus.ARCHIVED
        db.commit()

    act_as(actor, identities, "faculty")

    response = client.get(
        f"/classes/{class_id}/quiz-submissions/" f"{submission_id}/preview"
    )

    assert response.status_code == 200
    assert response.json()["can_approve"] is False
    assert response.json()["approval_block_reason"]
