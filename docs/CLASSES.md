# Classes: how they work

What the class features do today, and where the code for each one lives. The design and the reasons behind it are in [CLASS_APPROVAL.md](CLASS_APPROVAL.md). Request and response details are in [API.md](API.md).

## 1. Concepts

- **Class:** a group of people who play quizzes together. Table `class` (migration `0006_classes`).
- **Membership:** one `class_membership` row per person per class, with a `role` (`ORGANIZER` or `MEMBER`) and a `status` (`INVITED`, `ACTIVE`, `LEFT` or `REMOVED`). Only `ACTIVE` rows count for anything.
- **Organizer:** an active member with the `ORGANIZER` role. Organizers manage the class and host its sessions. An Admin passes every organizer check.
- **Open session:** `live_session.class_id` is `NULL`. Anyone signed in who has the six-digit code can join. This is how every session worked before classes.
- **Class session:** `live_session.class_id` is set (migration `0007_session_class`). Only active members of that class can join or answer, even if they have the code.

## 2. Hosting a class session

1. The host must be the quiz's author **and** an active organizer of the class (or an Admin). The class must not be archived.
2. They start the session in one of two places:
   - **Dashboard → Present → ⋯ on a quiz.** A **For** menu offers *Open session* plus every class the caller organizes. This menu only appears for people who organize at least one class.
   - **Class page → Present tab → Host in this class.** The class is preset.
3. The frontend sends `POST /quizzes/{quiz_id}/sessions` with `{"class_id": …}`, or with no body for an open session.

Code:
- `frontend/src/authenticated-demo/HostQuizButton.jsx`: the For menu and the start request.
- `backend/app/services/sessions.py` `create_session`.
- `require_class_host` in `backend/app/services/class_authorization.py`.

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
| Start | Quiz author and organizer/Admin, class not archived | `403 not_class_organizer`, `409 class_archived` |
| Join by code | Active member | `403 not_class_member` |
| Join by id (Live button) | Active member, and the session must be a class session | `404 session_not_found` |
| Answer | Still an active member | `403 not_class_member` |
| WebSocket | Still an active member | close `4403 not_class_member` |

A member removed mid-game is refused on their next answer and can't rejoin. Timing, late join, scoring and duplicate-answer rules are the same as for open sessions ([LIVE_PROTOCOL.md](LIVE_PROTOCOL.md)).

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

Code: `backend/app/services/class_dashboard.py` and the report tables in `frontend/src/classes/ClassPage.jsx`.

## 7. Deploying

Migration `0007_session_class` must be applied to the production database before the new backend starts. Nothing after 0007 needs a migration. Apply it the same way as earlier migrations (`ulugbek-err/migrations/README.md`), then redeploy as described in [DEPLOYMENT.md](DEPLOYMENT.md):

```bash
docker compose --env-file deploy/.env up --build -d
```

Older frontends keep working: they send no body when starting a session, which still creates an open session.
