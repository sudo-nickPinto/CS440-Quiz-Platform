# Quiz Platform — ER Diagram (v2)

Updated database model for the MySQL database. Replaces the first-pass diagram and folds in
team feedback and the decisions from the 09-27 meeting.

## Diagram

```mermaid
erDiagram
    ACCOUNT ||--o{ COURSE_GROUP : teaches
    ACCOUNT ||--o{ GROUP_MEMBERSHIP : "belongs to"
    COURSE_GROUP ||--o{ GROUP_MEMBERSHIP : has
    ACCOUNT ||--o{ QUIZ : authors
    ACCOUNT ||--o{ QUIZ_COLLABORATOR : "co-edits"
    QUIZ ||--o{ QUIZ_COLLABORATOR : "edited by"
    QUIZ ||--o{ QUIZ_GROUP : "assigned to"
    COURSE_GROUP ||--o{ QUIZ_GROUP : has
    QUIZ ||--|{ QUIZ_VERSION : "has versions"
    QUIZ_VERSION ||--|{ QUESTION : contains
    ACCOUNT |o--o{ QUESTION : "is editing"
    QUESTION ||--|{ ANSWER_CHOICE : offers
    QUIZ_VERSION ||--o{ LIVE_SESSION : "played as"
    ACCOUNT ||--o{ LIVE_SESSION : hosts
    COURSE_GROUP |o--o{ LIVE_SESSION : "restricted to"
    LIVE_SESSION ||--o{ SESSION_PARTICIPANT : admits
    ACCOUNT ||--o{ SESSION_PARTICIPANT : joins
    LIVE_SESSION ||--o{ SESSION_QUESTION : runs
    QUESTION ||--o{ SESSION_QUESTION : "shown as"
    SESSION_PARTICIPANT ||--o{ RESPONSE : submits
    SESSION_QUESTION ||--o{ RESPONSE : receives
    ANSWER_CHOICE |o--o{ RESPONSE : selected
    SESSION_PARTICIPANT ||--o| RESULT : earns

    ACCOUNT {
        int account_id PK
        varchar auth0_sub UK "Auth0 subject id"
        varchar email UK "any Gmail"
        varchar display_name
        enum account_type "STUDENT, PROFESSOR, ADMINISTRATOR; NULL until chosen at first login"
        boolean is_active
        datetime created_at
    }
    COURSE_GROUP {
        int group_id PK
        varchar group_name
        int teacher_id FK "exactly one teacher"
        datetime created_at
    }
    GROUP_MEMBERSHIP {
        int group_id PK,FK
        int account_id PK,FK
        datetime joined_at
    }
    QUIZ {
        int quiz_id PK
        int author_id FK
        enum status "DRAFT, PUBLISHED, ARCHIVED"
        enum visibility "PRIVATE, PUBLIC"
        datetime created_at
        datetime updated_at
    }
    QUIZ_COLLABORATOR {
        int quiz_id PK,FK
        int account_id PK,FK
        datetime added_at
    }
    QUIZ_GROUP {
        int quiz_id PK,FK
        int group_id PK,FK
    }
    QUIZ_VERSION {
        int quiz_version_id PK
        int quiz_id FK
        int version_number "UK with quiz_id"
        varchar title
        text description
        datetime created_at
        datetime published_at "NULL = editable draft"
    }
    QUESTION {
        int question_id PK
        int quiz_version_id FK
        int question_order "UK with quiz_version_id"
        enum question_type "MULTIPLE_CHOICE, FILL_IN_BLANK"
        text question_text
        text explanation
        int time_limit_seconds
        int base_points
        int locked_by_id FK "nullable; who is editing"
        datetime locked_at "nullable; lock expires after a timeout"
        datetime updated_at
    }
    ANSWER_CHOICE {
        int choice_id PK
        int question_id FK
        int choice_order "UK with question_id; drives color"
        varchar choice_text
        boolean is_correct
    }
    LIVE_SESSION {
        int session_id PK
        int quiz_version_id FK "published versions only"
        int host_id FK
        int group_id FK "nullable (see open questions)"
        char join_code "unique among LOBBY/ACTIVE sessions"
        enum status "LOBBY, ACTIVE, COMPLETED, CANCELLED"
        int current_question_order "nullable"
        datetime created_at
        datetime started_at
        datetime ended_at
    }
    SESSION_PARTICIPANT {
        int session_participant_id PK
        int session_id FK
        int account_id FK
        datetime joined_at
        datetime left_at
    }
    SESSION_QUESTION {
        int session_question_id PK
        int session_id FK
        int question_id FK
        enum status "PENDING, OPEN, CLOSED"
        datetime opened_at
        datetime closes_at "server deadline"
        datetime closed_at
    }
    RESPONSE {
        int response_id PK
        int session_participant_id FK
        int session_question_id FK
        int choice_id FK "nullable"
        varchar text_answer "fill-in-blank, nullable"
        datetime submitted_at "millisecond precision"
        int response_time_ms
        boolean is_correct
        int points_awarded "correctness + speed"
    }
    RESULT {
        int result_id PK
        int session_participant_id FK,UK
        int total_score
        int correct_count
        int final_rank "ties share a rank: 1, 2, 3, 3, 5"
        datetime computed_at
    }
```

