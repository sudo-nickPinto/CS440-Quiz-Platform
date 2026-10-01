# Roadmap

The plan for the rest of the semester (2026-10-01 to about 2026-12-11). We build a **walking skeleton** first: every layer connected end to end, even if thin. Then we add features one vertical slice at a time. Every task ends in something we can show: a merged PR, a doc, a passing test or a demo.

## 1. Where we are (main @ `b2973d0`, 2026-10-01)

| Area | Status | Owner (git evidence) |
|---|---|---|
| FastAPI foundation (config, DB session, errors, `/health`) | Done | Anh |
| Auth0 backend + frontend, `/me`, account linking | Done (#21, #22) | Nick |
| Quiz ORM models | Done (#13) | Anh |
| SQL schema `0001`–`0004` + ER diagram v2 | Done as hand-run SQL; needs ER refresh + a migration runner | Ulug |
| Quiz CRUD → publish → versioning | Written, **not merged**: stacked PRs #16–#20 (`feature/quiz-list-archive` … `feature/quiz-versioning`) | Anh |
| Mockups: in-quiz host/participant (`anh/`), dashboard + design guide (`taha/`), login/lobby (`anindo/`) | Done | Anh, Taha, Anindo |
| Classes, sessions/joining, WebSocket, scoring, results, exports | Not started (tables exist) | — |
| SRS cleanup, REST API contract, live-session protocol doc | Not started | — |
| CI, frontend tests, seed data, app shell/router | Not started | — |

## 2. Timeline

Sprints are two weeks. Red bars (`crit`) are the critical path: if one slips, the demo slips. Thanksgiving week (11-23 to 11-29) is a buffer with nothing planned.

```mermaid
gantt
    title CS440 Quiz Platform - Fall 2026
    dateFormat YYYY-MM-DD
    axisFormat %m-%d

    section Sprint 0 (done)
    FastAPI foundation                       :done, s0_api, 2026-09-14, 2026-09-30
    Auth0 end to end (me + linking)          :done, s0_auth, 2026-09-21, 2026-10-01
    Quiz ORM models                          :done, s0_orm, 2026-09-24, 2026-09-30
    SQL schema 0001-0004 + ER v2             :done, s0_schema, 2026-09-14, 2026-09-30
    Mockups (in-quiz, dashboard, login)      :done, s0_mock, 2026-09-07, 2026-09-30

    section Sprint 1 - walking skeleton
    Quiz CRUD/versioning - merge stack       :active, quiz_stack, 2026-10-01, 5d
    SRS - auth to Auth0                      :active, srs_auth, 2026-10-01, 2d
    SRS - terminology                        :active, srs_terms, 2026-10-01, 2d
    SRS - modes vs roles                     :active, srs_modes, 2026-10-01, 2d
    SRS - scoring choice                     :srs_scoring, after srs_modes, 2d
    SRS - private vs public                  :srs_private, after srs_modes, 2d
    SRS - class joining                      :srs_join, after srs_modes, 2d
    SRS - Taken/Made/explanations/stats/export :srs_pages, after srs_terms, 3d
    SRS - MVP vs stretch                     :srs_mvp, after srs_scoring srs_private srs_join srs_pages, 2d
    REST API contract                        :crit, api_contract, after srs_modes, 5d
    Live-session protocol doc                :crit, active, ws_protocol, 2026-10-01, 5d
    WebSocket PoC                            :crit, ws_poc, after ws_protocol, 7d
    Authz helpers + role tests               :authz, 2026-10-08, 7d
    DB - ER update + migration runner        :db_final, 2026-10-01, 7d
    CI workflow                              :q_ci, 2026-10-01, 5d
    Backend formatting + tests               :q_betest, after q_ci, 4d
    Test DB config                           :q_testdb, after db_final, 3d
    Seed data                                :q_seed, after db_final, 4d
    Setup docs                               :q_docs, after q_seed, 2d
    Global theme from DESIGN-GUIDE           :fe_theme, 2026-10-01, 5d
    Router + nav (student vs professor)      :fe_router, after fe_theme, 5d
    Taken/Made tabs                          :fe_tabs, after fe_router, 4d
    Loading/error/empty states               :fe_states, after fe_router, 3d
    Protected routes + unauthorized state    :fe_protect, after fe_router, 3d

    section Sprint 2 - core features
    Classes + membership API                 :crit, be_classes, after api_contract authz, 6d
    Session create/join (codes, lobby)       :crit, be_sessions, after be_classes ws_poc, 7d
    Made quiz-library page                   :fe_made, after fe_tabs quiz_stack, 7d
    Quiz editor first flow                   :fe_editor, after fe_made, 6d
    Frontend lint + tests                    :q_fetest, 2026-10-15, 7d

    section Sprint 3 - live gameplay
    Response submission + scoring            :crit, be_scoring, after be_sessions, 8d
    Live UI behavior (controls, states)      :crit, fe_live_ui, after ws_poc be_sessions, 7d
    Live UI integration                      :crit, fe_live_int, after fe_live_ui be_scoring, 7d
    Class-management UI                      :fe_classes, 2026-10-29, 10d

    section Sprint 4 - results
    Results + Taken history                  :crit, be_results, after fe_live_int, 5d
    Exports + stats                          :crit, be_export, after be_results, 5d
    Taken/results review page                :fe_review, after be_results, 5d

    section Thanksgiving (buffer)
    No planned work - catch up only          :thanks, 2026-11-23, 7d

    section Sprint 5 - hardening and demo
    End-to-end testing + bug bash            :crit, e2e, after thanks be_export fe_review, 5d
    Deploy                                   :crit, deploy, after e2e, 3d
    Final demo + docs                        :crit, demo, after deploy, 3d
```

## 3. Critical path

Arrows mean "must be done before". Red nodes are on the critical path.

```mermaid
flowchart LR
    SRS["SRS cleanup"] --> API["REST API contract"]
    API --> CLS["Classes + membership API"]
    API --> SES["Session create/join"]
    AUTHZ["Authz helpers"] --> CLS
    CLS --> SES
    PROTO["Live-session protocol doc"] --> WS["WebSocket PoC"]
    WS --> SES
    SES --> SCORE["Responses + scoring"]
    WS --> LIVE["Live UI behavior"]
    LIVE --> LIVEINT["Live UI integration"]
    SCORE --> LIVEINT
    SCORE --> RES["Results + Taken history"]
    RES --> EXP["Exports + stats"]
    RES --> REVIEW["Taken/results review page"]
    SHELL["Frontend app shell"] --> MADE["Made quiz-library page"]
    QUIZ["Quiz CRUD stack merged"] --> MADE
    MADE --> EDITOR["Quiz editor"]
    LIVEINT --> E2E["E2E tests"]
    EXP --> E2E
    REVIEW --> E2E
    E2E --> DEPLOY["Deploy"] --> DEMO["Final demo"]

    classDef crit fill:#f8d7da,stroke:#b02a37,stroke-width:2px,color:#000
    class API,CLS,SES,PROTO,WS,SCORE,LIVE,LIVEINT,RES,EXP,E2E,DEPLOY,DEMO crit
```

## 4. Tasks by sprint

Owners come from who has committed related work. "Unclaimed" means nobody has touched it yet, so anyone can take it.

### Sprint 0: done (through 09-30)

| Task | Owner | Done when |
|---|---|---|
| FastAPI foundation | Anh | `/health` returns DB status on `main` (done) |
| Auth0 end to end, `/me`, account linking | Nick | Login works and `/me` returns the account; #21 and #22 merged (done) |
| Quiz ORM models | Anh | #13 merged (done) |
| SQL schema `0001`–`0004` + ER v2 | Ulug | Migrations in `ulugbek-err/migrations/` run cleanly on MySQL 8 (done) |
| Mockups: in-quiz, dashboard + design guide, login/lobby | Anh, Taha, Anindo | `anh/`, `taha/`, `anindo/` on `main` (done) |

### Sprint 1: walking skeleton (10-01 to 10-14)

| Task | Owner | Done when |
|---|---|---|
| Quiz CRUD/versioning: merge the stack (#16–#20) | Anh | All five PRs merged in order; quiz tests pass on `main` |
| SRS: auth section rewritten for Auth0 | unclaimed | SRS PR replaces the old password/login section with the Auth0 flow |
| SRS: terminology | unclaimed | Glossary section; one term per concept (quiz, version, session, class/group) used throughout |
| SRS: modes vs roles | unclaimed | SRS states which are roles (student, professor) and which are modes (host, participant) |
| SRS: scoring choice | unclaimed | One scoring rule written down with a worked example |
| SRS: private vs public quizzes | unclaimed | Visibility rules written down, matching `quiz_group` |
| SRS: class joining | unclaimed | How a student joins a class (code, invite or roster) written down |
| SRS: Taken/Made/explanations/stats/export | unclaimed | Each page's contents, answer explanations, stats and export formats written down |
| SRS: MVP vs stretch | unclaimed | Every requirement tagged MVP or stretch; team agrees in a meeting |
| REST API contract | unclaimed | `docs/API.md` (or OpenAPI) lists every MVP endpoint with request, response and error shapes |
| Live-session protocol doc | Nick (proposed) | `docs/LIVE_PROTOCOL.md` has a state diagram, every event with its payload, and rules for reconnect, duplicate answers and host disconnect |
| WebSocket PoC | Nick (proposed) | Demo: host creates a session, two clients join, host starts a question, both receive it, a reconnecting client gets current state; a two-client pytest passes |
| Authorization helpers + role tests | Nick | `require_role` and ownership checks merged, with tests for missing, invalid, valid and wrong-role tokens |
| DB: ER update + migration runner | Ulug | `ER_Diagram.md` matches `0004`; one command applies pending migrations and records them in `schema_migrations` |
| CI workflow | unclaimed | GitHub Actions runs lint and tests on every PR |
| Backend formatting + tests | unclaimed | Formatter/linter config committed; `pytest` runs green in CI |
| Test DB config | unclaimed | Tests use a separate database (Docker MySQL or env var), never the shared `cray` DB |
| Seed data | unclaimed | Script loads demo accounts, a class, and two published quizzes |
| Setup docs | unclaimed | A new teammate goes from clone to running app + seeded DB using only `README.md` |
| Global theme from `taha/DESIGN-GUIDE.md` | Taha | One global stylesheet with the design tokens, imported by `frontend/` |
| Router + nav (student vs professor) | unclaimed | `react-router` in place; nav shows different links per role |
| Taken/Made tabs | unclaimed | Tabs switch between two routed (empty) pages, styled per the design guide |
| Loading/error/empty states | unclaimed | Shared components used by at least one page, shown at 390px width |
| Protected routes + unauthorized state | Nick | Logged-out users are sent to login; wrong role sees an "unauthorized" screen |

### Sprint 2: core features (10-15 to 10-28)

| Task | Owner | Done when |
|---|---|---|
| Classes + membership API | unclaimed | Professor creates a class, students join it, roster endpoint works; tests pass |
| Session create/join (codes, lobby) | unclaimed | Host creates a session from a published version, gets a join code; participants join and appear in the lobby |
| Made quiz-library page | Taha | Lists the user's quizzes from the API (mock data first), with create, open and archive |
| Quiz editor first flow | unclaimed | Create a quiz, add multiple-choice questions, publish; demo end to end against the API |
| Frontend lint + tests | unclaimed | `npm run lint` clean; a test runner (e.g. Vitest) with at least one component test, run in CI |

### Sprint 3: live gameplay (10-29 to 11-11)

| Task | Owner | Done when |
|---|---|---|
| Response submission + scoring | unclaimed | Answers saved once per participant per question; scores match the SRS rule; tests cover late and duplicate answers |
| Live UI behavior (presenter/participant controls, reconnecting, waiting, ended states) | Anh (in-quiz mockups), Anindo (lobby) | Each screen from `anh/` and `anindo/` ported to `frontend/` and driven by fake events |
| Live UI integration | Anh | Demo: a full game with one host and two participants over the real WebSocket |
| Class-management UI | unclaimed | Professor creates a class and sees its roster; student joins with a code |

### Sprint 4: results (11-12 to 11-22)

| Task | Owner | Done when |
|---|---|---|
| Results + Taken history (incl. presenter/professor results) | unclaimed | `result` rows written when a session ends; endpoints for a student's history and a host's session results |
| Exports + stats | unclaimed | Per-quiz and per-student CSV export with high, average, low and distribution |
| Taken/results review page | unclaimed | Student reviews a finished quiz with their answers and explanations |

### Thanksgiving buffer (11-23 to 11-29)

Nothing planned. Use it only to catch up on slipped work.

### Sprint 5: hardening and demo (11-30 to 12-11)

| Task | Owner | Done when |
|---|---|---|
| End-to-end testing + bug bash | unclaimed | Scripted run of login → create quiz → host → play → results passes; open bugs triaged |
| Deploy | unclaimed | App reachable at a shared URL with the production Auth0 settings |
| Final demo + docs | unclaimed | Demo rehearsed; README and docs match what we ship |

## 5. Notes

- **Dates are proposals.** Adjust them at the next team meeting, then update this file.
- **Owners are inferred from commit history**, not assigned. "Nick (proposed)" means Nick plans to take it. To claim an "unclaimed" task, put your name in the table in a PR.
- In the timeline, "Quiz CRUD/versioning – merge stack" covers both the "merge the versioning stack" and "backend quiz CRUD/versioning" items, since they are the same code.
