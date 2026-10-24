# Classes (after the MVP)

A proposal for how classes should work once we add them. **Nothing here is built yet, and none of it is in the MVP.** The schema changes are proposals for Ulugbek, who owns the database files. This doc adds no migration.

This replaces two earlier ideas:

- **#39 (closed):** an app-wide "approve this signup" queue. The team dropped it on 2026-10-14.
- **The first version of this doc:** per-class *teachers* who approved *students* one by one. We dropped teachers and approval. Anyone can make a class, and a class code lets you in right away.

## 1. Goal and scope

- **A class is a group of people who play quizzes together**, like a Google Classroom class. The people who run it are its **organizers**.
- **Any verified user can use the app.** Auth0 email verification is the only gate on signup. The backend's `403 email_not_verified` in `backend/app/accounts.py` stays as it is. So does `403 inactive_account`, which Admins use to deactivate an account by hand.
- **A class only gates class things:** its roster, its live sessions and its past results. Open sessions with a six-digit code keep working exactly as in the MVP.
- **No approval step.** Joining with a class code or accepting an invite makes you a member right away. Organizers control who's in by removing people, changing the code or closing joining.

Out of scope: LMS/roster imports, grading, semester statistics (see [ROADMAP §5](ROADMAP.md#5-after-the-mvp)).

## 2. Roles

There are only two app-wide roles, and there is no teacher role anywhere.

| Who | Scope | Meaning |
|---|---|---|
| **Admin** | App | The existing `account_type = 'ADMINISTRATOR'`. Can see and change anything, including any class. |
| **User** | App | Everyone else. Can make quizzes, make classes, host sessions and play in them. |
| **Organizer** | One class | Runs that class: invites and removes people, manages the codes and hosts its sessions. Whoever creates the class is its first organizer. A class can have several organizers and always has at least one. |
| **Member** | One class | Belongs to the class. Sees its past quizzes and their own results, and joins its live sessions. |

- **Host** and **participant** stay things a User *does*, not roles (as in the MVP). **Organizer** and **member** are the same idea inside one class. The same person can organize CS 111 and be a member of CS 440.
- "Organizer" is deliberately not "admin". **Admin** always means the app-wide Admin.
- USER and ADMIN stay the only app-wide roles (`effective_role` in `backend/app/models/account.py`). The `STUDENT` / `PROFESSOR` values in `account.account_type` stay unused, and we don't read them for permissions (see open question 6).

## 3. Flows

### Make a class

1. Any user creates a class with a name. They become an `ACTIVE` `ORGANIZER` of it.
2. The server generates a **class code**: 8 characters with no look-alikes (no `0 O 1 I L`), for example `K7RM-Q4XP`. Session codes are six digits, so one Join box can tell the two apart.
3. The **invite link** is the code in a URL: `/join/class/K7RM-Q4XP`. It isn't a separate secret.
4. An organizer can **change the code**, which kills the old code and link, or **close joining**. Neither affects existing members.

### Join a class with its code

1. On the dashboard, the user taps **Join a class** and enters the code, or opens the invite link. They have to be logged in with a verified email, as for anything else.
2. The server creates an `ACTIVE` `MEMBER` membership. There's no waiting step, and the class appears in their list right away.
3. A wrong, changed or archived code gives `404 class_code_not_found`. A class with joining closed gives `403 class_joining_closed`.

### Invite someone

- **In the app (MVP+1):** an organizer types the email of someone who already has an account. That person gets an `INVITED` membership and sees an invite card on their dashboard ("*Prof. Kim* invited you to *CS 440 · Fall 26*") with **Accept** and **Decline**. Accept makes them an `ACTIVE` member, and Decline removes the invite. Inviting works even when joining by code is closed.
- **By email (phase 2):** the same invite, sent as an email with a link. This also covers people who don't have an account yet: the link works after they sign up. It waits until we pick an email provider, because the app can't send email today (the same reason #39 was closed). Until then, organizers can paste the invite link into their own email.

### Organizers

- Any organizer can make a member an organizer, or turn another organizer back into a member.
- A class can't lose its last organizer. That person can't leave or step down until someone else is an organizer (`409 last_organizer`). They can archive the class instead.
- An Admin can do anything an organizer can, in any class. That includes appointing an organizer for a class whose organizers are gone.

### Leaving and removal

- **Leave:** a member or organizer removes themselves. Status becomes `LEFT`. They can join again later with the current code.
- **Remove:** an organizer removes someone. Status becomes `REMOVED`, with `decided_by_id` recorded. A removed person **can't** rejoin with the code. Only a new invite from an organizer lets them back in (see open question 3).
- **Results don't move.** Past `session_participant`, `response` and `result` rows stay. A removed member can still see their own past results, and organizers can still see theirs.

### Two codes, two doors

| Code | Looks like | Gets you into | Who can use it |
|---|---|---|---|
| **Class code** | `K7RM-Q4XP` (8 characters) | The class, as a member | Any verified user, while joining is open |
| **Session code** | `482913` (6 digits) | One live game | Open session: anyone logged in. Class session: active members of that class only. |

Members of a class rarely need the session code. The class page's **Live** button (§5) joins them without it.

### What each status can see

| Status | Sees | Doesn't see |
|---|---|---|
| Not a member | Nothing about the class, except its name after entering a valid code | Everything else |
| `INVITED` | The invite card: class name and who invited them | Roster, sessions, results |
| `LEFT` / `REMOVED` | "You're not in this class" on the class page, and their own past results in their history | The class's sessions, the Live button, other people's results |
| `ACTIVE` member | Class name, organizers, past quizzes, the Live button, their own results | Other members' results and emails |
| `ACTIVE` organizer | Everything about the class: roster, invites, codes, settings, everyone's results | n/a |

## 4. Class sessions vs open sessions

- **Open session (MVP, unchanged):** `live_session.group_id` is `NULL`. Anyone logged in who has the six-digit code can join.
- **Class session:** the host picks a class when starting it ("For: Open / CS 440 · Fall 26"), so `group_id` is set. Joining needs an `ACTIVE` membership in that class, whether by the session code or the Live button. Anyone else gets `403 not_class_member`, **even if they know the code**.
- **Who can start a class session:** an organizer of that class who is also the quiz's author (the MVP rule that only the author hosts still holds). An Admin can always start one. See open question 1 for organizers hosting each other's quizzes.
- **Membership is checked when someone joins and when they submit an answer.** If a member is removed in the middle of a session, their next answer is rejected with `403 not_class_member`, and they can't rejoin.
- **Nothing else about the game changes.** Question timing, the WebSocket protocol, late-join behaviour (someone who joins mid-question plays from the next question), rejection of duplicate and late answers, and the scoring formula all stay as in [`LIVE_PROTOCOL.md`](LIVE_PROTOCOL.md).
- **Six-digit session codes stay** for class sessions too. That keeps today's Join box working, and leaves room to let outsiders into a class session later if we want to.

## 5. The class page and the Live button

When a member opens a class, they see:

1. **The Live button**, only while one of the class's sessions is `LOBBY` or `ACTIVE`.
2. **Past quizzes:** the class's `COMPLETED` sessions, newest first, each with the quiz title, date and their own score. Tapping one opens their results for it.

### The Live button

A wide red button at the top of the class page:

```
┌──────────────────────────────────────────┐
│  ● LIVE   Week 6 Review                  │
│           Join @ Q6                      │
└──────────────────────────────────────────┘
```

- **The dot blinks**, a slow red pulse. With `prefers-reduced-motion` it stays still.
- **The title** is the quiz being played.
- **The subtext says where the game is**, so members know what they're walking into:

| Session state | Subtext |
|---|---|
| `LOBBY` | Join lobby |
| `ACTIVE`, question *n* open, or closed and showing results | Join @ Q*n* |
| `ACTIVE`, but Q1 hasn't opened yet | Join lobby |

- **Tapping it joins the session** with `POST /sessions/{session_id}/join`. The member doesn't type the code. It then opens the live screen. Someone who is already in the session goes straight back to it.
- **It updates by polling.** The page asks `GET /classes/{id}/active-sessions` every few seconds while it's visible, and again when the tab regains focus. Phase 1 has no class-wide WebSocket. The live game itself still uses the session's WebSocket.
- **If a class runs two sessions at once,** each gets its own Live button.
- **On the dashboard,** each class in the Classes list shows a small red dot while it has a live session, so members notice without opening it.

Organizers see the same page, plus the roster, invites, codes and everyone's results (§7).

## 6. Data model

We reuse the tables `0001` already created (`course_group`, `group_membership`) and `quiz_group` from `0002` instead of adding new ones. The MVP doesn't use them, so they're empty. Proposed migration `0006_classes` (number and names are Ulugbek's call):

```sql
-- Proposal only. Not a migration file.
ALTER TABLE course_group
    RENAME COLUMN teacher_id TO created_by_id,          -- there are no teachers any more
    ADD COLUMN join_code      CHAR(8)     NULL,
    ADD COLUMN joining_open   BOOLEAN     NOT NULL DEFAULT TRUE,
    ADD COLUMN archived_at    DATETIME(3) NULL,
    ADD CONSTRAINT uq_course_group_join_code UNIQUE (join_code);

ALTER TABLE group_membership
    ADD COLUMN role           ENUM('ORGANIZER', 'MEMBER') NOT NULL DEFAULT 'MEMBER',
    ADD COLUMN status         ENUM('INVITED', 'ACTIVE', 'LEFT', 'REMOVED')
                              NOT NULL DEFAULT 'ACTIVE',
    ADD COLUMN joined_via     ENUM('CREATOR', 'CODE', 'INVITE') NOT NULL DEFAULT 'CODE',
    ADD COLUMN invited_by_id  INT UNSIGNED NULL,       -- who sent the invite
    ADD COLUMN decided_by_id  INT UNSIGNED NULL,       -- who removed them or changed their role
    ADD COLUMN decided_at     DATETIME(3)  NULL,
    ADD COLUMN updated_at     DATETIME(3)  NOT NULL DEFAULT CURRENT_TIMESTAMP(3)
                              ON UPDATE CURRENT_TIMESTAMP(3),
    ADD CONSTRAINT fk_group_membership_invited_by
        FOREIGN KEY (invited_by_id) REFERENCES account (account_id) ON DELETE SET NULL,
    ADD CONSTRAINT fk_group_membership_decided_by
        FOREIGN KEY (decided_by_id) REFERENCES account (account_id) ON DELETE SET NULL;

-- "My classes" and "the roster / organizers of class X".
CREATE INDEX idx_group_membership_account ON group_membership (account_id, status);
CREATE INDEX idx_group_membership_roster  ON group_membership (group_id, status, role);

-- "Is anything live in class X?" for the Live button.
CREATE INDEX idx_live_session_group_status ON live_session (group_id, status);
```

| Rule | How |
|---|---|
| One membership per person per class | The existing primary key `(group_id, account_id)`. Joining again, being invited again or rejoining updates the row instead of adding one. |
| Creator starts as organizer | Creating a class inserts the `course_group` row and the creator's `ORGANIZER`/`ACTIVE`/`CREATOR` membership in one transaction. |
| At least one organizer | Backend: demoting or removing an organizer, or an organizer leaving, locks the class's organizer rows and refuses if it would leave none (`409 last_organizer`). |
| Codes are unique | `uq_course_group_join_code`. `NULL` means no code (archived class). |
| `joined_at` | Keeps its current default, so it means "when the row was first created". `decided_at` is when it last changed. |
| Audit | `invited_by_id`, `decided_by_id` and `decided_at` record the most recent action. Phase 2 adds an append-only `group_membership_event` table (`group_id, account_id, from_status, to_status, from_role, to_role, actor_id, at`) for the full history. |

How it connects to what already exists:

- **`live_session.group_id`** (made nullable in `0005`) is set for class sessions and stays `NULL` for open ones. Nothing changes in the MVP.
- **`quiz_group`** links a quiz to classes. Phase 1 uses it only for the start-session picker's default ("this quiz is usually played in CS 440"). Private-quiz visibility comes later.
- **The Live button's subtext** comes from data we already have: `live_session.status` plus the highest `session_question.position` that has opened.

## 7. API

All routes need `get_active_account` (logged in, email verified, not deactivated). "Organizer" below means an `ACTIVE` `ORGANIZER` membership in that class, and an Admin passes every organizer check.

### Classes

| Method & path | Who | What |
|---|---|---|
| `POST /classes` | Any user | Create a class. Body `{name}`. Returns the class with its code. |
| `GET /classes` | Any user | My classes, each with my `role`, plus pending invites. Each class says whether it has a live session (for the dashboard dot). |
| `GET /classes/{id}` | Any member | Class details. How much it shows depends on role (see §3). |
| `PATCH /classes/{id}` | Organizer | `{name?, joining_open?}` |
| `POST /classes/{id}/code` | Organizer | Change the join code. |
| `POST /classes/{id}/archive` | Organizer | Archive: clears the code, closes joining, keeps history. |
| `POST /classes/join` | Any user | Body `{code}`. Returns my new `ACTIVE` membership. |
| `DELETE /classes/{id}/membership` | Member or organizer | Leave (not allowed for the last organizer). |

### Roster and invites

| Method & path | Who | What |
|---|---|---|
| `GET /classes/{id}/members` | Organizer | Roster with names, emails, roles and statuses. |
| `PATCH /classes/{id}/members/{account_id}` | Organizer | Body `{role}`. Make someone an organizer or a member. |
| `DELETE /classes/{id}/members/{account_id}` | Organizer | Remove (`REMOVED`). |
| `POST /classes/{id}/invites` | Organizer | Body `{email}`. Invite an existing account. Phase 2 also emails it. |
| `DELETE /classes/{id}/invites/{account_id}` | Organizer | Cancel an invite. |
| `POST /classes/{id}/invite/accept` | The invited user | `INVITED` to `ACTIVE`. |
| `POST /classes/{id}/invite/decline` | The invited user | Drop the invite. |

### Sessions

| Method & path | Who | What |
|---|---|---|
| `POST /quizzes/{quiz_id}/sessions` | Quiz author | Existing route. Takes an optional `{group_id}`. If it's set, the host must be an organizer of that class. |
| `GET /classes/{id}/active-sessions` | Any member | The class's `LOBBY`/`ACTIVE` sessions, each with `session_id`, `quiz_title`, `status`, `current_question_position` (null in the lobby), `question_count` and `join_code`. This is all the Live button needs. |
| `GET /classes/{id}/sessions` | Any member | Past (`COMPLETED`) sessions, newest first. Members get their own score on each, and organizers get the summary. |
| `POST /sessions/{session_id}/join` | Any member | New. The Live button's join, with no code. Same result as joining by code. |
| `POST /sessions/join` | Any user | Existing route, body `{join_code}`. If the session has a `group_id`, the joiner must be an active member. |
| `POST /sessions/{session_id}/questions/{session_question_id}/responses` | Participant | Existing route. For class sessions it also checks that the participant is still an active member. |

### Errors

Errors use the existing `{"error": {"code", "message"}}` shape (`backend/app/errors.py`):

| Status | Code | When |
|---|---|---|
| 403 | `email_not_verified` | Existing. Unverified login, for every route. |
| 403 | `inactive_account` | Existing. Account deactivated by an Admin. |
| 404 | `class_not_found` | No such class, **or the caller isn't a member**. We don't confirm that a class exists to people outside it. |
| 404 | `class_code_not_found` | Wrong, changed or archived code. |
| 404 | `invite_not_found` | Accepting or declining an invite that doesn't exist or was cancelled. |
| 404 | `account_not_found` | Inviting an email that has no account (until email invites exist). |
| 403 | `class_joining_closed` | An organizer closed joining by code. |
| 403 | `class_member_removed` | A removed person tries the class code. Only an invite brings them back. |
| 403 | `not_class_organizer` | A member who isn't an organizer tries an organizer action. |
| 403 | `not_class_member` | Joining a class session, answering in one, or starting one without an active membership. |
| 409 | `already_class_member` | Joining or inviting someone who is already `ACTIVE`. |
| 409 | `last_organizer` | The change would leave the class with no organizer. |

## 8. Authorization and security

- **There's no approval anywhere.** Verified email gets you into the app, and a class code or invite gets you into a class. Don't add a "pending" state to `account` or to `group_membership`.
- **Check every rule on the server.** Role and status always come from `group_membership`, never from the request or the client. Hiding a button in the UI isn't a permission check.
- **Use one helper per rule**, for example `require_class_organizer(db, account, group_id)` and `require_class_member(...)`, instead of copying the checks into each route. This is the "authorization helpers" item in ROADMAP §5. The session join, answer and start-session paths call `require_class_member` / `require_class_organizer` when `group_id` is set.
- **Make state changes atomic.** For example, accepting an invite is `UPDATE … SET status='ACTIVE' WHERE group_id=? AND account_id=? AND status='INVITED'`, and no row changed means `404 invite_not_found`. The last-organizer check locks the organizer rows (`SELECT … FOR UPDATE`) so two organizers can't both step down at once.
- **Class codes now let people in, not just ask.** That makes guessing worth more than in the old design. 8 characters from a 31-character alphabet gives about 850 billion options, which is fine if we **rate-limit `POST /classes/join` per account**. If a code leaks, an organizer changes it and removes anyone who shouldn't be there, or closes joining and uses invites only.
- **Session codes don't bypass classes.** A six-digit code for a class session is useless to non-members, so guessing one only finds open sessions, as today.
- **Audit:** every invite, removal and role change stores who did it and when. An Admin acting on a class is recorded as that Admin.
- **Privacy:** only organizers see the roster's emails. In phase 1, members see the organizers' names but not the other members (see open question 5).

## 9. UI sketch

Follows `taha/DESIGN-GUIDE.md`: same header + `.frame` + scrolling `.list` skeleton, phone (390px) first.

- **Dashboard:** add a third tab, **Classes**, after Present and Participate. It lists my classes, each with the class name, my role tag (`ORGANIZER` navy / `MEMBER` sky) and a small red dot while it has a live session. At the top:
  - a **Join a class** button, which opens a code box;
  - a **New class** button;
  - invite cards with **Accept** (navy, primary) and **Decline** (sky, secondary), above the list.
- **Join box:** the existing Join panel takes both kinds of code. Six digits goes to a session lobby (with `403 not_class_member` shown as "This game is only for members of *CS 440*"). An 8-character code goes straight into the class.
- **Class page (member):** the class name and organizers, the **Live** button from §5 when something is running, then **Past quizzes**.
- **Class page (organizer):** the same, plus inner tabs **Members · Invites · Settings**:
  - a big class code in Archivo Black with **Copy link** and **New code**;
  - *Members:* name, email, role tag, and a row menu with **Make organizer** / **Make member** / **Remove**;
  - *Invites:* an email box with **Invite**, and pending invites with **Cancel**;
  - *Settings:* class name, a "Joining with code" toggle, and Archive.
- **Present tab:** starting a session gets a "For: Open / CS 440 · Fall 26 / …" picker listing the classes I organize. It defaults to the quiz's `quiz_group` class if there is one.
- **Participate tab:** live class sessions I can join show the same red Live treatment as on the class page.

## 10. Open questions

1. **Organizers hosting each other's quizzes:** can any organizer of a class host any quiz shared to that class, or only quizzes they wrote (proposed for phase 1)? This depends on `quiz_collaborator` and quiz editing, which are also after the MVP.
2. **Where a class session gets its class:** the host picks it when starting (proposed), or it's fixed by the quiz through `quiz_group` (one quiz, one class)? Picking is more flexible. Inheriting means the host can't start it in the wrong class.
3. **Removed members:** should they really need an invite to come back (proposed), or can they use the code like anyone who left?
4. **Email provider:** which one (Auth0, an SMTP service, Cloudflare Email), and when? Email invites in phase 2 depend on it.
5. **Can members see each other?** Proposed: no in phase 1, only organizers. A member list for everyone could come later as a class setting.
6. **What happens to `account_type` STUDENT/PROFESSOR?** Proposed: leave the values in the enum but never read them. Should a later migration drop them?
7. **Other organizers playing:** the host can't play their own session (`host_cannot_join`). Should other organizers of the class be able to join it as players? Proposed: yes, they're members too.
8. **Schema details for Ulugbek:** the migration number, renaming `teacher_id`, and what `joined_at` means.

## 11. Phased rollout

| Phase | What ships |
|---|---|
| **MVP (now)** | Nothing new. Email verification only, every session is open, `group_id` stays `NULL`. |
| **MVP+1** | Migration `0006`. Create and archive a class, class code and invite link, instant join, several organizers, in-app invites, leave/remove, Admin override, audit columns, rate limiting on join, class-gated sessions (join and answer checks), the class page with past quizzes and the Live button, the Classes tab. |
| **Phase 2** | Email invites (after picking a provider), the `group_membership_event` history table, in-app notifications. |
| **Later** | Private quizzes through `quiz_group`, class reports and Excel exports, semester statistics, roster import, Admin dashboard views of classes. |