### Uniqueness constraints

| Table | Unique on |
|---|---|
| `account` | `auth0_sub`; `email` |
| `group_membership` | `(group_id, account_id)` (PK) |
| `quiz_collaborator` | `(quiz_id, account_id)` (PK) |
| `quiz_group` | `(quiz_id, group_id)` (PK) |
| `quiz_version` | `(quiz_id, version_number)` |
| `question` | `(quiz_version_id, question_order)` |
| `answer_choice` | `(question_id, choice_order)` |
| `live_session` | `join_code` while the session is LOBBY/ACTIVE (generated column + unique index) |
| `session_participant` | `(session_id, account_id)` |
| `session_question` | `(session_id, question_id)` |
| `response` | `(session_participant_id, session_question_id)` |
| `result` | `session_participant_id` |

## Changes from the first draft

**Renamed**
- `GROUP` → `COURSE_GROUP`, because `GROUP` is a MySQL reserved word.
- `SESSION` → `LIVE_SESSION`.
- `rank` → `final_rank`, `ranking_points` → `total_score`, `position` → `question_order`.

**Authentication (Auth0 + Google)**
- Removed `username` and `password_hash`. Accounts are identified by `auth0_sub` and `email`.
- `account_type` is STUDENT, PROFESSOR or ADMINISTRATOR (the 3 roles agreed on 09-20).
  - A user picks Student or Professor at first login, so the column stays NULL until they choose.
  - Administrators (our team) are set manually in the database.
- Participant and Presenter are things a user *does*, not stored roles.

**Quiz versioning**
- Added `QUIZ_VERSION` between `QUIZ` and `QUESTION`.
- A version with `published_at = NULL` is the editable draft. Publishing locks it.
- Editing a published quiz creates version N+1.
- Sessions point to a specific published version, so later edits never change past results.
- `title` and `description` moved to the version, so each session shows the title it was played with.

**Quiz collaboration**
- New `QUIZ_COLLABORATOR` table: the student group that built the quiz can edit it.
- The professor of any group linked through `QUIZ_GROUP` can also edit it. This comes from the relationship, so no extra rows are needed.
- Question-level edit lock: `QUESTION.locked_by_id` + `locked_at`.
  - Several people can edit the same quiz, but only one person can edit a given question at a time.
  - A lock expires after a timeout, so an abandoned browser tab can't block a question forever.

