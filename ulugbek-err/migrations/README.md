# Database migrations

These SQL files create our database tables. The tables match the diagram in [`../ER_Diagram.md`](../ER_Diagram.md).

**Setting up a database on your own laptop?** Follow [`../LOCAL_DATABASE_SETUP.md`](../LOCAL_DATABASE_SETUP.md) instead. It walks through everything step by step.

| File | What it does |
|---|---|
| `0001_accounts_and_groups` | `schema_migrations`, `account`, `course_group`, `group_membership` |
| `0002_quizzes` | `quiz`, `quiz_collaborator`, `quiz_group`, `quiz_version`, `question`, `answer_choice` |
| `0003_live_sessions` | `live_session`, `session_participant`, `session_question`, `response`, `result` |
| `0004_account_identity` | `account_identity` (one account, several Auth0 logins); copies existing `account.auth0_sub` values into it |
| `0005_optional_session_group` | Makes `live_session.group_id` optional. The MVP has one shared class, so sessions don't belong to a group |
| `0006_classes` | `class`, `class_membership` (classes with organizers and members, from PR #51) |
| `0007_session_class` | Adds `live_session.class_id`: the host may pick a class for a session, and then only its active members can join (task 6). NULL is an open session |
| `0008_quiz_class` | Adds `quiz.class_id`: every quiz belongs to a class, and only that class can see it (V3 task 2). Fills it in for quizzes played in exactly one class |
| `0009_account_profile` | Adds `account.first_name`, `last_name` and `avatar_key`: the profile people fill in once after signing up. `display_name` becomes "first last" when it is saved |

Each migration comes in two files:

- `.up.sql` makes the change (usually creating tables).
- `.down.sql` undoes it.

These work on MySQL 5.7 and newer. The `CHECK` rules only work on MySQL 8.0.16 or newer, and older versions skip them without any error. To see which version you have, run `SELECT VERSION();`.

## Before you run anything

- **Ulugbek owns the database design.** If you need a table or column added or changed, ask him. He'll add the migration, so everyone's database stays the same.
- **Don't change a migration after it's been run on the shared database.** If you need to change a table, add a new file, like `0004_...`.
- **Run them in order.** Run `.up.sql` files from lowest number to highest, and `.down.sql` files from highest to lowest.
- **Check what's already been run.** Every migration adds a row to the `schema_migrations` table when it runs. To see them:

  ```sql
  SELECT * FROM schema_migrations ORDER BY version;
  ```

## Running the migrations

Run this from the main project folder. Your database login info is in `backend/.env`.

```bash
for f in ulugbek-err/migrations/*.up.sql; do
  echo "Running $f"
  mysql -h "$DB_HOST" -u "$DB_USERNAME" -p "$DB_DATABASE" < "$f" || break
done
```

To run just one file:

```bash
mysql -h "$DB_HOST" -u "$DB_USERNAME" -p "$DB_DATABASE" < ulugbek-err/migrations/0003_live_sessions.up.sql
```

## Undoing the migrations

**Careful: this deletes the tables and all the data in them.**

```bash
for f in $(ls ulugbek-err/migrations/*.down.sql | sort -r); do
  echo "Undoing $f"
  mysql -h "$DB_HOST" -u "$DB_USERNAME" -p "$DB_DATABASE" < "$f" || break
done
```

## Testing on your own computer

See [`../LOCAL_DATABASE_SETUP.md`](../LOCAL_DATABASE_SETUP.md). It sets up a MySQL database in Docker that only you use.

## Notes for backend code

- **Times:** every time column is saved in UTC, so the backend should always save UTC times.
- **Finding a session by its join code:** use the `active_join_code` column, not `join_code`. `active_join_code` is empty once a session ends, which lets old codes be used again.
- **Reordering questions or answers:** two questions in the same version can't have the same position, and neither can two answers to the same question. To swap two of them, move one to a temporary position first, or renumber them all in one `UPDATE`.
- **Replacing a question's answers:** delete the old answers before adding the new ones. If the new ones are added first, they clash with the old ones that have the same position, and the database rejects them.
- **Sessions and groups:** leave `live_session.group_id` empty for the MVP. Use `live_session.class_id` (0007) for the session's class.
- **Classes:** use `class` and `class_membership`, not the old `course_group` and `group_membership`. Classes are archived, never deleted: a class with members can't be deleted.
- **Quizzes and classes:** `quiz.class_id` (0008) is the class that owns the quiz. Every new quiz gets one. It's only allowed to be empty for quizzes made before V3. See "Quizzes without a class" below.
- **Deleting quizzes:** you can't delete a quiz that has already been played. Set its `status` to `'ARCHIVED'` instead.
- **Rules the database doesn't check:** some rules have to be checked in the backend code. They're listed at the top of `0003_live_sessions.up.sql` and in the "Rules the backend has to check" section of `ER_Diagram.md`.

## Quizzes without a class

Since V3, every quiz belongs to a class. Migration `0008` fills in `quiz.class_id` on its own when a quiz was played in exactly one class. Every other old quiz stays empty, and **someone has to decide** what happens to it before V3 goes live.

1. List the quizzes that still have no class:

   ```sql
   SELECT quiz.quiz_id, quiz.author_id, account.email, quiz.status, quiz.created_at
   FROM quiz
   JOIN account ON account.account_id = quiz.author_id
   WHERE quiz.class_id IS NULL
   ORDER BY quiz.author_id, quiz.quiz_id;
   ```

2. For each one, either:
   - **give it a class**, preferably one its author is an active member of:

     ```sql
     UPDATE quiz SET class_id = 12 WHERE quiz_id = 34;
     ```

   - **or park it in a legacy class** if no real class needs it. Make one archived class to hold old quizzes, then move them into it. Archived classes can't get new quizzes or class sessions, but the history stays:

     ```sql
     INSERT INTO class (name, created_by_id, join_code, joining_open, archived_at)
     VALUES ('Pre-V3 quizzes', 1, NULL, FALSE, UTC_TIMESTAMP(3));

     UPDATE quiz SET class_id = LAST_INSERT_ID(), status = 'ARCHIVED'
     WHERE quiz_id IN (34, 35);
     ```

     Use a faculty account's ID for `created_by_id`, and run the `UPDATE` right after the `INSERT` so `LAST_INSERT_ID()` still points at the new class.

3. Once the first query returns no rows, a later migration can make `quiz.class_id` required.

Until then, a quiz without a class is visible only to its author.
