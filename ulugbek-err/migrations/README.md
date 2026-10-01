# Database migrations

These SQL files create our database tables. The tables match the diagram in [`../ER_Diagram.md`](../ER_Diagram.md).

| File | What it creates |
|---|---|
| `0001_accounts_and_groups` | `schema_migrations`, `account`, `course_group`, `group_membership` |
| `0002_quizzes` | `quiz`, `quiz_collaborator`, `quiz_group`, `quiz_version`, `question`, `answer_choice` |
| `0003_live_sessions` | `live_session`, `session_participant`, `session_question`, `response`, `result` |
| `0004_account_identity` | `account_identity` (one account, several Auth0 logins); copies existing `account.auth0_sub` values into it |

Each migration comes in two files:

- `.up.sql` creates the tables.
- `.down.sql` deletes them.

These work on MySQL 5.7 and newer. The `CHECK` rules only work on MySQL 8.0.16 or newer, and older versions skip them without any error. To see which version you have, run `SELECT VERSION();`.

## Before you run anything

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

If you want to try things without touching the shared database, you can run a test database in Docker:

```bash
docker run -d --name quizdb-test -e MYSQL_ROOT_PASSWORD=test -e MYSQL_DATABASE=quizdb -p 3307:3306 mysql:8.0
# Wait about 20 seconds for MySQL to start, then:
for f in ulugbek-err/migrations/*.up.sql; do
  mysql -h 127.0.0.1 -P 3307 -u root -ptest quizdb < "$f" || break
done
docker rm -f quizdb-test   # deletes the test database when you're done
```

## Notes for backend code

- **Times:** every time column is saved in UTC, so the backend should always save UTC times.
- **Finding a session by its join code:** use the `active_join_code` column, not `join_code`. `active_join_code` is empty once a session ends, which lets old codes be used again.
- **Reordering questions or answers:** two questions in the same version can't have the same position, and neither can two answers to the same question. To swap two of them, move one to a temporary position first, or renumber them all in one `UPDATE`.
- **Deleting quizzes:** you can't delete a quiz that has already been played. Set its `status` to `'ARCHIVED'` instead.
- **Rules the database doesn't check:** some rules have to be checked in the backend code. They're listed at the top of `0003_live_sessions.up.sql` and in the "Rules the backend has to check" section of `ER_Diagram.md`.