**Quiz fields**
- `QUIZ`: added `visibility` (PRIVATE / PUBLIC), separate from `status` (DRAFT / PUBLISHED / ARCHIVED). PUBLIC means visible to the quiz's groups only, not to everyone.
- `QUIZ`: added `created_at` and `updated_at`.
- `QUIZ_GROUP` (new): links a quiz to one or more course groups.
- `QUESTION`: added `question_type` and `explanation` (shown after each question).
- `ANSWER_CHOICE`: added `choice_order`. Dropped the stored `color`, because it comes from `choice_order` so colors always match the options shown.

**Live sessions**
- `LIVE_SESSION`: added `status`, `current_question_order`, `created_at` and an optional `group_id`.
- `SESSION_PARTICIPANT` (new): records who joined, including people who never answered.
  - Its unique key blocks duplicate joins and makes reconnecting after a refresh simple.
  - Connection status and heartbeats stay in server memory, not the database, to avoid constant writes.
- `SESSION_QUESTION` (new): when each question opened, its server deadline (`closes_at`) and when it closed.
  - Supports the Lobby → Question Open → Question Closed → Feedback flow.
  - Makes rejecting late answers a simple comparison.

**Responses and results**
- `RESPONSE` now points to `session_participant_id` and `session_question_id`.
  - Dropped `session_id`, which was redundant.
  - One response per participant per question.
  - Stores `is_correct`, `points_awarded` and `response_time_ms` exactly as the server calculated them at submission time.
- `RESULT` now points to `session_participant_id` (one per participant) and stores `total_score`, `correct_count` and `final_rank`.
- `GROUP_MEMBERSHIP` got a composite primary key and `joined_at`.

## Rules enforced by the backend (not the schema)

- **Hosting:** a session can be hosted by the quiz's author, its collaborators, or the professor of a linked group. The host presents and is never a `SESSION_PARTICIPANT`.
- **Joining:** if a session has a `group_id`, only members of that group can join.
- **Quiz visibility:** PUBLIC quizzes are visible only to members of the quiz's groups. PRIVATE quizzes are visible only to the author, collaborators and the professor.
- **Content checks:**
  - a session question must belong to the session's quiz version
  - a response's `choice_id` must belong to that question
- **Published versions can't be edited.**
- **Ranking:** ties share a rank and the next rank is skipped (1, 2, 3, 3, 5). This matches MySQL's `RANK()`.
- **Late joiners:** they receive 0 points for questions that closed before they joined.

## Decided

| Topic | Decision |
|---|---|
| Scoring | Correctness + speed |
| Teachers per group | One |
| Login | Google via Auth0; any Gmail allowed |
| Account type | Chosen at first login (Student/Professor); admins set manually |
| Collaborators | Quiz's student group + their professor; one editor per question at a time |
| Quiz visibility | Within the author's group(s) |
| Hosting | Students (their group's quiz) and professors; host presents only |
| Group-linked sessions | Members only |
| Ties | Shared rank, next rank skipped |

## Still open

1. **Adding students by Gmail:** what if the student has never logged in, so no account exists yet? Proposal: a `GROUP_INVITE (group_id, email, invited_at)` table, turned into a `GROUP_MEMBERSHIP` row on that student's first login.
2. **Sessions without a group:** can a session run with just a join code? This decides whether `LIVE_SESSION.group_id` is nullable.
3. **Speed formula:** Kahoot uses `base × (1 − (time/limit) / 2)`. The schema stores points per response, so any formula works, but we should pick one.
4. **Excel export:** it will probably show both correct answers and total score per day. Confirm with the client.

## Concerns

- **Self-selected Professor role.** If anyone can pick "Professor" at login, a student can give themselves access to classmates' results. Suggestion: professor accounts start unverified until an admin (our team) approves them.
- **Student groups vs course groups.** The team of 3–4 students building a quiz is modeled with `QUIZ_COLLABORATOR` rather than a second kind of group. Confirm that's how the team pictures it.
- **Migration tooling.** `feature/backend-setup` (SQLAlchemy) isn't merged yet. Decide between Alembic and plain SQL before writing migrations.
- **Shared database.** Agree on who is allowed to run migrations on the shared `cray` database.
