# REST API reference

What the FastAPI backend serves today, taken from `backend/app/api/routes/`. Request and response shapes come from `backend/app/schemas/`; the live WebSocket has its own spec in [LIVE_PROTOCOL.md](LIVE_PROTOCOL.md).

With the backend running, FastAPI's generated docs are at `/docs` on the backend (e.g. `http://localhost:8001/docs`). This page adds what those don't show: who may call each route and which error codes it returns.

## Conventions

- **Auth.** Every route except `GET /` and `GET /health` needs `Authorization: Bearer <Auth0 access token>` for the API audience. The first authenticated request creates the caller's `account` row (see [AUTH.md](AUTH.md)).
- **Roles.** There are two: **User** and **Admin** (`/me` → `role`). Hosting and playing aren't roles; anyone can do either.
- **Active accounts.** Every route below `/me` also rejects a deactivated account with `403 inactive_account`. `/me` itself still answers, returning `is_active: false`, so the frontend can show the deactivated screen.
- **Times** are UTC ISO 8601. Most are naive (no offset), because the MySQL `DATETIME` columns are naive UTC.
- **IDs** are positive integers. Join codes are 6 digits.

### Error shape

Every error, including validation errors, has this body:

```json
{ "error": { "code": "session_not_found", "message": "Session not found.", "details": null } }
```

`details` is present only for `422 request_validation_error`, where it is FastAPI's list of field errors. Clients should branch on `code`, never on `message`.

**Errors any authenticated route can return**

| Status | Code | When |
|---|---|---|
| 401 | `missing_token` | No bearer token |
| 401 | `invalid_token` | Bad signature, audience, issuer or expiry |
| 403 | `email_not_verified` | The Auth0 email isn't verified yet (account not created or linked) |
| 403 | `inactive_account` | The account is deactivated (every route except `/me`) |
| 422 | `request_validation_error` | Body or path failed validation |
| 500 | `auth_not_configured` | `AUTH0_DOMAIN` / `AUTH0_AUDIENCE` not set on the server |
| 500 | `internal_server_error` | Unhandled exception (logged server-side) |
| 502 | `profile_unavailable` | Auth0 `/userinfo` failed while creating or linking the account |

The tables below list only the route-specific codes.

## System

### `GET /`
No auth. Returns `{"message": "Quiz Platform API"}`.

### `GET /health`
No auth. `200 {"status": "ok", "components": {"database": "ok"}}`, or `503 database_unavailable`.

## Account

### `GET /me`
The caller's account, created on first call.

```json
{
  "account_id": 7, "email": "a@gettysburg.edu", "display_name": "Ana Lopez",
  "first_name": "Ana", "last_name": "Lopez", "avatar_key": "owl.sky",
  "profile_complete": true, "role": "USER", "is_active": true
}
```

`role` is `USER` or `ADMIN`. `profile_complete` is false until both names are saved; the app shows the profile setup screen until then. `first_name`, `last_name` and `avatar_key` are `null` on a new account.

### `PATCH /me`
Saves the caller's profile and returns the same body as `GET /me`. Always send all three fields:

```json
{ "first_name": "Ana", "last_name": "Lopez", "avatar_key": "owl.sky" }
```

- Names are trimmed and must be 1–50 characters with no control characters.
- `avatar_key` is `"figure.color"` from the preset list in `backend/app/avatars.py`, or `null` for initials. There are no uploads.
- `display_name` becomes `"First Last"`, so every screen, report and export that shows names picks up the change.

Errors: `403 inactive_account`, `422 invalid_profile` (blank or too-long name, bad characters, unknown avatar).

## Quizzes

Since V3, **every quiz belongs to a class** (`class_id`), and there is no app-wide quiz list. Who can do what:
- **Create:** any active member or organizer of the class. The creator becomes the quiz's owner (`author_id`). Nobody needs a special permission.
- **See:** the owner and the class's organizers (the class-level `ORGANIZER` role), and only while they're active in the class. Other classmates and outsiders get `404`. Being an Admin doesn't help: there is no app-wide authority over classes.
- **New quizzes are drafts:** `status: "DRAFT"`, and `version.published_at` is null. A draft can't be hosted. Publishing (task 3) makes an unchangeable version, and doesn't approve it for hosting (task 4).
- `visibility` is always `PRIVATE` for new quizzes. `PUBLIC` no longer shows a quiz outside its class.

