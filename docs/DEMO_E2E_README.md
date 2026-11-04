# Demo end-to-end test script

A manual, click-by-click test for every feature we show in the demo. Run it top to bottom once before the demo (about 20 minutes), then use the same order live.

- **Build:** `demo/all` (PR #88, commit `fdd9b1d`). This combines #82 (sign-up profile), #84 (header nav), #85 (drafts and Save & publish) and #86 ("Join class" label). Features from other open PRs, such as #87's start countdown, are **not** in this build.
- **Each test lists:** who does it, the steps, what you should see, and what to do if it goes wrong.
- Button names are quoted exactly as they appear in the app.

---

## 0. Automated checks (already run on `fdd9b1d`)

| Check | Command | Result |
|---|---|---|
| Backend unit + MySQL integration tests (all 11 migrations on a fresh MySQL 8) | `cd backend && TEST_DATABASE_URL=… python -m pytest -ra` | **531 passed, 0 skipped** |
| Frontend unit tests | `cd frontend && npm test` | **70 passed** |
| Frontend lint | `npm run lint` | clean |
| Frontend build | `npm run build` | passes; warns that the JS bundle is 662 kB (> 500 kB). Harmless for the demo |
| Live e2e (real server, real sockets, 1 host + 2 players) | `cd frontend && npm run test:e2e` | **2 of 2 FAIL** in setup with `POST /classes -> 403 faculty_required`. See [§Known issues](#known-issues). With the e2e host made an Admin, both pass: join, skip, answer, end, leaderboard, leave, cancel in lobby |
| CI on PR #88 | GitHub Actions | `backend`, `frontend`, `containers` all green |

To run the e2e suite yourself: `cd frontend && npm run test:e2e`. It needs `backend/.venv` (or set `BACKEND_PYTHON`).

---

## 1. Before the demo: setup checklist

1. **Servers.** Start the frontend and backend from the `demo/all` checkout:
   ```bash
   cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8001
   cd frontend && npm run dev
   ```
   Check them: `curl http://127.0.0.1:8001/health` should print `{"status":"ok","components":{"database":"ok"}}`.
   - Don't start the servers from a Claude Code session: they can't reach Auth0, and every sign-in fails with "Invalid token".
   - Make sure nothing else holds port 5173 or 8001: `lsof -nP -iTCP:5173 -sTCP:LISTEN`.
2. **Open the app at `http://localhost:5173`, not `127.0.0.1`.** Vite listens on `localhost` only, CORS only allows `http://localhost:5173`, and Auth0's callback URL is `localhost`.
3. **Database.** The local `quizdb` (Docker, port 3307) must have migrations `0001`–`0011`:
   ```sql
   SELECT version FROM schema_migrations ORDER BY version;   -- last row: 0011_account_profile
   ```
4. **Accounts.** You need three people, each in a **separate browser profile or private window**. Auth0 keeps one session per browser, so two tabs in the same window are the same person.

   | Role in demo | Account | Notes |
   |---|---|---|
   | **Professor** (creates the class, writes the quiz, hosts) | an existing account, promoted to Admin | must be Admin; see step 5 |
   | **Student A** | an existing verified account | joins the class with the code |
   | **Student B** | a brand-new email you control | used for the live sign-up demo |

5. **Make the Professor an Admin.** Only Admins can create classes and run organizer actions (hosting a class session, reports, exports). Nobody can do this from the app. Run it once:
   ```sql
   UPDATE account SET account_type = 'ADMINISTRATOR' WHERE email = 'professor@example.edu';
   ```
   Then reload the app: **+ New class** appears on **Classes** only for Admins.
6. **Test emails.** Student B must be able to open their verification email during the demo. Have the inbox open in that browser profile, and check the spam folder.

---

## 2. Sign-up flow (new user)

**Who:** Student B, in a fresh private window.

1. Open `http://localhost:5173`. The landing page loads.
2. Click **Create an account**. The Auth0 page opens on **Sign up**.
3. Enter Student B's email and a password, then submit.
4. **Expected:** the app shows **Verify email · One more step · Check your inbox**, with Student B's email.
5. In the inbox, open the Auth0 verification email and click the link.
6. Back in the app, click **I've verified, continue**.
7. **Expected:** **Welcome to QuizBurg · Your profile · Last step** appears.

If it goes wrong:
- If it still says *"Still not verified. Check your spam folder."* after you clicked the link, wait a few seconds and click again. The button already fetches a fresh token.
- If Auth0 asks you to sign in again, that's expected when a fresh token needs interaction. Use the same email.
- Any email domain works. There is no `@gettysburg.edu` restriction yet.

## 3. Profile setup

**Who:** Student B, continuing from §2.

1. Fill in **First name** and **Last name**.
2. Pick a preset avatar figure and a **Tile color**.
3. Click **Save and continue**.
4. **Expected:** you land in the app. The header shows "First Last" and the avatar.
5. Open the avatar menu → **Edit profile**, change something, and save. The header updates.
6. Avatar menu → **Sign out**, then sign back in. The profile screen does **not** come back.

## 4. Header navigation

**Who:** anyone signed in.

- The header shows **Dashboard · Classes · Join game**, and each one opens its page.
- The QuizBurg logo goes to **Classes**.
- Check at phone width too: in DevTools, toggle the device toolbar to 390 px. There should be no sideways scrolling.

## 5. Create a class

**Who:** Professor (an Admin).

1. **Classes** → **+ New class** → type a name (e.g. "CS 440 Demo") → **Create class →**.
2. **Expected:** the class page opens in **Admin** view, with a **Code XXXX-XXXX** chip. Click it to copy the code.
3. The tabs read **Presentations · Quizzes · Students · Members · Settings**.

If it goes wrong: if **+ New class** is missing, the account isn't an Admin (see §1 step 5). The API returns `403 faculty_required`.

## 6. Join the class

**Who:** Student A and Student B.

Join with the code:
1. **Classes** → **Join class** → type the code (e.g. `ABCD-2345`; case and the dash don't matter) → **Join class →**.
2. **Expected:** the class opens in the member view, with tabs **Present · Participate**, plus **+ New quiz**, **My class report** and **Leave class**.

Join with the link (show this with Student B):
1. Open `http://localhost:5173/app/join/class/ABCD-2345`. The link is under **Settings → Class code**.
2. **Expected:** Student B joins straight away. A signed-out visitor signs in first and then comes back to the link.

Professor check: **Members** now lists both students as **Member**.

If it goes wrong: each account gets 10 join attempts a minute. Someone an organizer removed can't rejoin with the code; they need a new invite.

## 7. Members and settings (optional)

**Who:** Professor.

- **Members** → **Invite a member** by email. The invite shows under **Pending invitations**.
- **Make organizer** / **Make member** on a row, and **Remove** a member.
- **Settings** → **Generate code** (the old code stops working), or untick **Class code enabled** to stop new joins.
- **Don't press Archive class** until the very end: it closes joining, clears the code and blocks new quizzes and sessions.

## 8. Create a quiz (draft → publish)

**Who:** Professor. Only the quiz's author can host it, so the Professor must write the quiz they'll present.

1. On the class page → **+ New quiz**. Or **Dashboard** → **Create a quiz** → **Which class is this quiz for?** → pick the class.
2. Enter a title, and set **Time per question** to 20 s or less to keep the demo moving.
3. Add 3 or more questions. Each needs text, at least 2 choices and at least 1 marked **Correct**. You can add an **Answer explanation** and give a question its own time.
4. Click **Save draft**.
5. **Expected:** **Quizzes** shows the quiz as **Draft**, with **Review & publish**. A draft can't be hosted.
6. Click **Review & publish** → **Publish quiz**.
7. **Expected:** the status changes to **Published**, and the row now offers **Host in this class**.
8. Shortcut for next time: **Save & publish** in the editor does both in one step.

Also worth showing:
- A student can also click **+ New quiz** in the class. Only they and the class organizers can see it.
- A student's quiz can't be hosted in the class, because only organizers host. Its row shows **Organizers host**.
- Leaving the editor with unsaved work asks **Discard your changes?**.

## 9. Host a class session

**Who:** Professor.

1. Class page → **Quizzes** → **Host in this class**. Or **Dashboard → Present** → **⋯** on the quiz → **For:** the class.
2. **Expected:** the host lobby opens: **Live session · Waiting room**, a 6-digit **Session code**, and *"Waiting for players to join…"*.

Note: an **Open session** (no class) can be joined by anyone signed in who has the code, but it **does not** appear on the class page, in class reports or in the grade export. **Always pick the class for the demo.**

## 10. Join with the LIVE button

**Who:** Student A.

1. Open the class page, or stay on it.
2. **Expected:** within about 5 seconds, an orange **LIVE** bar appears with the quiz title and **Join lobby**. The page checks every 5 s and whenever the tab regains focus.
3. Tap the bar. **Expected:** the waiting room opens, and the host's player count goes up.
4. On the Professor's screen, the bar reads **Return to hosting**.

## 11. Join with the code (Join game)

**Who:** Student B.

1. **Join game** → type the 6-digit code → **Join →**.
2. **Expected:** the waiting room opens.
3. For a class session, only active class members get in. Anyone else gets `not_class_member`.

## 12. Live game: host controls and playing

**Who:** Professor hosting, both students playing.

1. Host: **Start quiz →**. Each player's screen shows the question, the choices and a countdown.
2. Players tap an answer. **Expected:** **Answer submitted!** · *"Waiting for everyone else to answer…"*.
3. The question closes when everyone has answered or the time runs out. Both sides then see the correct answer and how everyone answered, and players see **Got it right** / **Got it wrong**, plus points and rank.
4. Host: **Next question →**. Faster correct answers score more points.
5. **Late join:** start a third player (or a student who hasn't joined) partway through. The LIVE bar reads **Join @ Q*n***, and late joiners are welcome.
6. **Skip:** on one question, the host clicks **Close question** early. It closes for everyone with the results so far.
7. **Reconnect:** a player reloads the page mid-question. The game picks up where it was, and the same answer can't be submitted twice.
8. Host: **End session** → confirm **End the session and save the final results?**.
9. **Expected:** players see **Quiz complete**, with their **Final rank**, **Points** and **Correct answers**.

If it goes wrong:
- If the host closes their tab, the game waits. Players see "waiting for host", and the host can go back with **Return to hosting**. After 15 minutes with no host, the server ends the session on its own.
- **Always click End session.** Results, reports and grades only count **completed** sessions.
- Don't run more than one backend worker: the live socket registry lives in a single process.

## 13. Session results and CSV export

**Who:** Professor, then a student.

1. Professor: open the session's results, via the link after the game or **Classes → Presentations → Report**.
2. **Expected:** totals (**Participants**, **Average correct**, **Average points**), a **Leaderboard** (rank, participant, points, correct) and **Question breakdowns**, all searchable.
3. Click **Export CSV**. **Expected:** a CSV of the session's results downloads.
4. Student: **Participate** tab → their own results (own rows only).

## 14. Class reports

**Who:** Professor (Admin view), then a student.

- The summary bar shows students, presentations, class average and attendance.
- **Presentations:** each completed session, with date, quiz, attendance, average, top score and report link.
- **Students:** each student's average, attendance, total points and last five scores. A dotted dash means absent. Organizers aren't graded.
- Open a session, quiz or student report → **Export Excel**. An `.xlsx` downloads.
- Student: **My class report** shows only their own rows, and they can export only their own report.
- Members never see classmates' scores.

## 15. Export grades

**Who:** Professor, on the class page in **Admin** view.

1. Click **Export grades**.
2. **Expected:** `class-grades.csv` downloads, with a row per student, a column per completed class session, and totals.
3. Check that a student who missed a session shows as absent there, not as 0 in their average.

If it goes wrong: if the file is empty or missing a session, that session was an open session or was never ended (§9, §12).

## 16. Leaving and archiving (end of demo)

- Student: **Leave class** → confirm. They lose access to the class. The last organizer can't leave.
- Professor: **Settings → Archive class** → confirm. The class is now read-only, and its history stays.

## 17. Deactivated account (optional)

```sql
UPDATE account SET is_active = FALSE WHERE email = 'studentb@example.com';
```
Student B reloads and sees **Account · Deactivated · Access paused**. Set it back to `TRUE` afterwards.

## 18. API-only features (not in the UI yet)

These exist only in the backend. Show them at `http://127.0.0.1:8001/docs` if asked:
- **Quiz collaborators:** `POST /classes/{id}/quizzes/{quiz_id}/collaborators`. Collaborators can edit a draft but not publish it.
- **Quiz submissions and approvals** (V3 task 4): `POST /classes/{id}/quiz-submissions`, then `PATCH … {"status":"APPROVED"}`. Hosting doesn't check approval yet.

For "Try it out" in `/docs`, you need a bearer token. Copy it from the browser's network tab (`Authorization` header on a `/me` request).

---

## Known issues

1. **The live e2e test fails on `demo/all` (and on `main`).** `frontend/e2e/live.e2e.test.js` creates a class as the plain-User `e2e|host`. Since the V3 faculty rule, that returns `403 faculty_required`. The live flow itself is fine: with the host promoted to Admin, both tests pass. The fix belongs in `backend/tests/e2e_server.py`: give `e2e|host` `account_type = 'ADMINISTRATOR'`. CI doesn't run this suite, which is why nobody noticed.
2. **Admin is required for every organizer action.** Making a regular User an **Organizer** in **Members** doesn't let them host, see reports or export grades. `ClassAccess.is_organizer` requires Admin (`is_faculty = is_admin`) *and* the ORGANIZER role. Use the Admin account for anything an organizer does.
3. **No phones over Wi-Fi.** The dev servers listen on `localhost`, and Auth0's SPA SDK refuses plain-`http` origins other than `localhost`. Participants on other devices need the HTTPS deployment (`docs/DEPLOYMENT.md`). For a local demo, use separate browser profiles on one machine.
4. **Open sessions are invisible to classes.** Only sessions started **for a class** show the LIVE button and count in reports and grades.
5. **Unfinished sessions don't count.** A session counts toward results only after **End session**, or after the 15-minute abandoned-host timeout.
6. **Bundle size warning.** `npm run build` warns about a 662 kB chunk. It doesn't break anything.
