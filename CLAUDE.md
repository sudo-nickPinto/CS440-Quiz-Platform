# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Gettysburg CS440 Fall Capstone: a Kahoot-style classroom quiz platform.

- `frontend/`: React 19 + Vite, `react-router`, Auth0 (`@auth0/auth0-react`)
- `backend/`: FastAPI + SQLAlchemy 2 on MySQL (PyMySQL), Auth0 JWT verification (PyJWT)
- Database schema: hand-written SQL migrations in `ulugbek-err/migrations/` (no Alembic)

**MVP scope:** there are two roles, USER and ADMIN. ADMIN is set by hand (`account.account_type = 'ADMINISTRATOR'`, mapped by `effective_role` in `backend/app/models/account.py`). Host and participant are things a user *does*, not roles. Professor/Student RBAC, classes, quiz editing and collaborators are deliberately deferred. Authorization is done with inline author-or-admin checks inside services, not role decorators. The DB tables for the deferred features already exist (`course_group`, `quiz_collaborator`, etc.) but are unused. The planned work lives in `docs/ROADMAP.md` (PR #23, branch `docs/roadmap`).

## Commands

### Backend (`backend/`)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                      # fill in DB_* and AUTH0_*
uvicorn app.main:app --reload --port 8001 # frontend .env.example expects 8001; docs at /docs

pytest                                     # all tests
pytest tests/test_scoring.py               # one file
pytest tests/test_quiz_api.py::test_name   # one test
TEST_DATABASE_URL=mysql+pymysql://root:devpass@127.0.0.1:3307/quizdb_test?charset=utf8mb4 pytest tests/integration
```

- Unit tests build the app with `create_app(Settings(database_url="sqlite://", ...))`, call `Base.metadata.create_all`, and override the `get_active_account` / `get_current_account` dependencies with a `CurrentAccount`. No Auth0 or MySQL is needed.
- `tests/integration/` runs against a real, migrated MySQL. These tests are **skipped** unless `TEST_DATABASE_URL` is set, and the DB name **must contain `test`** because the fixture deletes every row in every table.
- There is no linter or formatter configured for the backend.

### Frontend (`frontend/`)

```bash
cd frontend
npm install
cp .env.example .env   # VITE_AUTH0_DOMAIN / CLIENT_ID / AUDIENCE, VITE_API_BASE_URL
npm run dev            # http://localhost:5173
npm run lint
npm run build
```

There is no frontend test runner yet.

### Local database

Docker MySQL on port 3307 (`quizdb`, root/`devpass`). Apply `ulugbek-err/migrations/*.up.sql` in numeric order; full walkthrough in `ulugbek-err/LOCAL_DATABASE_SETUP.md`. The shared class DB is `f26_cs440_quizdb` on `cray`, reachable only from the school network or over an SSH tunnel.

## Backend architecture

`app/main.py:create_app(settings)` is an app factory. The lifespan creates a `Database` on `app.state.database`, and `get_db` yields one SQLAlchemy `Session` per request. Tests pass their own `Settings` into the factory.

Layering: `api/routes/*` (thin HTTP handlers) → `services/*` (business rules, authz, transactions) → `models/*` (SQLAlchemy ORM mapped onto the migration-defined tables). `schemas/*` holds the Pydantic request and response models. A new router must be registered in `api/router.py`.

- **Errors:** raise `APIError(status, code, message)` from `app/errors.py`. Every error response has the shape `{"error": {"code", "message"}}`, and the frontend's `api.js:apiFetch` displays `message`.
- **Auth chain** (`app/auth.py`): `current_user` verifies the Auth0 RS256 JWT against the tenant JWKS. `get_current_account` finds or creates the `account` row through `accounts.get_or_create_account`. `get_active_account` additionally rejects inactive accounts. Routes depend on these and receive a `CurrentAccount(account_id, role, is_active)`.
- **Account linking:** each Auth0 `sub` (`auth0|…`, `google-oauth2|…`) is a row in `account_identity` pointing at one `account`. A new `sub` is linked by **verified** email only. `account.auth0_sub` holds just the first login and must not be used for lookups. Details and diagrams are in `docs/AUTH.md`.
- **Quizzes:** a saved quiz is immutable in the MVP. `quiz` → `quiz_version` → `question` → `answer_choice`. Quizzes are archived, never deleted once played.
- **Sessions:** `live_session` references a `quiz_version_id` and has a six-digit numeric join code. Look up active sessions by `active_join_code`, which is cleared when a session ends so codes can be reused. Leave `live_session.group_id` NULL in the MVP.
- **Scoring** (`services/scoring.py`) is server-side and rewards speed. Scores stay hidden from participants until a question closes.
- **Time:** all DB timestamps are UTC.
- **Rules the DB does not enforce** are listed at the top of `0003_live_sessions.up.sql` and in `ulugbek-err/ER_Diagram.md`, and the services must check them.

## Schema changes

Ulugbek owns the schema. Never edit a migration that has already run on the shared DB; add a new `000N_*.up.sql` / `.down.sql` pair instead. When adding a table, keep `cleanup_database` in `tests/integration/conftest.py` in child-first FK order. Position uniqueness is enforced on questions and choices, so move items through a temporary position (or delete old choices before inserting new ones) when reordering.

## Frontend architecture

`main.jsx` wraps everything in `BrowserRouter`. In dev only, `/preview/dashboard/:view` renders the dashboard without auth. All other routes go through `Auth0Provider` → `App.jsx`, which handles silent session restore (with an anti-redirect-loop flag), then `AccountGate` (calls `GET /me` to create or link the account) → `/dashboard/:view`. The dashboard still runs on sample data (`src/data/dashboardDemo.js`) and is not yet wired to `/quizzes`. Call the API with `apiFetch(path, getAccessTokenSilently, options)`.

Auth0 behaviours worth knowing (more in `docs/AUTH.md` §9): in dev, tokens are cached in localStorage, while production keeps them in memory. On `localhost`, Auth0 always shows a consent screen and silent login fails with `consent_required`.

## Prototype folders

`anh/` (in-quiz host and participant screens), `anindo/` (login and lobby), and `taha/` (static HTML mockups for every screen) are standalone prototypes. They are reference material to port into `frontend/`, not apps to extend. `meeting_minutes/` and `notes/` are course documentation.

## Design system

`taha/DESIGN-GUIDE.md` is the source of truth; read it before building UI. Shared tokens live in `frontend/src/styles/theme.css`.

- Neo-brutalism in Gettysburg colors: 3px `var(--ink)` borders, hard `6px 6px 0 var(--ink)` shadows, square corners. No radius, blur or gradients (except the one stripe texture).
- Always use the color variables (`--navy`, `--orange`, `--sky`, `--sand`, `--ink`, `--white`, `--gray`), never raw hex. Orange means selected or a key number, navy means structure or the primary action, and sky means a secondary action.
- Fonts: Archivo Black for display text, Space Grotesk for everything else.
- Page skeleton: a header plus one bordered `.frame` that fills the screen, with only the inner `.list` scrolling (`.frame` needs `min-height: 0`).
- Design for phone width (390px) first, and check 1440, 1000 and 390 with no horizontal scroll.
- When porting a mockup, keep its class names, turn `innerHTML` building into JSX, and factor out shared components and CSS instead of copying them per page.

## Git workflow

Branch off `main` per feature (`feature/…`, `docs/…`, `chore/…`), push, and open a PR into `main`. `.env` files are gitignored, and each app has a `.env.example`.
