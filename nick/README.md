# Nick Pinto — Contributions to the CS440 Quiz Platform

This folder documents what Nick Pinto (GitHub: `sudo-nickPinto` / `spinto16`) contributed to the CS440 Fall 2026 capstone, a Kahoot-style quiz platform for Professor Kim, up through **PR #40**. It also gives a plain-language, week-by-week account of everyone else's work so Nick's work can be read in context.

> **Assumption:** this documentation treats every PR up to #40 as merged, including the ones still open on 2026-10-12 (#36, #38, #39, #40). The one exception is **#37 (CI workflow)**, which Nick closed on purpose ("not adding CI/tests right now") and is described as closed. Dates are in Eastern time, so a PR GitHub stamps "Oct 13, 01:30 UTC" shows here as Oct 12.

## Files in this folder

| File | What it covers |
|---|---|
| [01-authentication-and-accounts.md](01-authentication-and-accounts.md) | Login with Auth0, accounts in MySQL, joining Google and email logins into one account, in-app approval of new signups, removing Google sign-in, and the auth tests (PRs #21, #22, #31, #39, #40) |
| [02-live-sessions.md](02-live-sessions.md) | The real-time "play a quiz together" layer: the live protocol and the WebSocket proof of concept (PRs #36, #38) |
| [03-planning-process-and-maintenance.md](03-planning-process-and-maintenance.md) | Team management in weeks 1–3, client outreach, the repo, meeting minutes, the SRS, the MVP roadmap, the dependency security fix, and the proposed CI (PRs #23, #32, #37) |
| [04-team-timeline-by-week.md](04-team-timeline-by-week.md) | Week-by-week, plain-language account of the whole team's contributions, from Week 1 to Week 8 |

All diagrams are [Mermaid](https://mermaid.js.org/) blocks, so they render directly on GitHub.

## Nick's contributions at a glance

| PR | Course week | What it did (in one line) | Size |
|---|---|---|---|
| — | Wk 1–5 | Team manager through Sep 20, client email, repo setup, meeting minutes, SRS front matter and Section 1 | — |
| [#21](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/21) | Wk 6 | Users can sign up, log in and log out, and the backend checks who they are on every request | +768 / −47 |
| [#22](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/22) | Wk 6 | Logging in with Google or with email/password on the same email lands in the same account | +168 / −43 |
| [#23](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/23) | Wk 6 → 8 | MVP roadmap: Gantt chart, critical path, owners and "done when" for each task | +193 |
| [#31](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/31) | Wk 7 | 11 end-to-end tests proving protected routes really reject bad logins | +113 |
| [#32](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/32) | Wk 7 → 8 | Fixed a high-severity npm security warning | +3 / −3 |
| [#36](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/36) | Wk 8 | The live session protocol: the rulebook the host and player screens and the server follow during a game | +213 |
| [#37](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/37) | Wk 8 | *(closed)* Proposed automatic test/build checks on every PR | +75 |
| [#38](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/38) | Wk 8 | WebSocket proof of concept: a host and players can play questions in real time | +786 / −2 |
| [#39](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/39) | Wk 8 | New email signups wait for approval inside the app, instead of needing a verification email | +516 / −37 |
| [#40](https://github.com/sudo-nickPinto/CS440-Quiz-Platform/pull/40) | Wk 8 | Removed Google sign-in after the group decided to drop it | +14 / −599 |

## Where Nick's work sits in the system

The shaded boxes are what Nick built. Everything else was built by teammates, and Nick's code connects to it.

```mermaid
flowchart LR
    subgraph Browser["Browser (React + Vite)"]
        LP["Landing page<br/>(Anindo, from Taha's mockup)"]
        AG["AccountGate + api.js<br/>(Nick)"]
        DB_UI["Dashboard<br/>(Anindo, from Taha's mockup)"]
        AP["Approve users page<br/>(Nick)"]
        LIVE_UI["Live host / player screens<br/>(designed by Anh + Taha, not yet built)"]
    end

    AUTH0[("Auth0<br/>hosted login")]

    subgraph Backend["FastAPI backend"]
        FOUND["Config, DB session, errors, /health<br/>(Anh)"]
        AUTHPY["auth.py + accounts.py + /me<br/>(Nick)"]
        APPR["/accounts/pending, approve, reject<br/>(Nick)"]
        QUIZ["Quizzes API<br/>(Anh)"]
        SESS["Sessions: create + join<br/>(Anh)"]
        RESP["Answers + scoring<br/>(Pronob)"]
        LIFE["Question open/close rules<br/>(Pronob)"]
        RES["Results + leaderboard<br/>(Pronob)"]
        WS["WebSocket hub /ws/sessions/{id}<br/>(Nick)"]
    end

    MYSQL[("MySQL on the CS server<br/>schema + migrations by Ulugbek")]

    LP -->|"Sign in / Create account"| AUTH0
    AUTH0 -->|"access token"| AG
    AG -->|"GET /me"| AUTHPY
    AP --> APPR
    DB_UI --> QUIZ
    LIVE_UI <-->|"live events"| WS
    WS --> LIFE
    WS --> RESP
    WS --> RES
    WS --> SESS
    AUTHPY --> MYSQL
    APPR --> MYSQL
    QUIZ --> MYSQL
    SESS --> MYSQL
    RESP --> MYSQL
    LIFE --> MYSQL
    RES --> MYSQL
    FOUND --- MYSQL

    classDef nick fill:#f28c28,stroke:#111,color:#111,stroke-width:2px
    class AG,AP,AUTHPY,APPR,WS nick
```

## Nick's timeline

```mermaid
timeline
    title Nick's work by course week (Fall 2026)
    Week 1 (Aug 24-30) : Kickoff meeting scribe : Named team manager through Sep 20
    Week 2 (Aug 31-Sep 6) : Emailed Professor Kim : Created the GitHub repo : First meeting minutes committed : Built the React app for the collaboration assignment with Anh
    Week 3 (Sep 7-13) : Reviewed teammates' assignment PRs : Assigned SRS front matter and Section 1
    Week 4 (Sep 14-20) : Presented the web design and UI flow structure : Handed management to Taha
    Week 5 (Sep 21-27) : Finished and submitted the SRS : Reviewed the SRS : Assigned Auth0 login
    Week 6 (Sep 28-Oct 4) : Uploaded minutes for 09-13, 09-20, 09-27 : PR 21 Auth0 login + accounts : PR 22 account linking : PR 23 roadmap opened
    Week 7 (Oct 5-11) : PR 31 auth end-to-end tests : PR 32 npm security fix
    Week 8 (Oct 12-18) : PR 36 live protocol : PR 37 CI (closed) : PR 38 WebSocket PoC : PR 39 in-app signup approval : PR 40 remove Google sign-in
```
