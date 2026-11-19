# Email

QuizBurg sends three emails of its own, all through one service, `EmailService` in `backend/app/emails.py`:

| Email | Sent when |
|---|---|
| Added to class | An organizer adds someone who has an account, with **+ Add student** or a roster import. They are a student right away |
| Roster invitation | A roster row lists an email that has no account yet: it asks them to sign up with that address |
| Join approved | An organizer approves a join request (one, **Accept all**, or a roster import that matches the person) |
| Join rejected | An organizer rejects a join request |

Auth0 still sends sign-up, verification and password emails. Those are set up in the Auth0 dashboard, not here.

## How sending works

- Emails are written in the service after the database change, and sent from a FastAPI background task once the response is ready. A mail-server failure is logged and never undoes the change: an approved student stays approved.
- Messages are plain text with links built from `APP_BASE_URL`, such as `https://<app>/app/classes/12` and the class join link.
- Addresses are not written to the log; only the subject is.

## Settings

All are environment variables (`backend/.env` locally, `deploy/.env` with Docker Compose).

| Variable | Default | Meaning |
|---|---|---|
| `EMAIL_BACKEND` | `log` | `log` prints each email in the backend window and sends nothing (local development). `smtp` sends for real. `memory` keeps them in a list, for tests |
| `EMAIL_FROM` | `QuizBurg <no-reply@quizburg.local>` | The From header. Use an address the SMTP server may send as |
| `SMTP_HOST` | | Required with `EMAIL_BACKEND=smtp` |
| `SMTP_PORT` | `587` | |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | | Leave the username blank for a relay that needs no login. Never commit the password |
| `SMTP_STARTTLS` | `true` | Upgrade the connection with STARTTLS before logging in |
| `APP_BASE_URL` | `http://localhost:5173` | The frontend address used in links |

Any SMTP service works, for example the college's relay or a transactional email provider. To try it locally without a real server, keep `EMAIL_BACKEND=log` and read the emails in the Uvicorn window.

## Adding another email

Add a method to `EmailService` that returns an `OutgoingEmail`, have the service function return it alongside its result, and in the route pass the list to `background_tasks.add_task(request.app.state.email.send_all, messages)`. See `backend/app/api/routes/class_roster.py`.
