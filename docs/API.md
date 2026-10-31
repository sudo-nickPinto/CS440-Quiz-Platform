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
{ "account_id": 7, "email": "a@gettysburg.edu", "display_name": "Ana", "role": "USER", "is_active": true }
```

`role` is `USER` or `ADMIN`.

## Quizzes

A quiz is saved and published in one step (one version, `version_number` 1). There are no drafts in the MVP.

### `POST /quizzes` → `201 QuizResponse`
Any active account. Unknown fields are rejected.

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

Errors: `500 quiz_save_failed`.

### `GET /quizzes` → `200 QuizListItem[]`
Published quizzes, newest first. An Admin also gets archived ones.

```json
[{ "quiz_id": 3, "author_id": 7, "status": "PUBLISHED", "title": "…", "description": null, "question_count": 10, "created_at": "…" }]
```

### `GET /quizzes/{quiz_id}` → `200 QuizResponse`
Full quiz, including correct answers. A non-published quiz is visible only to its author or an Admin; anyone else gets 404.

`QuizResponse`: `quiz_id, author_id, class_id, revision, status, visibility, created_at, updated_at, version`. `version` holds `quiz_version_id, version_number, title, description, created_at, published_at, questions[]`. Each question holds `question_id, question_order, question_type, question_text, explanation, time_limit_seconds, base_points, choices[]`. Each choice holds `choice_id, choice_order, choice_text, is_correct`.

Errors: `404 quiz_not_found`, `500 invalid_quiz`.

### `PATCH /quizzes/{quiz_id}/archive` → `200 QuizResponse`
Author or Admin. Sets `status` to `ARCHIVED`.

Errors: `403 quiz_access_denied`, `404 quiz_not_found`, `500 quiz_archive_failed`.

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

Collaborator management is owner-only:

```text
GET    /classes/{class_id}/quizzes/{quiz_id}/collaborators
POST   /classes/{class_id}/quizzes/{quiz_id}/collaborators
DELETE /classes/{class_id}/quizzes/{quiz_id}/collaborators/{account_id}
```

The POST body is `{ "email": "member@example.edu", "permission": "EDITOR" }`.
The email is normalized before lookup, and the target must be an active member
of the quiz's class. Revocation is audited and immediately blocks future draft
reads and writes. Errors include `account_not_found`, `not_class_member`,
`already_quiz_collaborator`, `quiz_owner_cannot_collaborate`,
`collaborator_management_denied`, and `quiz_collaborator_not_found`.

## Sessions

Statuses: `LOBBY → ACTIVE → COMPLETED`, or `LOBBY → CANCELLED`. Starting, advancing, ending and answering all happen over the WebSocket ([LIVE_PROTOCOL.md](LIVE_PROTOCOL.md) §1, §4). A session whose host is gone for 15 minutes is ended automatically (§5, PR #53).

`SessionResponse`: `session_id, quiz_id, quiz_version_id, quiz_title, host_id, class_id, join_code, status, current_question_order, created_at, started_at, ended_at`. `class_id` is `null` for an open session.

### `POST /quizzes/{quiz_id}/sessions` → `201 SessionResponse`
Only the quiz's author can host it (Admins can't host other people's quizzes). Creates a `LOBBY` session with a fresh 6-digit `join_code`.

Optional body: `{"class_id": 12}`. No body, or `{"class_id": null}`, creates an **open session** that anyone with the code can join. With a `class_id` it creates a **class session**: the caller must also be an active organizer of that class (or an Admin), and only the class's active members can join it.

| Status | Code | When |
|---|---|---|
| 403 | `session_host_denied` | Caller isn't the quiz author |
| 403 | `not_class_organizer` | `class_id` given and the caller isn't an active organizer or Admin |
| 404 | `class_not_found` | `class_id` given and the class doesn't exist or the caller isn't in it |
| 409 | `class_archived` | `class_id` given and the class is archived |
| 404 | `quiz_not_found` | |
| 409 | `quiz_not_hostable` | Quiz is archived, or has no published version |
| 500 | `session_creation_failed` | |
| 503 | `join_code_unavailable` | No free join code after several tries; retry |

### `POST /sessions/join` → `201 SessionJoinResponse`
Any active account. Body: `{"join_code": "123456"}` (6 digits; surrounding spaces are trimmed). Works in `LOBBY` or `ACTIVE`; a late joiner starts from the next question. The host is notified over the WebSocket after the commit.

Response: `{ "session": SessionResponse, "participant": { "session_participant_id", "account_id", "display_name", "joined_at" } }`.

| Status | Code | When |
|---|---|---|
| 403 | `not_class_member` | It's a class session and the caller isn't an active member, even with the right code |
| 404 | `join_code_not_found` | No LOBBY/ACTIVE session uses the code |
| 409 | `host_cannot_join` | The host tried to join their own session |
| 409 | `session_already_joined` | This account already has a participant row, even one that has left |
| 500 | `session_join_failed` | |

### `POST /sessions/{session_id}/join` → `201 SessionJoinResponse`
The class page's Live button: join a **class session** by id, with no code. Same response, errors and late-join rules as joining by code. Only active members of the session's class can use it. Open sessions answer `404 session_not_found` so they still need their code.

### `GET /classes/{class_id}/active-sessions` → `200 ClassActiveSession[]`
Any active member. The class's `LOBBY` and `ACTIVE` sessions, newest first; the class page polls it every 5 seconds to draw the Live button.

`ClassActiveSession`: `session_id, class_id, quiz_id, quiz_title, host_id, is_host, joined, left, join_code, status, current_question_order, question_count, created_at, started_at`. `joined` is true when the caller has an active participant row (`left_at IS NULL`), so the button goes straight to the game. `left` is true when the caller previously participated but left; that participant row is permanent, so the Live button is disabled and they cannot rejoin. Nonmembers get `404 class_not_found`.

### `GET /sessions/{session_id}` → `200 SessionResponse`
Host, Admin, or a participant who hasn't left.

Errors: `403 session_access_denied`, `404 session_not_found`, `500 invalid_session`.

### `GET /sessions/{session_id}/participants` → `200 SessionParticipant[]`
Host or Admin. Participants who haven't left, in join order.

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
- Host or Admin: `{ session_id, status, ended_at, standings: [{ session_participant_id, display_name, total_score, correct_count, final_rank }] }`.
- Participant: `{ session_id, status, ended_at, me: <own standing or null>, leaderboard: [{ display_name, total_score, final_rank }] }` (top 5).

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
  - the first ten `students`, for organizers.
- `GET /classes/{class_id}/sessions`: for any member. It takes `page`, `page_size` (1–100), `sort=started_at|participant_count|average_score` and `order`. Each item has:
  - `session_id, quiz_id, quiz_title, status, host_name, is_host, started_at, ended_at, participant_count`;
  - `average_score` and `top_score`, which are organizers only;
  - `my_score` and `my_rank`, the caller's own result or null.
- `GET /classes/{class_id}/quizzes`: for any member. Completed sessions grouped by quiz, with `presented_at, session_count, participant_count` and `average_score` (organizers only). It takes `sort=presented_at|title|participant_count`.
- `GET /classes/{class_id}/students`: organizers only (`403 not_class_organizer`). Active `MEMBER`s, with:
  - `session_count, average_score, total_points`;
  - `attendance_rate` (0–1);
  - `recent_scores`, the last five sessions newest first, with null where they were absent.

  It takes `sort=name|average_score|session_count`.

All four use the same paging shape: `{ class_id, items, pagination: { page, page_size, total_items, total_pages } }`.

### Detailed class reports
For one session, one quiz or one student. Like the lists above, they only count the class's `COMPLETED` sessions and use stored scores. All three are sent with `Cache-Control: no-store`.

Organizers and Admins see everyone. Members see only their own rows, and class-wide numbers come back null for them. People without an active membership get `404 class_not_found`.

- `GET /classes/{class_id}/sessions/{session_id}/results`: the same body as `GET /sessions/{session_id}/report`, plus `class_id` and `started_at`. Any organizer gets every player (`view: "host"`), not just the one who hosted. A member gets `view: "participant"` with only their own row.
  - Errors: `404 session_not_found` (a session from another class, an open session, or one that isn't `COMPLETED`), `403 participant_report_denied` (a member who didn't play it).
- `GET /classes/{class_id}/quizzes/{quiz_id}/results`: every completed presentation of the quiz in this class, newest first. It returns `{ class_id, quiz_id, title, session_count, participant_count, average_score, sessions }`.
  - Each session has the same fields as a `/sessions` item, plus `results: [{ account_id, name, rank, points, correct }]`. Members only get their own result.
  - `average_score` is averaged over every player in every session (organizers only).
  - Errors: `404 quiz_not_found`. A quiz that was never presented here returns an empty `sessions` list.
- `GET /classes/{class_id}/students/{account_id}/results`: one student's history in the class. Members can only ask for themselves (`403 not_class_organizer` otherwise). It returns:
  - `display_name`, `email` (organizers only), `role` and `status`. Removed and departed students keep their history;
  - `class_session_count`, `session_count`, `attendance_rate`, `total_points`, `average_score`, `correct_count` and `incorrect_count`;
  - `class_average`, organizers only, using the same formula as the dashboard;
  - `sessions`: every completed class session, newest first, with `played, points, rank, question_count, correct, incorrect`. The last four are null when the student missed it. Unanswered questions count as incorrect.
  - Errors: `404 student_not_found` (never in this class).

### `GET /classes/{class_id}/grades/export.csv` → `200 text/csv`
Organizers only. Returns `{class-name}-grades.csv`, a gradebook (UTF-8 with BOM, `no-store`):
- one row per student, sorted by name;
- one column per completed session, oldest first (`Quiz title (YYYY-MM-DD)`), where an empty cell means absent;
- then `Sessions played, Attendance %, Average points, Total points`.

Cells get the same formula escaping as the session export.
