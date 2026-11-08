# Classes: how they work

What the class features do today, and where the code for each one lives. The design and the reasons behind it are in [CLASS_APPROVAL.md](CLASS_APPROVAL.md). Request and response details are in [API.md](API.md).

## 1. Concepts

- **Class:** a group of people who play quizzes together. Table `class` (migration `0006_classes`).
- **Membership:** one `class_membership` row per person per class, with a `role` (`ORGANIZER` or `MEMBER`) and a `status` (`INVITED`, `ACTIVE`, `LEFT` or `REMOVED`). Only `ACTIVE` rows count for anything.
- **Organizer:** an active faculty member with the `ORGANIZER` role. Organizers manage the class and can host any approved quiz in it. Faculty status alone gives no access to a class.
- **Class session:** every session belongs to a class through `live_session.class_id` (migration `0007_session_class`). Only active members of that class can join or answer, even if they have the code. There are no open sessions any more.
- **Old sessions with no class:** sessions from before V3 may have `class_id = NULL`. They are read-only history: nobody can join or answer in them.

## 2. Hosting a class session

1. The quiz must belong to the class, and its newest published version must be approved for the class (see the quiz submission and approval endpoints in [API.md](API.md)).
2. The host must be an active member of the class and either the quiz owner or a class organizer. Collaborators can't host just because they collaborate. The class must not be archived.
3. They start the session from the quiz page or from **Class page → Present tab → Host in this class**. A quiz lives in exactly one class, so there is no class to choose.
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
| WebSocket | Still an active member | close `4403 not_class_member` |

A member removed mid-game is refused on their next answer and can't rejoin. Timing, late join, scoring and duplicate-answer rules are the same as before classes ([LIVE_PROTOCOL.md](LIVE_PROTOCOL.md)).

Code: `backend/app/services/class_access.py` (`may_play`, `require_session_class_member`).

## 5. Joining and leaving

- **By code:** on **Classes → Join**, the member types the code an organizer gave them (`ABCD-2345`; the dash and case don't matter). That calls `POST /classes/join`.
- **By link:** an organizer can share `/app/join/class/ABCD-2345` (shown in **Settings → Class code**). Opening it joins straight away. Signed-out visitors sign in first and come back to the link.
- **By invite:** organizers can still invite by email from **Members**.
- **Who can't join:** turning the code off, or archiving the class, stops new joins. Someone an organizer removed can't come back with the code; they need a new invite.
- **Leaving:** the User view of a class has a **Leave class** button (`DELETE /classes/{id}/membership`). The last organizer can't leave.
- **Rate limit:** each account gets 10 join attempts a minute, counted in memory per server process.

Code: `join_class` and `leave_class` in `backend/app/services/classes.py`, `frontend/src/classes/ClassesPage.jsx`, `frontend/src/classes/JoinClassPage.jsx`.

## 6. History, reports and grades

Every number below comes from the class's **completed** sessions (`live_session.class_id` set, status `COMPLETED`), using each player's final `result` row. Open sessions never show up in a class.

| Where | Who | What |
|---|---|---|
| Summary bar (Admin view) | Organizers | Students, presentations, class average (mean of student averages), attendance (mean of student attendance) |
| **Presentations** tab | Organizers | Each session: date, quiz, attendance (players / students), average, top score, and a link to the full report when the viewer hosted it |
| **Students** tab | Organizers | Each student ranked by average: last five scores (dotted dash = absent), average, attendance, total points |
| **Participate** tab | Everyone | Each session with the viewer's own score and rank, and a link to their results |
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

## 7. Deploying

Migration `0007_session_class` must be applied to the production database before the new backend starts. Nothing after 0007 needs a migration. Apply it the same way as earlier migrations (`ulugbek-err/migrations/README.md`), then redeploy as described in [DEPLOYMENT.md](DEPLOYMENT.md):

```bash
docker compose --env-file deploy/.env up --build -d
```

Older frontends can't start sessions any more: `POST /quizzes/{quiz_id}/sessions` was removed in V3 Task 5. Deploy the frontend together with the backend.
