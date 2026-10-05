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
- **Sessions and groups:** leave `live_session.group_id` empty for the MVP.
- **Deleting quizzes:** you can't delete a quiz that has already been played. Set its `status` to `'ARCHIVED'` instead.
- **Rules the database doesn't check:** some rules have to be checked in the backend code. They're listed at the top of `0003_live_sessions.up.sql` and in the "Rules the backend has to check" section of `ER_Diagram.md`.
