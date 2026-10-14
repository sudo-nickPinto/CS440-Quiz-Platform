# Class approval (after the MVP)

A proposal for how approving users should work once we add classes. **Nothing here is built yet, and none of it is in the MVP.** The schema changes are proposals for Ulugbek, who owns the database files. This doc adds no migration.

It replaces the approach in #39 (closed). #39 had an app-wide "approve this signup" queue. The team decided on 2026-10-14 not to do that.

## 1. Goal and scope

- **Approval is per class.** A class's teacher decides who gets into *that class*. Nobody approves people into the app.
- **Any verified user can use the app.** Auth0 email verification is the only gate on signup. The backend's `403 email_not_verified` in `backend/app/accounts.py` stays as it is. So does `403 inactive_account`, which Admins use to deactivate an account by hand.
- **A class only gates class things:** its roster, the sessions run for it and (later) its private quizzes. Open sessions with a six-digit code keep working exactly as in the MVP.

Out of scope: LMS/roster imports, grading, semester statistics (see [ROADMAP §5](ROADMAP.md#5-after-the-mvp)).

## 2. Concepts and roles

| Concept | Meaning |
|---|---|
| **Class** | A named group, for example "CS 440 · Fall 26". Stored in the existing `course_group` table. |
| **Owner** | The teacher who created the class (`course_group.teacher_id`). There's exactly one. They can't be removed, only replaced by an Admin. |
| **Teacher** | A class membership with role `TEACHER`. The owner is one, and co-teachers (a second professor, a TA) are others. |
| **Student** | A class membership with role `STUDENT`. Its status is `PENDING` until a teacher approves it. |
| **Admin** | The existing app-wide Admin (`account_type = 'ADMINISTRATOR'`). Can do anything a teacher can in any class. |

### Teacher is a per-class role, not an account type

We recommend storing "teacher" on the **class membership**, not as a global `PROFESSOR` account type.

- **A global professor type brings back app-wide approval.** Someone would have to decide who is a professor, and that is exactly the queue we just dropped.
- **People are both.** A TA teaches CS 111 and takes CS 440. A per-class role handles that, and a global type can't.
- **The checks stay local.** "Can this person approve students for class 12?" is one query on one row. It doesn't depend on a global flag that has to be kept in sync.
- **It fits the MVP.** USER and ADMIN stay the only app-wide roles (`effective_role` in `backend/app/models/account.py`). Host and participant stay modes. Teacher and student become modes *within a class*.

The `STUDENT` / `PROFESSOR` values in `account.account_type` stay unused. We don't read them for permissions. (See open question 2.)

## 3. Flows

### Teacher creates a class

1. A User creates a class with a name. They become its owner, with an `ACTIVE` `TEACHER` membership.
2. The server generates a **class code**: 8 characters with no look-alikes (no `0 O 1 I L`), for example `K7RM-Q4XP`. Session codes are six digits, so the one Join box can tell the two apart.
3. The **invite link** is the code in a URL: `/join/class/K7RM-Q4XP`. It isn't a separate secret.
4. The teacher can **rotate** the code, which kills the old code and link, or **close joining**. Neither affects existing members.

### Student asks to join

1. The student enters the code or opens the link. They have to be logged in with a verified email, as for anything else.
2. The server creates a `PENDING` `STUDENT` membership. The student sees "Waiting for approval" for that class.
3. **Optional auto-admit by email domain.** If the class sets `auto_admit_domain = 'gettysburg.edu'` and the student's verified email ends in exactly `@gettysburg.edu`, the membership is `ACTIVE` right away. The match is exact and lowercased, with no subdomains. Anyone else still goes to `PENDING`. Setting a domain doesn't replace the code: you need both.

### Teacher approves or rejects

1. Teachers see a **Pending** list with each student's display name, email and when they asked. The email lets the teacher check who it really is, since display names can be anything.
2. **Approve** sets the membership to `ACTIVE`. **Reject** sets it to `REJECTED`. Both record `decided_by_id` and `decided_at`. There's also an "Approve all" button.
3. If two teachers act on the same request, the first one wins. The second gets `409 membership_not_pending`.

### Leaving and removal

- **Leave:** a student or co-teacher removes themselves. Status becomes `LEFT`. The owner can't leave (they can archive the class instead).
- **Remove:** a teacher removes a student, or the owner removes a co-teacher. Status becomes `REMOVED`, with `decided_by_id` recorded.
- **Rejoining:** someone who `LEFT` can use the code again and goes back to `PENDING`. Someone who was `REJECTED` or `REMOVED` can also ask again and goes back to `PENDING`, so the teacher can just ignore them. (See open question 3.)
- **Results don't move.** Past `session_participant`, `response` and `result` rows stay. A removed student can still see their own past results, and the host can still see theirs.

### What each status can see

| Status | Sees | Doesn't see |
|---|---|---|
| Not a member | Nothing about the class, except its name after entering a valid code | Everything else |
| `PENDING` | Class name, owner's name, "Waiting for approval", a Cancel button | Roster, the class's quizzes and sessions, results |
| `REJECTED` / `REMOVED` | "You're not in this class", and a button to ask again | Same as above |
| `ACTIVE` student | Class name, teachers, the class's sessions they can join, their own results | Other students' results, the pending list |
| `ACTIVE` teacher | Everything about the class: roster, pending list, settings, everyone's results for class sessions | n/a |

### Class sessions vs open sessions

- **Open session (MVP, unchanged):** `live_session.group_id` is `NULL`. Anyone logged in who has the six-digit code can join.
- **Class session:** the host picks a class when starting it, so `group_id` is set. Joining needs the code **and** an `ACTIVE` membership in that class. Otherwise the answer is `403 not_class_member`. A pending student gets the same 403. The UI shows them "Waiting for approval" instead.
- **Who can start a class session:** an `ACTIVE` teacher of that class who is also the quiz's author (the MVP rule that only the author hosts still holds). An Admin can always start one.
- Membership is checked **when someone joins**. If a student is removed in the middle of a session, they keep playing that session but can't join the next one. (See open question 5.)

## 4. Data model

We reuse the tables `0001` already created (`course_group`, `group_membership`) and `quiz_group` from `0002` instead of adding new ones. The MVP doesn't use them, so they're empty. Proposed migration `0006_class_membership` (number and names are Ulugbek's call):

```sql
-- Proposal only. Not a migration file.
ALTER TABLE course_group
    ADD COLUMN join_code          CHAR(8)      NULL,
    ADD COLUMN joining_open       BOOLEAN      NOT NULL DEFAULT TRUE,
    ADD COLUMN auto_admit_domain  VARCHAR(255) NULL,   -- e.g. 'gettysburg.edu'; NULL = off
    ADD COLUMN archived_at        DATETIME(3)  NULL,
    ADD CONSTRAINT uq_course_group_join_code UNIQUE (join_code);

ALTER TABLE group_membership
    ADD COLUMN role           ENUM('TEACHER', 'STUDENT') NOT NULL DEFAULT 'STUDENT',
    ADD COLUMN status         ENUM('PENDING', 'ACTIVE', 'REJECTED', 'REMOVED', 'LEFT')
                              NOT NULL DEFAULT 'PENDING',
    ADD COLUMN joined_via     ENUM('CODE', 'DOMAIN', 'CREATOR', 'ADDED') NOT NULL DEFAULT 'CODE',
    ADD COLUMN decided_by_id  INT UNSIGNED NULL,       -- who approved/rejected/removed
    ADD COLUMN decided_at     DATETIME(3)  NULL,
    ADD COLUMN updated_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                              ON UPDATE CURRENT_TIMESTAMP(3),
    ADD CONSTRAINT fk_group_membership_decided_by
        FOREIGN KEY (decided_by_id) REFERENCES account (account_id) ON DELETE SET NULL;

-- "My classes" and "pending requests for class X".
CREATE INDEX idx_group_membership_account ON group_membership (account_id, status);
CREATE INDEX idx_group_membership_status  ON group_membership (group_id, status, role);
```

| Rule | How |
|---|---|
| One membership per person per class | The existing primary key `(group_id, account_id)`. Asking again updates the row instead of adding one. |
| Owner is always an active teacher | Backend: creating a class inserts both the `course_group` row and the owner's `TEACHER`/`ACTIVE` membership in one transaction. Owner can't be removed or leave. |
| Codes are unique | `uq_course_group_join_code`. `NULL` means no code (joining off, or the class is archived). |
| `joined_at` | It keeps its current default, so it means "when the row was first created" (the first request). `decided_at` is when it last changed status. |
| Audit | `decided_by_id` + `decided_at` record the most recent decision. Phase 2 adds an append-only `group_membership_event` table (`group_id, account_id, from_status, to_status, actor_id, at`) for the full history. |

How it connects to what already exists:

- **`live_session.group_id`** (made nullable in `0005`) is set for class sessions and stays `NULL` for open ones. Nothing changes in the MVP.
- **`quiz_group`** links a quiz to classes. This is the dashboard's "Publish to…" menu. Phase 1 uses it only to list "this class's quizzes". Private-quiz visibility comes later.
- **`course_group.teacher_id`** stays as the owner. Co-teachers live only in `group_membership`.

## 5. API

All routes need `get_active_account` (logged in, email verified, not deactivated). "Teacher" below means an `ACTIVE` `TEACHER` membership in that class, and Admin passes every teacher check.

| Method & path | Who | What |
|---|---|---|
| `POST /classes` | Any user | Create a class. Body `{name}`. Returns the class with its code. |
| `GET /classes` | Any user | My classes, each with my `role` and `status` (pending ones included). |
| `GET /classes/{id}` | Any member | Class details. How much it shows depends on status (see §3). |
| `PATCH /classes/{id}` | Teacher | `{name?, joining_open?, auto_admit_domain?}` |
| `POST /classes/{id}/code` | Teacher | Rotate the join code. |
| `POST /classes/{id}/archive` | Owner | Archive: clears the code, closes joining, keeps history. |
| `POST /classes/join` | Any user | Body `{code}`. Returns my membership (`PENDING` or `ACTIVE`). |
| `DELETE /classes/{id}/membership` | Member (not owner) | Leave, or cancel my pending request. |
| `GET /classes/{id}/members?status=PENDING` | Teacher | Roster or pending list. |
| `POST /classes/{id}/members/{account_id}/approve` | Teacher | `PENDING` to `ACTIVE`. |
| `POST /classes/{id}/members/{account_id}/reject` | Teacher | `PENDING` to `REJECTED`. |
| `POST /classes/{id}/members/approve` | Teacher | Body `{account_ids: [...]}`. Approve several at once. |
| `DELETE /classes/{id}/members/{account_id}` | Teacher (students), owner (co-teachers) | Remove (`REMOVED`). |
| `POST /classes/{id}/teachers` | Owner | Body `{email}`. Add an existing account as a co-teacher. Phase 2. |
| `POST /quizzes/{quiz_id}/sessions` | Quiz author | Existing route. Takes an optional `{group_id}`. If it's set, the host must be a teacher of that class. |
| `POST /sessions/join` | Any user | Existing route. If the session has a `group_id`, the joiner must be an active member. |

Errors use the existing `{"error": {"code", "message"}}` shape (`backend/app/errors.py`):

| Status | Code | When |
|---|---|---|
| 403 | `email_not_verified` | Existing. Unverified login, for every route. |
| 403 | `inactive_account` | Existing. Account deactivated by an Admin. |
| 404 | `class_not_found` | No such class, **or the caller isn't a member**. We don't confirm that a class exists to people outside it. |
| 404 | `class_code_not_found` | Wrong, rotated or archived code. |
| 403 | `class_joining_closed` | The teacher closed joining. |
| 403 | `not_class_teacher` | A member who isn't a teacher tries a teacher action. |
| 403 | `not_class_member` | Joining or starting a class session without an active membership. |
| 409 | `already_class_member` | `POST /classes/join` when already `ACTIVE`. |
| 409 | `class_request_pending` | `POST /classes/join` when already `PENDING`. The frontend shows this as "still waiting", not as an error. |
| 409 | `membership_not_pending` | Approving or rejecting a request that is no longer `PENDING` (another teacher got there first). |
| 409 | `cannot_remove_owner` | Removing the owner, or the owner trying to leave. |
| 422 | `invalid_class_domain` | `auto_admit_domain` isn't a plain domain. |

## 6. Authorization and security

- **There's no app-wide approval.** Verified email is the only gate to the app. Don't add a "pending account" state to `account` (that was #39).
- **Check every rule on the server.** Role and status always come from `group_membership`, never from the request or the client. Hiding a button in the UI isn't a permission check.
- **Use one helper per rule**, for example `require_class_teacher(db, account, group_id)` and `require_class_member(...)`, instead of copying the checks into each route. This is the "authorization helpers" item in ROADMAP §5.
- **Make state changes atomic.** Approve is `UPDATE … SET status='ACTIVE' WHERE group_id=? AND account_id=? AND status='PENDING'`. If no row changed, return `409 membership_not_pending`. Then two teachers, or a double click, can't both decide.
- **Domain auto-admit relies on the verified email.** It's only safe because `email_not_verified` blocks unverified logins. Compare the domain exactly and lowercased, and never use a suffix match (`evilgettysburg.edu`).
- **Codes:** 8 characters from a 31-character alphabet gives about 850 billion options. Rate-limit `POST /classes/join` per account so codes can't be guessed. Teachers rotate the code if it leaks, and a leaked code only lets people *ask*.
- **Audit:** every approve, reject and remove stores `decided_by_id` and `decided_at`. An Admin acting on a class is recorded as that Admin.
- **Privacy:** only teachers see the roster and the pending emails. Students don't see each other in phase 1.

## 7. UI sketch

Follows `taha/DESIGN-GUIDE.md`: same header + `.frame` + scrolling `.list` skeleton, phone (390px) first.

- **Dashboard:** add a third tab, **Classes**, after Present and Participate. Each row shows the class name, my role tag (`TEACHER` navy / `STUDENT` sky) and, for teachers, the pending count as an orange badge (orange = key number).
- **Join box:** the existing Join panel takes both kinds of code. Six digits goes to a session lobby, and an 8-character code like `K7RM-Q4XP` goes to "Ask to join *CS 440 · Fall 26*?" → **Ask to join**.
- **Class page (teacher):** a big join code in Archivo Black with **Copy link** and **New code**. Inner tabs: **Pending · Students · Teachers · Settings**.
  - *Pending:* rows with name, email and "asked 2h ago", each with **Approve** (navy, primary) and **Reject** (sky, secondary). An **Approve all** button sits in the toolbar. On phones the buttons sit under the name, full width.
  - *Settings:* class name, a "Joining open" toggle, the auto-admit domain field and Archive.
- **Class page (student), pending:** one bordered card saying "Waiting for approval from *Prof. Name*", with **Check again** and **Cancel request**. It's like #39's waiting screen, but scoped to one class, so the rest of the app works.
- **Present tab:** the row menu's "Publish to…" list (`CLASSES` in the mockup, `classes` in `frontend/src/data/dashboardDemo.js`) becomes the classes where I'm an active teacher. Starting a session gets a "For class: (none) / CS 440 …" picker.
- **Participate tab:** a class session I'm not approved for shows as locked, labeled "Waiting for approval".

## 8. Open questions

1. **Who can create a class?** We propose any user, the same way anyone can make a quiz. The alternative is an Admin-granted "can teach" flag, which partly brings back app-wide approval.
2. **What happens to `account_type` STUDENT/PROFESSOR?** We propose leaving the values in the enum but never reading them. Should a later migration drop them?
3. **Rejected students asking again:** do we allow it freely (proposed), limit how often, or add a teacher-side "block" status?
4. **Co-teachers and quizzes:** can a co-teacher host a quiz the owner wrote for the class? That depends on `quiz_collaborator` and quiz editing, which are also after the MVP.
5. **Removal in the middle of a session:** let them finish (proposed), or kick them from the live session over WebSocket?
6. **Notifications:** we have no email sender (the reason for #39). Is an in-app pending badge enough, or do we set up an Auth0/SMTP provider?
7. **Schema details for Ulugbek:** the migration number, reusing `group_membership` vs a new table, and what `joined_at` means.

## 9. Phased rollout

| Phase | What ships |
|---|---|
| **MVP (now)** | Nothing new. Email verification only, every session is open, `group_id` stays `NULL`. Close #39. |
| **MVP+1** | Migration `0006`. Create and archive a class, code and invite link, ask to join, approve/reject (single and bulk), leave/remove, owner + Admin override, `decided_by` audit, rate limiting on join, class-gated sessions, Classes tab and pending screens. |
| **Phase 2** | Co-teachers, email-domain auto-admit, the `group_membership_event` history table, in-app notifications. |
| **Later** | Private quizzes through `quiz_group`, per-class results and semester statistics, transferring ownership, roster import, Admin dashboard views of classes. |
