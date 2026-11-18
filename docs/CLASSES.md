# Classes: how they work

What the class features do today, and where the code for each one lives. The design and the reasons behind it are in [CLASS_APPROVAL.md](CLASS_APPROVAL.md). Request and response details are in [API.md](API.md).

## 1. Concepts

- **Class:** a group of people who play quizzes together. Table `class` (migration `0006_classes`).
- **Membership:** one `class_membership` row per person per class, with a `role` (`ORGANIZER` or `MEMBER`) and a `status` (`INVITED`, `ACTIVE`, `LEFT`, `REMOVED`, `REQUESTED` or `REJECTED`). Only `ACTIVE` rows count for anything. In the app, `MEMBER`s are called **students**.
- **Organizer:** an active faculty member with the `ORGANIZER` role. Organizers manage the class and can host any approved quiz in it. Faculty status alone gives no access to a class.
- **Class session:** every session belongs to a class through `live_session.class_id` (migration `0007_session_class`). Only active members of that class can join or answer, even if they have the code. There are no open sessions any more.
- **Old sessions with no class:** sessions from before V3 may have `class_id = NULL`. They are read-only history: nobody can join or answer in them.

## 2. Hosting a class session

1. The quiz must belong to the class, and its newest published version must be approved for the class (see the quiz submission and approval endpoints in [API.md](API.md)).
2. The host must be an active member of the class and either the quiz owner or a class organizer. Collaborators can't host just because they collaborate. The class must not be archived.
3. They start the session from the quiz page or from **Class page → My quizzes → Host in this class**. A quiz lives in exactly one class, so there is no class to choose.
4. The frontend sends `POST /classes/{class_id}/quizzes/{quiz_id}/sessions` with no body.

Code:
- `frontend/src/authenticated-demo/HostQuizButton.jsx`: the start request.
- `backend/app/services/sessions.py` `create_session`.
- `require_approved_quiz_version` in `backend/app/services/quiz_submissions.py`.

## 3. The Live button

While a class has a session in `LOBBY` or `ACTIVE`, its class page shows one wide orange **LIVE** bar per session at the top. The bar shows the quiz title and where the game is:

| Session state | Subtext |
|---|---|
| `LOBBY`, or `ACTIVE` before Q1 opens | Join lobby |
| `ACTIVE`, question *n* | Join @ Q*n* |
| The caller is the host | Return to hosting |

- **Tapping it** joins with `POST /sessions/{session_id}/join` (no code) and opens the play screen. Someone who has already joined goes straight in, and the host goes back to the host screen.
- **Updates:** the page polls `GET /classes/{class_id}/active-sessions` every 5 seconds, and again whenever the tab regains focus. There's no class-wide WebSocket; the game itself still uses the session's socket.
- **Motion:** the dot pulses. With `prefers-reduced-motion` it stays still.

Code:
- `frontend/src/classes/ClassLiveButton.jsx`, with the `.cl-live*` styles in `frontend/src/classes/classes.css`.
- `list_class_active_sessions` and `join_session_by_id` in `backend/app/services/sessions.py`.

## 4. Who can do what in a class session

Checked on the server every time. Hiding a button in the UI is not a permission check.

| Action | Rule | Failure |
|---|---|---|
| Start | Active member who owns the quiz or organizes the class; quiz in this class and approved; class not archived | `404 class_not_found`, `404 quiz_not_found`, `403 session_host_denied`, `409 quiz_version_not_approved`, `409 class_archived` |
| Join by code | Active member | `403 not_class_member` |
| Join by id (Live button) | Active member | `404 session_not_found` |
| Answer | Still an active member | `403 not_class_member` |
| WebSocket | Still an active member, host included | close `4403 not_class_member` on connect, and right away for an open socket when an organizer removes the person from the class |

A member (or host) removed mid-game has their live socket closed with `4403` and can't reconnect, rejoin or answer. They are marked as left in the class's running sessions: the host sees the smaller participant count, and they stop counting toward an open question, so it can still close when everyone else has answered. Timing, late join, scoring and duplicate-answer rules are the same as before classes ([LIVE_PROTOCOL.md](LIVE_PROTOCOL.md)).

Code: `backend/app/services/class_access.py` (`may_play`, `require_session_class_member`).

## 5. Joining and leaving

