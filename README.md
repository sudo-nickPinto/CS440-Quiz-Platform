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

## Environment Variables

Do not commit passwords, API keys, database credentials, or other secrets.

Local environment variables should be stored in `.env` files, which are ignored by Git.