Responses show the version people work on: the newest draft if there is one, otherwise the newest published version.

Quizzes made before V3 may have `class_id: null` until someone gives them a class ([migrations README](../ulugbek-err/migrations/README.md#quizzes-without-a-class)). Only their owner can see them.

### `POST /classes/{class_id}/quizzes` → `201 QuizResponse`
Active members and organizers of the class. Unknown fields are rejected. (`POST /quizzes` is gone.)

```json
{
  "title": "Week 3 review",
  "description": "optional",
  "questions": [
    {
      "question_text": "2 + 2?",
      "explanation": "optional, shown after the question closes",
      "time_limit_seconds": 20,
      "base_points": 1000,
      "choices": [
        { "choice_text": "4", "is_correct": true },
        { "choice_text": "5" }
      ]
    }
  ]
}
```

Validation:
- `title`: required, 1 to 200 characters, trimmed.
- `questions`: at least one.
- Each question:
  - non-blank text;
  - 2 to 255 choices, at least one of them correct;
  - `time_limit_seconds` from 1 to 65535 (default 20);
  - `base_points` of at least 1 (default 1000).
- Each choice: 1 to 500 characters.

Errors:
- `404 class_not_found`: the class doesn't exist, or the caller isn't an active member (invited, left, removed or never joined).
- `409 class_archived`.
- `500 quiz_save_failed`.

### `GET /classes/{class_id}/quizzes` → `200 ClassQuizListPage`
The class's quizzes. Organizers get every quiz in the class; members get only the ones they own or collaborate on. `mine=true` narrows an organizer's list the same way. It takes `page`, `page_size` (1–100, default 25), `sort=created_at|updated_at|title` (default `created_at`) and `order=asc|desc` (default `desc`). Each item's `my_access` is `OWNER`, `EDITOR` (an active collaborator), or null when an organizer sees someone else's quiz. `published_version_id` is the newest published version (null for a draft-only quiz), and `approval_status` / `approval_submission_id` describe that version's newest submission to this class (`PENDING`, `APPROVED`, `REJECTED`, `WITHDRAWN`, or null if it was never submitted). `approval_sent_by_me` says whether the caller sent that submission, so the class page offers Withdraw only to them.

```json
{
  "class_id": 4,
  "items": [{ "quiz_id": 3, "author_id": 7, "author_name": "Amy", "class_id": 4, "status": "PUBLISHED", "title": "…", "description": null, "question_count": 10, "version_number": 2, "created_at": "…", "updated_at": "…", "my_access": "OWNER" }],
  "pagination": { "page": 1, "page_size": 25, "total_items": 1, "total_pages": 1 }
}
```

Errors: `404 class_not_found`.

### `GET /classes/{class_id}/quizzes/{quiz_id}` → `200 QuizResponse`
One quiz in the class, for its owner or a class organizer. Errors: `404 class_not_found`, and `404 quiz_not_found` when the quiz isn't in this class or the caller can't see it.

### `GET /quizzes` → `200 QuizListItem[]`
The caller's own quizzes, across every class they're active in, newest first. Includes archived ones.

```json
[{ "quiz_id": 3, "author_id": 7, "class_id": 4, "status": "PUBLISHED", "title": "…", "description": null, "question_count": 10, "created_at": "…" }]
```

### `GET /quizzes/{quiz_id}` → `200 QuizResponse`
Full quiz, including correct answers. Same rule as above: only the owner or an organizer of the quiz's class, and anyone else gets 404.

`QuizResponse`: `quiz_id, author_id, class_id, revision, status, visibility, created_at, updated_at, version`. `version` holds `quiz_version_id, version_number, title, description, created_at, published_at, questions[]`. Each question holds `question_id, question_order, question_type, question_text, explanation, time_limit_seconds, base_points, choices[]`. Each choice holds `choice_id, choice_order, choice_text, is_correct`.

Errors: `404 quiz_not_found`, `500 invalid_quiz`.

### `PATCH /quizzes/{quiz_id}/archive` → `200 QuizResponse`
The quiz's owner only. Sets `status` to `ARCHIVED`.

Errors: `403 quiz_access_denied` (an organizer who isn't the owner), `404 quiz_not_found`, `500 quiz_archive_failed`.

### V3 class quiz drafts and collaborators

`POST /classes/{class_id}/quizzes` creates a private draft owned by the caller.
The caller must be an active member of the class. Its initial `revision` is 1
and its version has `published_at: null`.

`GET /classes/{class_id}/quizzes/{quiz_id}` returns the editable draft to its
owner or an active named collaborator. `PUT` on the same URL replaces the
draft content and requires `expected_revision`. A successful transaction
increments the quiz revision exactly once. A stale request returns:

```json
{
  "error": {
    "code": "quiz_edit_conflict",
    "message": "This quiz changed after you opened it. Reload the latest version before saving again.",
    "details": { "current_revision": 4 }
  }
}
```

`base_version` is not accepted in V3: published version numbers and optimistic
revisions are separate counters. Clients must fetch `QuizResponse.revision` and
send it back as `expected_revision`.

`POST /classes/{class_id}/quizzes/{quiz_id}/publish` publishes the current
draft and takes `{ "expected_revision": 4 }`. Only the quiz owner may publish.
It timestamps the draft, changes the quiz status to `PUBLISHED`, and increments
the revision exactly once. Collaborators can edit but cannot publish. A later
edit creates a new draft version without changing the published version.

Publish errors include `quiz_publish_denied`, `quiz_not_publishable`, and
`quiz_edit_conflict`.

Collaborator management is owner-only:

```text
GET    /classes/{class_id}/quizzes/{quiz_id}/collaborators
POST   /classes/{class_id}/quizzes/{quiz_id}/collaborators
DELETE /classes/{class_id}/quizzes/{quiz_id}/collaborators/{account_id}
```

The POST body is `{ "email": "member@example.edu", "permission": "EDITOR" }`.
The email is normalized before lookup, and the target must be an active member
of the quiz's class. Unknown emails and accounts outside the class both return
`not_class_member`, so this endpoint cannot probe account registration.
Every share and revocation is preserved in an append-only audit table, while
revocation immediately blocks future draft reads and writes. Errors include `not_class_member`,
`already_quiz_collaborator`, `quiz_owner_cannot_collaborate`,
`collaborator_management_denied`, and `quiz_collaborator_not_found`.

## Quiz submissions and approvals

Task 4 adds a class approval layer around an exact immutable quiz version.
Every route first requires an active membership in the class; missing classes,
invited/removed/left members, outsiders, and unrelated faculty all receive
`404 class_not_found`. Approval makes a version available to the class but does
not grant edit, collaborator, class-management, report, or results access.
Archived classes retain readable submission history, but cannot receive new
submissions, approve versions, or return hostable quizzes. Organizers may still
reject pending submissions, and submitters may still withdraw their own.

### `POST /classes/{class_id}/quiz-submissions` → `201 QuizSubmissionResponse`

Body: `{ "quiz_version_id": 321 }`. The caller must own the quiz or be an
active named collaborator. The exact version must be published, current,
non-archived, and owned by this class. A newer draft does not make a published
version stale; a newer published version does.

Errors: `404 quiz_version_not_found`, `409 class_archived`,
`409 quiz_version_not_published`, `409 quiz_version_stale`,
`409 quiz_submission_conflict`, and
`500 quiz_submission_failed`. The database's generated active-version key
makes duplicate pending/approved submissions safe under concurrent requests.

### `GET /classes/{class_id}/quiz-submissions` → `200 QuizSubmissionResponse[]`

Newest first, without pagination. Active faculty organizers see every class
submission; other active members see only submissions they created.

`QuizSubmissionResponse`: `submission_id, class_id, quiz_version_id,
submitted_by_id, status, decided_by_id, submitted_at, decided_at`.

### `PATCH /classes/{class_id}/quiz-submissions/{submission_id}` → `200 QuizSubmissionResponse`

Body accepts only `{ "status": "APPROVED" }` or
`{ "status": "REJECTED" }`. Only an active faculty `ORGANIZER` may decide;
self-approval is allowed. Approval rechecks the version and that the submitter
still has an active account and class membership and still owns or actively
collaborates on the quiz. Rejection remains available after that eligibility
is lost or the class is archived. Approval of an archived class returns
`409 class_archived`. Conditional `PENDING` updates give concurrent decisions
one winner.

Errors: `404 submission_not_found`, `403 not_class_organizer`,
`409 class_archived`, `409 submission_no_longer_eligible`,
`409 invalid_submission_transition`, the version errors above, and
`500 quiz_submission_decision_failed`.

### `DELETE /classes/{class_id}/quiz-submissions/{submission_id}` → `204`

Soft-withdraws the original submitter's pending row. The row remains as
`WITHDRAWN`, with the submitter in `decided_by_id` and a `decided_at` timestamp.
Rejected and withdrawn versions may be submitted again.
Withdrawal remains available after the class is archived so pending records
can be closed without deleting their audit history.

Errors: `404 submission_not_found`, `403 not_submission_owner`,
`409 invalid_submission_transition`, and
`500 quiz_submission_withdrawal_failed`. A submission the caller cannot see is
always `404`; the 403 applies only when the resource is visible.

### `GET /classes/{class_id}/approved-quizzes` → `200 ApprovedQuizResponse[]`

Available to every active class member. Returns approved, published, current,
non-archived versions that still belong to the class, newest approval first.
An archived class returns `409 class_archived` instead of a hostable list.

`ApprovedQuizResponse`: `submission_id, quiz_id, quiz_version_id,
version_number, title, author_id, approved_at, approved_by_id`.

Task 4 also exposes
`require_approved_quiz_version(db, class_id, quiz_version_id)` for Task 5. It
uses the same filtering and raises `409 quiz_version_not_approved` when the
exact version is not currently hostable, or `409 class_archived` when the class
itself cannot host. Session creation calls it (Task 5).

## Sessions

Statuses: `LOBBY → ACTIVE → COMPLETED`, or `LOBBY → CANCELLED`. Starting, advancing, ending and answering all happen over the WebSocket ([LIVE_PROTOCOL.md](LIVE_PROTOCOL.md) §1, §4). A session whose host is gone for 15 minutes is ended automatically (§5, PR #53).

`SessionResponse`: `session_id, quiz_id, quiz_version_id, quiz_title, host_id, class_id, join_code, status, current_question_order, created_at, started_at, ended_at`. Every new session has a `class_id`. It's `null` only on old sessions from before V3, which are read-only history: nobody can join or answer in them.

### `POST /classes/{class_id}/quizzes/{quiz_id}/sessions` → `201 SessionResponse`
Starts a `LOBBY` session in the class with a fresh 6-digit `join_code`. There are no open sessions: every session belongs to a class, and only the class's active members can join it. No body.

Rules, checked in this order:
1. The caller is an active member of the class, and the class isn't archived.
2. The quiz belongs to this class.
3. The caller is the quiz owner or an active organizer of the class. Organizer powers need faculty status too, the same rule as every other organizer action, so an old non-faculty organizer can only host their own quizzes. Being a collaborator isn't enough, and faculty status alone (without being an organizer of this class) gives no extra access.
4. The quiz isn't archived, has a published version, and has no unpublished draft on top of it (an edited quiz must be published and approved again).
5. That newest published version is approved for the class (Task 4). Pending, rejected, withdrawn and stale (a newer version was published) versions can't be hosted.

| Status | Code | When |
|---|---|---|
| 404 | `class_not_found` | The class doesn't exist or the caller isn't an active member |
| 409 | `class_archived` | The class is archived |
| 404 | `quiz_not_found` | The quiz doesn't exist or belongs to another class |
| 403 | `session_host_denied` | Caller is neither the quiz owner nor a class organizer |
| 409 | `quiz_not_hostable` | Quiz is archived, or has no published version |
| 409 | `quiz_version_not_approved` | The newest published version isn't approved for the class |
| 500 | `session_creation_failed` | |
| 503 | `join_code_unavailable` | No free join code after several tries; retry |

The old `POST /quizzes/{quiz_id}/sessions` route is gone.

When hosting is refused for one of rules 1–5, the error also says exactly why, in `error.details.reason`, and the `message` says what to do next. The error codes above stay the same.

**Knowing before you click.** Quiz responses (`GET /quizzes`, `GET /quizzes/{id}`, `GET /classes/{id}/quizzes`, `GET /classes/{id}/quizzes/{quiz_id}`, and the create, update and publish responses) include a `hosting` object for the caller. It comes from the same checks as this endpoint, so the Host button and the server always agree:

```json
"hosting": { "can_host": false, "reason": "pending_approval", "message": "This quiz is waiting for a class organizer to approve it." }
```

| `reason` | Meaning | Error code when you try anyway |
|---|---|---|
| `not_in_class` | Old quiz with no class | `quiz_not_hostable` |
| `class_archived` | The class is archived | `class_archived` |
| `not_host` | Caller isn't the quiz owner or a class organizer | `session_host_denied` |
| `quiz_archived` | The quiz is archived | `quiz_not_hostable` |
| `not_published` | Still a draft | `quiz_not_hostable` |
| `unpublished_changes` | Edited after publishing. The page shows the new draft, so the older published version isn't hosted silently; publish and get the new version approved | `quiz_not_hostable` |
| `not_submitted` | Published but never submitted for approval | `quiz_version_not_approved` |
| `pending_approval` | Waiting for an organizer | `quiz_version_not_approved` |
| `rejected` | An organizer rejected this version | `quiz_version_not_approved` |
| `withdrawn` | The submission was withdrawn | `quiz_version_not_approved` |
| `approval_outdated` | An older version was approved, but not the newest one | `quiz_version_not_approved` |

When hosting is allowed, `hosting` is `{"can_host": true, "reason": null, "message": null}`.

The status is loaded in a fixed number of queries for the whole list, so long quiz lists don't make extra database calls.

### `POST /sessions/join` → `201 SessionJoinResponse`
Any active account. Body: `{"join_code": "123456"}` (6 digits; surrounding spaces are trimmed). Works in `LOBBY` or `ACTIVE`; a late joiner starts from the next question. The host is notified over the WebSocket after the commit.

Response: `{ "session": SessionResponse, "participant": { "session_participant_id", "account_id", "display_name", "joined_at" } }`.

| Status | Code | When |
|---|---|---|
| 403 | `not_class_member` | The caller isn't an active member of the session's class, even with the right code (also for old sessions with no class) |
| 404 | `join_code_not_found` | No LOBBY/ACTIVE session uses the code |
| 409 | `host_cannot_join` | The host tried to join their own session |
| 409 | `session_already_joined` | This account already has a participant row, even one that has left |
| 500 | `session_join_failed` | |

### `POST /sessions/{session_id}/join` → `201 SessionJoinResponse`
The class page's Live button: join a session by id, with no code. Same response, errors and late-join rules as joining by code. Only active members of the session's class can use it; anyone else gets `404 session_not_found`.

### `GET /classes/{class_id}/active-sessions` → `200 ClassActiveSession[]`
Any active member. The class's `LOBBY` and `ACTIVE` sessions, newest first; the class page polls it every 5 seconds to draw the Live button.

`ClassActiveSession`: `session_id, class_id, quiz_id, quiz_title, host_id, is_host, joined, left, join_code, status, current_question_order, question_count, created_at, started_at`. `joined` is true when the caller has an active participant row (`left_at IS NULL`), so the button goes straight to the game. `left` is true when the caller previously participated but left; that participant row is permanent, so the Live button is disabled and they cannot rejoin. Nonmembers get `404 class_not_found`.

### `GET /sessions/{session_id}` → `200 SessionResponse`
Host, Admin, or a participant who hasn't left.

Errors: `403 session_access_denied`, `404 session_not_found`, `500 invalid_session`.

### `GET /sessions/{session_id}/participants` → `200 SessionParticipant[]`
Host or Admin. Participants who haven't left, in join order. Each row is `{ session_participant_id, account_id, display_name, avatar_key, joined_at }`.

Errors: `403 session_access_denied`, `404 session_not_found`, `500 invalid_participant`.

### `POST /sessions/{session_id}/questions/{session_question_id}/responses` → `201 ResponseReceipt`
An active participant answers the open question. This is the REST alternative to the socket's `submit_answer`; both run the same checks and the same after-answer hook. Body: `{"choice_id": 42}`. Only the first answer counts.

The receipt deliberately leaves out correctness and points until the question closes: `{ "response_id", "session_question_id", "choice_id", "submitted_at" }`.

| Status | Code | When |
|---|---|---|
| 403 | `not_session_participant` | Not an active participant (never joined, or left) |
| 404 | `session_not_found` / `session_question_not_found` | |
| 409 | `session_not_active` | Session isn't ACTIVE |
| 409 | `question_not_open` | Question is PENDING or CLOSED |
| 409 | `response_deadline_passed` | Arrived after `closes_at` |
| 409 | `joined_after_question_opened` | Joined after this question opened (`joined_at > opened_at`); they start with the next question |
| 409 | `response_already_submitted` | Already answered this question |
| 422 | `choice_not_for_question` | `choice_id` belongs to another question |
| 500 | `invalid_question_timing` | Server timestamps are inconsistent |

## Results and reports

All three routes below need the session to have **ended** (`COMPLETED` or `CANCELLED`). Access is the same for all three:
- the host or an Admin sees every participant;
- anyone who played, even if they left early, sees their own cut.

Shared errors: `403 session_access_denied`, `404 session_not_found`, `409 results_not_ready`.

### `GET /sessions/{session_id}/results` → `200 FinalResults | ParticipantFinalResults`
Final standings, matching the live `session_ended` event. Ties share a rank (1, 1, 3).
- Host or Admin: `{ session_id, status, ended_at, standings: [{ session_participant_id, display_name, avatar_key, total_score, correct_count, final_rank }] }`.
- Participant: `{ session_id, status, ended_at, me: <own standing or null>, leaderboard: [{ display_name, avatar_key, total_score, final_rank }] }` (top 5).

### `GET /sessions/{session_id}/report` → `200`
Per-question breakdown for the results pages, sent with `Cache-Control: no-store`.

```json
{
  "session_id": 12, "view": "host", "status": "COMPLETED",
  "quiz_title": "…", "host_name": "…", "ended_at": "…+00:00",
  "total_participants": 8, "played_count": 5,
  "questions": [{ "question_id", "order", "text", "explanation", "seconds", "base_points", "played", "choices": [{ "id", "text", "correct" }] }],
  "players": [{ "id", "name", "rank", "points", "correct",
                "answers": [{ "question_id", "state", "choice_id", "points", "time_ms" }] }]
}
```

- `view` is `participant` for a player, and `players` then holds only their own row.
- `state` is one of `correct`, `wrong`, `missed` or `not_played`.
- A `CANCELLED` session returns empty `questions` and `players`.

Extra error: `500 results_incomplete`.

### `GET /sessions/{session_id}/results/export.csv` → `200 text/csv`
Host or Admin only. Returns `session-{id}-results.csv` (UTF-8 with BOM, `no-store`). It contains:
- the summary;
- the leaderboard;
- one row per participant per question.

Cells starting with `=`, `+`, `-` or `@` get a leading `'` so spreadsheets don't run them as formulas.

Extra errors: `403 results_export_denied` (a participant), `500 results_incomplete`.

## WebSocket

`/ws/sessions/{session_id}`: the host and participant live channel. Authentication is the first message, not the URL. See [LIVE_PROTOCOL.md](LIVE_PROTOCOL.md) for events, close codes and reconnects. In a class session the socket re-checks membership; a member removed mid-game is closed with `4403 not_class_member`, and their answers are refused with `403 not_class_member`.

## Classes

How the class features fit together is in [CLASSES.md](CLASSES.md); the original design is [CLASS_APPROVAL.md](CLASS_APPROVAL.md). Class-aware session routes are listed under [Sessions](#sessions) above.

### `POST /classes/join` → `200 ClassResponse`
Join a class by its code. Body: `{"code": "ABCD-2345"}`. Case, spaces and the dash don't matter. The caller becomes an active `MEMBER` (`joined_via: CODE`). A pending invite or an earlier membership they left is reactivated. The invite link `/app/join/class/{code}` in the frontend calls this route.

| Status | Code | When |
|---|---|---|
| 403 | `class_joining_closed` | The code is turned off, or the class is archived |
| 403 | `class_member_removed` | An organizer removed them; only a new invite lets them back |
| 404 | `class_code_not_found` | No class has that code |
| 409 | `already_class_member` | Already an active member |
| 429 | `too_many_join_attempts` | More than 10 tries in a minute from one account (counted per server process) |

### `DELETE /classes/{class_id}/membership` → `204`
Leave a class. The membership becomes `LEFT`, and the code brings them back. Errors: `404 class_not_found` (not a member), `409 not_class_member` (an Admin who never joined), `409 last_organizer`.

### Class reports
Built from the class's `COMPLETED` sessions only; open sessions never count. Scores are each player's `result.total_score`.

- `GET /classes/{class_id}/dashboard`: for any member. It returns:
  - `student_count` and `completed_session_count`;
  - `class_average` and `attendance_rate`, which are organizers only and null for members;
  - `active_sessions`;
  - the five most recent `completed_sessions` and `presented_quizzes`;
  - the first ten `students`, for organizers;
  - `my_quizzes`, the five most recently updated quizzes in this class the caller owns or collaborates on (same items as `GET /classes/{class_id}/quizzes?mine=true`), and `my_quiz_count`, the full total.
  - `pending_submission_count`: every pending submission in the class for organizers, the caller's own for members; and `approved_quiz_count`, the hostable approved quizzes.

  `is_global_admin` was removed in V3: Admin status never grants access to a class.
- `GET /classes/{class_id}/sessions`: for any member. It takes `page`, `page_size` (1–100), `sort=started_at|participant_count|average_score` and `order`. Each item has:
  - `session_id, quiz_id, quiz_title, status, host_name, is_host, started_at, ended_at, participant_count`;
  - `average_score` and `top_score`, which are organizers only;
  - `my_score` and `my_rank`, the caller's own result or null.
- `GET /classes/{class_id}/presented-quizzes`: for any member. (It was `/quizzes` before V3; that address now lists the class's own quizzes.) Completed sessions grouped by quiz, with `presented_at, session_count, participant_count` and `average_score` (organizers only). It takes `sort=presented_at|title|participant_count`.
- `GET /classes/{class_id}/students`: organizers only (`403 not_class_organizer`). Active `MEMBER`s, with:
  - `session_count, average_score, total_points`;
  - `attendance_rate` (0–1);
  - `recent_scores`, the last five sessions newest first, with null where they were absent.

  It takes `sort=name|average_score|session_count`.

- `GET /classes/{class_id}/dashboard/submissions`: for any member (V3 Task 6). Organizers see every submission in the class; members see their own. It takes `status=PENDING|APPROVED|REJECTED|WITHDRAWN` (optional), `sort=submitted_at|title|submitter` (default `submitted_at`) and `order` (default `desc`). Each item has `submission_id, quiz_id, quiz_version_id, version_number, quiz_title, question_count, submitted_by_id, submitter_name, status, submitted_at, decided_at, decided_by_name`, and `is_current_version` (false once a newer version is published). Decisions still go through `PATCH`/`DELETE /classes/{class_id}/quiz-submissions/{submission_id}`. Counting, sorting and paging happen in the database.
- `GET /classes/{class_id}/dashboard/submissions/{submission_id}/preview`: the organizer or the submitter (others get `404 submission_not_found`). Returns `{ submission, version }`: the same summary as above plus the exact submitted `QuizVersion` with its questions and choices (including `is_correct`), never the quiz's newer draft. The Approvals queue links here (`/app/classes/{class_id}/submissions/{submission_id}`) so organizers review what they approve.
- `GET /classes/{class_id}/dashboard/approved-quizzes`: for any member (V3 Task 6). The same versions as `GET /classes/{class_id}/approved-quizzes`, paged, with `title, question_count, author_name, approved_at, approved_by_name`, and `hosting` plus `can_host`, from the same checks as starting a session (see the `hosting` reasons above), so the owner sees why an approved quiz is blocked, for example `unpublished_changes`, and other members get `not_host`. `can_view` says whether the caller may open `GET /quizzes/{quiz_id}` (owner, organizer, or active collaborator); the Present tab only links the card when it's true. It takes `sort=approved_at|title` and `order`. An archived class returns its list with `can_host` false (`class_archived`) instead of `409`.

All six use the same paging shape: `{ class_id, items, pagination: { page, page_size, total_items, total_pages } }`.

### Detailed class reports
For one session, one quiz or one student. Like the lists above, they only count the class's `COMPLETED` sessions and use stored scores. All three are sent with `Cache-Control: no-store`.

Organizers and Admins see everyone. Members see only their own rows, and class-wide numbers come back null for them. People without an active membership get `404 class_not_found`.

- `GET /classes/{class_id}/sessions/{session_id}/results`: the same body as `GET /sessions/{session_id}/report`, plus `class_id` and `started_at`. Any organizer gets every player (`view: "host"`), not just the one who hosted. A member gets `view: "participant"` with only their own row.
  - Errors: `404 session_not_found` (a session from another class, an open session, or one that isn't `COMPLETED`), `403 participant_report_denied` (a member who didn't play it).
- `GET /classes/{class_id}/quizzes/{quiz_id}/results`: every completed presentation of the quiz in this class, newest first. It returns `{ class_id, quiz_id, view, title, session_count, participant_count, average_score, sessions }`, where `view` is `organizer` or `member`.
  - Each session has the same fields as a `/sessions` item, plus `results: [{ account_id, name, rank, points, correct }]`. Members only get their own result.
  - `average_score` is averaged over every player in every session (organizers only).
  - Errors: `404 quiz_not_found`, also for a quiz that has no completed session in this class.
- `GET /classes/{class_id}/students/{account_id}/results`: one student's history in the class. Members can only ask for themselves (`403 not_class_organizer` otherwise). It returns:
  - `view`: `organizer` or `member`;
  - `display_name`, `email` (organizers only), `role` and `status`. Removed and departed students keep their history;
  - `class_session_count`, `session_count`, `attendance_rate`, `total_points`, `average_score`, `correct_count` and `incorrect_count`;
  - `class_average`, organizers only, using the same formula as the dashboard;
  - `sessions`: every completed class session, newest first, with `played, points, rank, question_count, correct, incorrect`. The last four are null when the student missed it. Unanswered questions count as incorrect.
  - Errors: `404 student_not_found` (never in this class).

### Excel exports of the class reports → `200 .xlsx`
Each export is built from the matching report above, so the workbook shows the same numbers. They return `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` with `Cache-Control: no-store`. They take the same errors as the report, and times are in UTC.

| Endpoint | Who | File | Sheets |
|---|---|---|---|
| `GET /classes/{class_id}/sessions/{session_id}/export.xlsx` | Organizers | `class-{cid}-session-{sid}-results.xlsx` | **Summary**; **Scores** (rank, participant, total points, correct); **Answers** (one row per participant per question: result, selected and correct answer, time, points) |
| `GET /classes/{class_id}/quizzes/{quiz_id}/export.xlsx` | Organizers | `class-{cid}-quiz-{qid}-results.xlsx` | **Summary**; **Presentations** (one row per completed presentation); **Results** (every player's result in each presentation) |
| `GET /classes/{class_id}/students/{account_id}/export.xlsx` | Organizers, or the student themselves | `class-{cid}-student-{aid}-results.xlsx` | **Summary** (totals, attendance, class average); **Sessions** (every completed class session, played or not) |

- A member who exports a session or quiz gets `403 not_class_organizer`. So does a member who exports another student.
- A member's own student export leaves out the email and the class average, as the report does.
- Cells starting with `=`, `+`, `-` or `@` get a leading `'`, as in the CSV exports, so they stay text. Control characters that Excel can't store are dropped.

### `GET /classes/{class_id}/grades/export.csv` → `200 text/csv`
Organizers only. Returns `{class-name}-grades.csv`, a gradebook (UTF-8 with BOM, `no-store`):
- one row per student, sorted by name;
- one column per completed session, oldest first (`Quiz title (YYYY-MM-DD)`), where an empty cell means absent;
- then `Sessions played, Attendance %, Average points, Total points`.

Cells get the same formula escaping as the session export.
