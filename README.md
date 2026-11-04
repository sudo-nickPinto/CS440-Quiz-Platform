# CS440-Quiz-Platform
Central repo for Gettysburg's CS440 Fall Capstone course, regarding the creation of a kahoot-style quiz platform

## Tech Stack

- Frontend: React + Vite
- Backend: FastAPI
- Database: MySQL

## Project Structure

```text
CS440-Quiz-Platform/
├── frontend/           # React frontend
├── backend/            # FastAPI backend
│   └── app/
├── meeting_minutes/
├── notes/
├── .gitignore
└── README.md
```

## Getting Started

### 1. Clone the Repository

```bash
git clone <repository-url>
cd CS440-Quiz-Platform
```

### 2. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend will run at:

```text
http://localhost:5173
```

### 3. Backend Setup

From the project root:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Edit `backend/.env` with your MySQL credentials. The shared database is
`f26_cs440_quizdb` on `cray`; do not commit the `.env` file or its password.

The backend will run at:

```text
http://127.0.0.1:8000
```

FastAPI documentation is available at:

```text
http://127.0.0.1:8000/docs
```

The database readiness endpoint is available at:

```text
http://127.0.0.1:8000/health
```

## Authentication

Login uses Auth0 email/password (no Google sign-in); new signups verify their email, then can use the app right away. The frontend needs `frontend/.env` (copy `frontend/.env.example`); the backend needs `AUTH0_DOMAIN` and `AUTH0_AUDIENCE` in `backend/.env`. On first login the backend creates the user's row in the `account` table. See [docs/AUTH.md](docs/AUTH.md) for diagrams, local setup with a Docker MySQL, error codes and how to protect a new route.

Note: `frontend/.env.example` points at the backend on port `8001`, so run `uvicorn app.main:app --reload --port 8001`.

## API

Every REST route, who may call it and its error codes: [docs/API.md](docs/API.md). The live WebSocket: [docs/LIVE_PROTOCOL.md](docs/LIVE_PROTOCOL.md).

## Development Workflow

Before starting a new feature, update your local `main` branch:

```bash
git checkout main
git pull origin main
```

Create a new branch for your feature:

```bash
git checkout -b feature/feature-name
```

For example:

```bash
git checkout -b feature/question-response
```

After completing your work:

```bash
git add .
git commit -m "Add question response feature"
git push origin feature/question-response
```

Then create a pull request to merge the feature into `main`.

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every pull request into `main`, on every push to `main`, and by hand from **Actions → CI → Run workflow**. It has three jobs, and a ruleset on `main` requires all three to pass before a PR can merge:

| Check | What it does |
|---|---|
| `backend` | Applies every migration in `ulugbek-err/migrations/` to a fresh MySQL 8 container, then runs the whole pytest suite against it, including the migration, authorization, locking and optimistic-concurrency tests. Fails if any MySQL test is skipped. |
| `frontend` | `npm ci`, `npm test`, `npm run lint` and `npm run build`, with placeholder Auth0 values. |
| `containers` | Validates the Compose files with `deploy/.env.example` and builds the backend and frontend images. Images are never pushed and nothing is deployed. |

- A newer push to the same PR cancels the older run.
- When a job fails, its test reports and logs are attached to the run under **Artifacts**.
- Don't rename the jobs. Their names are the required checks in the `main` ruleset (**Settings → Rules → Rulesets**).
- Deployment stays manual ([docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)) until the Reclaim migration, backups, credentials and rollback steps are settled.

To run the MySQL tests locally the way CI does, migrate a database whose name contains `test` and set `TEST_DATABASE_URL` (see `backend/.env.example`). Without it, those tests are skipped.

## Environment Variables

Do not commit passwords, API keys, database credentials, or other secrets.

Local environment variables should be stored in `.env` files, which are ignored by Git.

## Docker deployment

Production-ready Dockerfiles and Compose configuration are included for the
React frontend, FastAPI backend, and an optional persistent MySQL container.
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for local verification and Reclaim
deployment instructions.
