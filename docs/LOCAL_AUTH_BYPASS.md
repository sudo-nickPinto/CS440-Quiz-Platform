# Local Authentication Bypass

The development-only authentication bypass lets developers use the complete
local application without signing in through Auth0. It supports multiple named
accounts so one developer can manually run a host and two participants.

The bypass is intentionally unavailable when `APP_ENV` is anything other than
`development`, and Vite excludes it from production builds.

## Prerequisites

- The repository dependencies are installed.
- A migrated MySQL database is available locally.
- `frontend/.env` contains:

```env
VITE_API_BASE_URL=http://127.0.0.1:8001
```

## Start one backend

All users must share one backend process because live-session state and
WebSocket connections are coordinated by the backend's in-memory live hub.

From `backend/`, run:

```bash
APP_ENV=development \
DEV_AUTH_BYPASS=true \
CORS_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:5175 \
DATABASE_URL='mysql+pymysql://root:devpass@127.0.0.1:3307/quizdb_test?charset=utf8mb4' \
.venv/bin/uvicorn app.main:app --reload --port 8001
```

Adjust `DATABASE_URL` for your local database. Never commit its password.

## Start three frontend identities

Open three terminals. Run each command from `frontend/`.

### Host

```bash
VITE_DEV_AUTH_BYPASS=true \
VITE_DEV_AUTH_USER=host \
npm run dev -- --port 5173 --strictPort
```

Open <http://localhost:5173>.

### Alice

```bash
VITE_DEV_AUTH_BYPASS=true \
VITE_DEV_AUTH_USER=alice \
npm run dev -- --port 5174 --strictPort
```

Open <http://localhost:5174>.

### Bob

```bash
VITE_DEV_AUTH_BYPASS=true \
VITE_DEV_AUTH_USER=bob \
npm run dev -- --port 5175 --strictPort
```

Open <http://localhost:5175>.

The backend creates these active `USER` accounts on their first request:

```text
host@localhost
alice@localhost
bob@localhost
```

Valid identity names contain 1–32 lowercase letters, numbers, underscores, or
hyphens and must start with a letter or number.

## Manual MVP flow

1. In the host window, create and save a quiz.
2. Select **Host live session** and copy the six-digit join code.
3. In the Alice and Bob windows, join using that code.
4. Start or open the first question from the host window.
5. Submit different answers from Alice and Bob.
6. Continue through the quiz and end the session.
7. Verify the final standings and reopen the saved results.

## Automated host plus two-participant flow

The E2E suite starts a real FastAPI server, real REST requests, and real
WebSockets with separate host, Alice, and Bob accounts:

```bash
cd frontend
BACKEND_PYTHON='../backend/.venv/bin/python' npm run test:e2e
```

## Safety notes

- Never enable `DEV_AUTH_BYPASS` in a deployed environment.
- Do not add the bypass variables to production configuration.
- The backend ignores the flag unless `APP_ENV=development`.
- A production Vite build ignores `VITE_DEV_AUTH_BYPASS`.
- The generated local tokens are not real Auth0 tokens and work only while the
  backend development bypass is enabled.