- **By code:** on **Classes → Join**, the student types the code an organizer gave them (`ABCD-2345`; the dash and case don't matter). That calls `POST /classes/join` and creates a **join request**: the student sees "Waiting for approval" until an organizer accepts or rejects it under **Approvals → Students** (one at a time or **Accept all**). The student gets an email either way.
- **By link:** an organizer can share `/app/join/class/ABCD-2345`. Opening it sends the same join request. Signed-out visitors sign in first and come back to the link.
- **By + Add student:** organizers add one person, picking from names and emails of every QuizBurg account as they type. Someone with an account is a student right away (the professor's rule: there is no invitation to accept) and gets a "You've been added" email.
- **By roster:** **+ Add student → Import roster** takes the registrar's class list (CSV or `.xlsx`: `ID`, `Name` as `Last,First`, ...). A preview shows what will happen first. Rows with an email are matched to accounts by that email: those students are added straight away and emailed, and anyone not signed up yet is emailed and added as soon as they sign up with that address. The registrar's usual export has no emails, so its rows are only matched by name as a hint ("Same name as …") and those students' code joins wait for an organizer. Details in [API.md](API.md#rosters-and-join-requests).
- **Skipping the queue:** a code join is approved at once when the person has a pending invite or matches the imported roster by email. A name match isn't enough, since anyone can change their profile name; the organizer sees it as a hint on the request.
- **Who can't join:** turning the code off, or archiving the class, stops new joins. Someone an organizer removed can't come back with the code; they need a new invite.
- **Removal:** students cannot leave a class themselves. An organizer removes them with **Remove from class** on the student's full report (**Students → the student's name**), which preserves their historical results and immediately removes access.
- **Rate limit:** each account gets 10 join attempts a minute, counted in memory per server process.

Code: `join_class` and `leave_class` in `backend/app/services/classes.py`; rosters, join requests and suggestions in `backend/app/services/class_roster.py`; emails in `backend/app/emails.py`; `frontend/src/classes/ClassesPage.jsx`, `frontend/src/classes/JoinClassPage.jsx`.

## 6. History, reports and grades

Every number below comes from the class's **completed** sessions (`live_session.class_id` set, status `COMPLETED`), using each player's final `result` row. Open sessions never show up in a class, and neither do sessions the host moved to the trash (section 7).

| Where | Who | What |
|---|---|---|
| Summary bar (Admin view) | Organizers | Students, presentations, class average (mean of student averages), attendance (mean of student attendance) |
| **Presentations** tab | Organizers | Each session: date, quiz, attendance (players / students), average, top score, and a link to the full report when the viewer hosted it |
| **Students** tab | Organizers | Each student ranked by average: last five scores (dotted dash = absent), average, attendance, total points |
| **Reports** tab | Everyone | Each session with the viewer's own score and rank, and a link to their results |
| **Export grades** | Organizers | CSV gradebook: a row per student, a column per session, and the totals |

- **Members never see classmates' scores.** For them the class-wide fields come back null.
- **Who counts as a student:** active members with the `MEMBER` role. Organizers aren't graded.
- **Attendance** is sessions played divided by the class's completed sessions.
- **Report links:** the per-session report (`/app/results/host/:id`) is limited to the host and Admins, the same rule as before classes. A co-organizer who didn't host sees "Hosted by …" instead of a link.

**Class average formula.** Used by the dashboard, the Students tab and the student report:
1. A student's average is their total points divided by the completed sessions they played. Missed sessions are left out, not counted as 0. Attendance covers those.
2. The class average is the mean of those student averages, over students who played at least once. Each student counts once, however often they played.

**Detailed reports.** Organizers can open a full report for one session, one quiz (every time it was presented), or one student. Members can open the same reports but only see their own rows. See "Detailed class reports" in [API.md](API.md). Code: `backend/app/services/class_reports.py`.

**Excel exports.** Each detailed report has an **Export Excel** button that downloads the same data as a workbook. The session and quiz exports are for organizers. A member can export only their own student report. See "Excel exports of the class reports" in [API.md](API.md). Code: `backend/app/services/class_exports.py`.

Code: `backend/app/services/class_dashboard.py` and the report tables in `frontend/src/classes/ClassPage.jsx`.

## 7. Semesters, archiving and the trash

- **Semesters:** a class has an optional semester label ("Fall 2026"), set when it's created or with **✎ Edit** next to the class name. The same course in a new semester is a new class with its own code, roster and grades: on the old class, **More → New semester…** opens a form with the name filled in and the next semester suggested. The class list and class page show the semester next to the name.
- **Archiving:** **More → Archive class…** asks the organizer to type the class name first, so it can't be pressed by accident. An archived class keeps its reports and grades but stops its code, new joins, new quizzes and new sessions. It gets its own grayed-out look: the **Archived classes** filter on the class list (the other filters show active classes only), a gray card, and a gray class page with an "Archived" banner.
- **Unarchiving:** the banner's **Unarchive class** button (or **More → Unarchive class…**) makes the class active again with a new code. Joining is open; code joins still wait for an organizer.
- **The trash:** "deleting" moves something to the trash, where it can be restored from **Classes → Trash**. Nothing is really deleted.
  - A **class** (organizers: **More → Move to trash…**) disappears for everyone, with its quizzes and reports, until an organizer restores it.
  - A **quiz** (its owner: the quiz page's **More → Move to trash…**) leaves the class's lists and approval queue.
  - A **hosted session** (its host: **Delete** on a row of the quiz's **Hosting history**) leaves the hosting history, the students' "quizzes taken", and the class's reports, attendance and grades. That's how a session hosted by mistake stops counting.
  - Something running live can't be trashed; end it first.

Code: `backend/app/services/trash.py` (and the `deleted_at` filters it lists), `unarchive_class` in `backend/app/services/classes.py`; `frontend/src/classes/ClassLifecycle.jsx`, `TrashPanel.jsx` and `frontend/src/authenticated-demo/MoreMenu.jsx`.

## 8. Deploying

Migration `0007_session_class` must be applied to the production database before the new backend starts, and so must `0016_class_roster` (join requests and rosters) and `0017_trash_and_semester` (the trash and semesters). Apply it the same way as earlier migrations (`ulugbek-err/migrations/README.md`), then redeploy as described in [DEPLOYMENT.md](DEPLOYMENT.md):

```bash
docker compose --env-file deploy/.env up --build -d
```

Older frontends can't start sessions any more: `POST /quizzes/{quiz_id}/sessions` was removed in V3 Task 5. Deploy the frontend together with the backend.
