# Live quiz load test

Runs one class's live quiz with many students at once, through the real
FastAPI app and the same live-session code the React app uses, and reports how
long each step takes.

```bash
cd frontend
npm run loadtest                                   # 50 students, 5 questions
npm run loadtest -- --students 100 --questions 10  # bigger class
npm run loadtest -- --timeout 60                   # seconds to wait per step (default 30)
```

It starts `backend/tests/e2e_server.py` itself, with a test key standing in for
Auth0, so no real accounts are involved and nothing is sent to Auth0. It needs
the backend's Python environment (`backend/.venv`, or set `BACKEND_PYTHON`).
Don't point it at the deployed site.

## What it does

1. A faculty host creates a class; every student signs in for the first time
   and joins with the class code; the host approves them all.
2. The host creates, publishes and approves a quiz (four choices per question)
   and starts a live session.
3. Every student joins the session and connects over WebSockets.
4. For each question the host opens it, and **all students answer at the same
   moment**; the question closes by itself once everyone has answered.
5. The host ends the session and everyone receives the final results.

## Reading the report

```
Step                                    count    median       p95     worst  failed
sign in + join class                      100    1.77 s    1.89 s    1.91 s       0
join session (HTTP)                       100    816 ms    868 ms    890 ms       0
connect socket + lobby                    100    484 ms    670 ms    681 ms       0
question reaches student                  500     20 ms     44 ms     44 ms       0
answer accepted                           500    498 ms    856 ms    952 ms       0
results reach student                     500    201 ms    948 ms    948 ms       0
whole question (open → all results)         5    1.17 s    1.52 s    1.52 s       0
final results reach student               100     54 ms     55 ms     55 ms       0
Students who finished: 100/100   Final leaderboard rows: 100   Total time: 10.66 s
PASS: every student joined, answered every question and got the results.
```

- **question reaches student**: from the host pressing "next question" to each
  student's screen having it.
- **answer accepted**: from a student answering to the server confirming it,
  with every student answering at once.
- **results reach student**: from the last answer being accepted to each
  student having the results.
- **p95**: 95% of students were at least this fast. **failed** counts errors
  and timeouts; the first error of each step is printed below the table.

It exits with status 0 on PASS and 1 on FAIL, so it can run in a script.

## Closer to production: MySQL

By default the data goes to a throwaway SQLite file. The deployed app uses
MySQL, so for realistic numbers point it at a migrated MySQL **test** database
(the name must contain `test`; tests create their own data):

```bash
E2E_DATABASE_URL='mysql+pymysql://root:<password>@127.0.0.1:3307/quizdb_test?charset=utf8mb4' \
  npm run loadtest -- --students 100
```

The example numbers above are from MySQL 8.0 on a laptop.
