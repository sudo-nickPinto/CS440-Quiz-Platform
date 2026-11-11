# V3 Task 4: Class Quiz Submission and Approval

**Status:** Implemented and merged in [PR #83](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/83)

**Migration:** `0010_quiz_submission`

**Scope:** Backend approval workflow; frontend integration belongs to later tasks

## Overview

Task 4 adds an approval gate between publishing a quiz and hosting it in a
class. Publishing creates a fixed quiz version, but does not automatically make
it available for live sessions. The quiz owner or an active collaborator
submits that version to the class, and an active faculty organizer approves or
rejects it.

```text
Create quiz
    ↓
Publish version
    ↓
Submit to class
    ↓
PENDING
    ├── APPROVED → Available for hosting
    ├── REJECTED
    └── WITHDRAWN
```

## Why Approval Is Required

The approval workflow gives class organizers control over which quizzes may be
used with students. Approval applies to an exact version so completed sessions
can always be connected to the original questions, choices, answers, time
limits, and point values.

Changing an approved version in place would make previous sessions and results
unreliable.

## Published Versions and Corrections

An immutable version cannot be edited after publication. The quiz itself may
still be updated by creating a new version.

For example:

1. Version 1 is published and submitted.
2. The organizer finds a typo and rejects it.
3. The owner edits the quiz, creating version 2 as a draft.
4. The owner fixes and publishes version 2.
5. Version 2 is submitted for a new review.
6. Version 1 remains unchanged in the audit history.

```text
Quiz
├── Version 1 — Published — Rejected
└── Version 2 — Published — Approved
```

Task 4 records the decision status but does not currently store organizer
feedback or rejection comments.

## Stale Versions

A version becomes stale when a newer version of the same quiz is published.

```text
Version 1 — Published and approved
Version 2 — Draft
```

Version 1 remains hostable because version 2 is unfinished. After version 2 is
published:

```text
Version 1 — Approved but stale
Version 2 — Published but awaiting approval
```

Version 1 is excluded from hosting, while version 2 must be submitted and
approved separately. The old approval remains in the audit history.

## User Workflow

1. An active class member creates and publishes a quiz.
2. The owner or active collaborator submits the published version.
3. The submission enters the class-level `PENDING` queue.
4. Any active faculty organizer of that class may review it.
5. The organizer approves or rejects the submission.
6. Approved, current versions appear in the class's hostable quiz list.
7. Task 5 uses that list when creating live sessions.

Submitters do not select a specific organizer. Task 4 does not send email,
WebSocket, or in-app notifications. A future dashboard can retrieve the pending
queue and display it to class organizers.

## Roles and Permissions

| Actor | Permission |
|---|---|
| Quiz owner | Submit published versions and withdraw their pending submissions |
| Active collaborator | Submit eligible versions and withdraw their pending submissions |
| Active faculty organizer | View all class submissions and approve or reject pending submissions |
| Ordinary active member | View approved quizzes and only their own submissions |
| Invited, removed, or departed member | No access |
| Unrelated faculty `ADMIN` | No global class-access bypass |
| Outsider | No access |

Self-approval is allowed when the quiz owner is also an active faculty
organizer.

Approval grants class availability only. It does not grant quiz editing,
collaborator management, class management, hosting authority, or reports and
results access.

## Submission States

| State | Meaning |
|---|---|
| `PENDING` | Waiting for an organizer decision |
| `APPROVED` | Available if the version remains current and hostable |
| `REJECTED` | Declined by an organizer |
| `WITHDRAWN` | Cancelled by the original submitter |

Approved, rejected, and withdrawn records are terminal and remain stored for
audit history.

Rejected and withdrawn versions may be submitted again if they are still
current and eligible. `PENDING` and `APPROVED` submissions count as active
duplicates.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/classes/{class_id}/quiz-submissions` | Submit a published version |
| `GET` | `/classes/{class_id}/quiz-submissions` | List submissions visible to the caller |
| `PATCH` | `/classes/{class_id}/quiz-submissions/{submission_id}` | Approve or reject |
| `DELETE` | `/classes/{class_id}/quiz-submissions/{submission_id}` | Soft-withdraw a pending submission |
| `GET` | `/classes/{class_id}/approved-quizzes` | List currently hostable approved versions |

`DELETE` does not physically delete the record. It changes the status to
`WITHDRAWN` and records the actor and timestamp.

See [API.md](API.md) for complete request, response, and error contracts.

## Implementation Structure

| Layer | Responsibility | Location |
|---|---|---|
| Migration | Creates the table, constraints, indexes, and rollback | [`0010_quiz_submission`](../ulugbek-err/migrations/0010_quiz_submission.up.sql) |
| Model | Maps submission records to Python objects | [`models/quiz_submission.py`](../backend/app/models/quiz_submission.py) |
| Schemas | Validate API requests and define responses | [`schemas/quiz_submission.py`](../backend/app/schemas/quiz_submission.py) |
| Routes | Expose the five HTTP endpoints | [`api/routes/quiz_submissions.py`](../backend/app/api/routes/quiz_submissions.py) |
| Service | Applies authorization, transitions, staleness, and hostability rules | [`services/quiz_submissions.py`](../backend/app/services/quiz_submissions.py) |
| Tests | Verify API, database, authorization, and concurrency behavior | [`test_quiz_submissions_api.py`](../backend/tests/test_quiz_submissions_api.py) |

```text
Client request
    ↓
Route and schema validation
    ↓
Authorization and service rules
    ↓
SQLAlchemy model
    ↓
MySQL database
    ↓
Response schema
    ↓
JSON response
```

Database constraints provide final duplicate and consistency protection, while
service checks provide clear API errors.

## Task 5 Integration

Task 4 provides:

```python
require_approved_quiz_version(
    db,
    class_id,
    quiz_version_id,
)
```

Task 5 will call this helper before creating a live session. The helper confirms
that the version is approved, published, current, in the requested class, and
attached to a non-archived quiz and class.

If valid, it returns the exact `QuizVersion`. Otherwise, session creation must
be rejected.

Task 5 remains responsible for requiring a class, checking host authority,
creating the session and join code, restricting participation to active class
members, and preserving WebSocket, timing, scoring, reconnect, and results
behavior.

## Archived Classes

Archived classes retain readable submission history but cannot receive new
submissions, approve pending submissions, return hostable quizzes, or pass the
Task 5 hostability check.

Cleanup remains possible: organizers may reject pending submissions, and
submitters may withdraw their own pending submissions.

## Automated API Coverage

The API test file contains 18 collected user-story scenarios.

### Submission and visibility

1. Owners and active collaborators can submit.
2. Ordinary classmates without quiz access cannot submit.
3. Revoked collaborators cannot submit.
4. Invited students cannot submit.
5. Removed members cannot submit.
6. Outsiders cannot submit.
7. Unrelated faculty receive no global bypass.

### Version and duplicate protection

8. Missing, cross-class, unpublished, and stale versions are rejected.
9. Duplicate pending or approved submissions are prevented.

### Decisions and eligibility changes

10. Faculty organizers can approve, including self-approval.
11. Approval is blocked if the submitter's account becomes inactive.
12. Approval is blocked if the submitter loses class membership.
13. Approval is blocked if collaboration access is revoked.

In cases 11–13, organizers may still reject the pending record.

### State, privacy, and hostability

14. Withdrawal is soft-audited, and terminal decisions cannot be changed.
15. Submission visibility uses non-leaking errors.
16. Archived classes block submissions, approvals, and hosting while allowing cleanup.
17. Only an approved, current version is hostable.
18. Approval does not grant editing or results access.

These are automated API or functional tests. They simulate authenticated users,
HTTP requests, service logic, and database state using an isolated test
database.

## Running the API Tests

From the repository root:

```bash
cd backend
python -m pytest --collect-only -q tests/test_quiz_submissions_api.py
```

This lists the 18 collected scenarios. Run them with:

```bash
python -m pytest -vv tests/test_quiz_submissions_api.py
```

Expected result at the time of merge:

```text
18 passed
```

A passing scenario means the API response and stored database state matched the
expected behavior.

Task 4 also includes model and schema tests, real-MySQL migration and rollback
tests, database constraint tests, duplicate-submission concurrency tests,
competing decision and withdrawal tests, complete backend regression testing,
and GitHub backend, frontend, and container CI checks.

## Out of Scope

Task 4 does not include:

- Submission-management frontend screens
- Organizer dashboard integration
- Email or in-app notifications
- Assignment to a specific reviewer
- Rejection comments
- Live-session creation
- Changes to WebSockets, scoring, timing, or results

These capabilities are handled by Task 5, Task 6, or future work.

For the complete technical contract, see
[V3_TASK4_SUBMISSION_APPROVAL_DRAFT.md](V3_TASK4_SUBMISSION_APPROVAL_DRAFT.md).
