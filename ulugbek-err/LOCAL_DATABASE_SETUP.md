# Setting up your own database

This guide gets a MySQL database running on your laptop, with all our tables in it. It takes about 10 minutes.

Everyone should have their own database for day-to-day work. That way you can add test data, break things and start over without affecting anyone else.

We use Docker to run MySQL. You don't have to install MySQL itself, and the steps are the same on Mac and Windows.

## What you'll end up with

| Setting | Value |
|---|---|
| Host | `127.0.0.1` |
| Port | `3307` |
| Database | `quizdb` |
| Username | `root` |
| Password | `devpass` |

The password is simple on purpose. This database only exists on your laptop and only holds test data.

## Before you start

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and open it. Wait until it says it's running.
2. Pull the latest code:

   ```bash
   git checkout main
   git pull origin main
   ```

3. Open a terminal in the main project folder (`CS440-Quiz-Platform`). On Windows, use PowerShell.

Run every command in this guide from that folder.

## Step 1: Start MySQL

```bash
docker run -d --name quizdb-dev -e MYSQL_ROOT_PASSWORD=devpass -e MYSQL_DATABASE=quizdb -p 3307:3306 mysql:8.0
```

The first time, this downloads MySQL, which can take a few minutes. After it finishes, **wait about 30 seconds** for MySQL to start up.

## Step 2: Create the tables

Our tables are created by the SQL files in `ulugbek-err/migrations`. First copy those files into the database container:

```bash
docker cp ulugbek-err/migrations/. quizdb-dev:/migrations
```

Then run them:

```bash
docker exec quizdb-dev sh -c 'for f in /migrations/*.up.sql; do echo Running $f; mysql -uroot -pdevpass quizdb < $f || exit 1; done'
```

You should see one `Running ...` line for each migration file.

Two things that are normal:

- A warning that says `Using a password on the command line interface can be insecure`. You can ignore it.
- An error that says `Can't connect to local MySQL server`. This means MySQL hasn't finished starting. Wait 20 seconds and run the command again.

## Step 3: Check that it worked

```bash
docker exec quizdb-dev mysql -uroot -pdevpass quizdb -e "SHOW TABLES; SELECT version FROM schema_migrations;"
```

You should see 16 tables (`account`, `quiz`, `live_session` and so on), and one row for each migration that has been run.

## Step 4: Point the backend at your database

If you don't have a `backend/.env` file yet, make one by copying the example:

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and set the database lines to this:

```text
DB_HOST=127.0.0.1
DB_PORT=3307
DB_DATABASE=quizdb
DB_USERNAME=root
DB_PASSWORD=devpass
```

You also need the Auth0 values in that file. See [`docs/AUTH.md`](../docs/AUTH.md) for those.

Now start the backend the way you normally do (see the main README), and open the health check. If you run the backend on port 8001:

```text
http://127.0.0.1:8001/health
```

It should say `"database":"ok"`.

## Looking at your data

**From the terminal:**

```bash
docker exec -it quizdb-dev mysql -uroot -pdevpass quizdb
```

This opens a MySQL prompt where you can type SQL, for example `SELECT * FROM account;`. Type `exit` to leave.

**From MySQL Workbench or another app:** make a new connection using the values in the table at the top of this guide.

## Day-to-day use

Your database keeps its data when you stop it or restart your laptop.

| What you want | Command |
|---|---|
| Stop the database | `docker stop quizdb-dev` |
| Start it again | `docker start quizdb-dev` |
| See if it's running | `docker ps` |

If the backend suddenly can't connect, the database is probably stopped. Open Docker Desktop and run `docker start quizdb-dev`.

## When someone adds a new migration

When a new file shows up in `ulugbek-err/migrations` (for example `0006_...`), your database needs it too.

1. Pull the latest code.
2. Copy the files into the container again:

   ```bash
   docker cp ulugbek-err/migrations/. quizdb-dev:/migrations
   ```

3. Run **only the new file**. Replace the file name with the real one:

   ```bash
   docker exec quizdb-dev sh -c 'mysql -uroot -pdevpass quizdb < /migrations/0006_example.up.sql'
   ```

Don't run the old files again. They'll fail because those tables already exist.

Not sure which ones you've already run? This shows you:

```bash
docker exec quizdb-dev mysql -uroot -pdevpass quizdb -e "SELECT version FROM schema_migrations;"
```

## Starting over

If your database gets into a bad state, the easiest fix is to delete it and make a new one. **This deletes all the data in it.**

```bash
docker rm -f quizdb-dev
```

Then do Step 1 and Step 2 again.

## A test database for the backend tests (optional)

Some backend tests need a real MySQL database. They must use a separate database with "test" in its name, so they can never touch your normal data.

Create it and add the tables:

```bash
docker exec quizdb-dev sh -c 'mysql -uroot -pdevpass -e "CREATE DATABASE IF NOT EXISTS quizdb_test" && for f in /migrations/*.up.sql; do mysql -uroot -pdevpass quizdb_test < $f || exit 1; done'
```

Then run the tests from the `backend` folder, with your virtual environment turned on.

Mac or Linux:

```bash
TEST_DATABASE_URL='mysql+pymysql://root:devpass@127.0.0.1:3307/quizdb_test?charset=utf8mb4' python -m pytest
```

Windows PowerShell:

```powershell
$env:TEST_DATABASE_URL = 'mysql+pymysql://root:devpass@127.0.0.1:3307/quizdb_test?charset=utf8mb4'
python -m pytest
```

Without `TEST_DATABASE_URL`, those tests are skipped.

When a new migration is added, run it on `quizdb_test` too. Use the same command as in "When someone adds a new migration", but with `quizdb_test` instead of `quizdb`.

## If something goes wrong

- **`Cannot connect to the Docker daemon`**: Docker Desktop isn't open. Open it and wait until it's running.
- **`The container name "/quizdb-dev" is already in use`**: you already created the database. Run `docker start quizdb-dev` instead of Step 1.
- **`port is already allocated`**: something else on your laptop is using port 3307. Use a different port, like 3308: change `-p 3307:3306` to `-p 3308:3306` in Step 1, and use `DB_PORT=3308` in `backend/.env`.
- **`Table 'account' already exists`**: you ran a migration twice. Nothing is broken. If you're not sure what state your database is in, see "Starting over".

## If you can't use Docker

You can install MySQL 8 straight onto your laptop instead:

- **Mac:** `brew install mysql@8.0`
- **Windows:** download the MySQL Installer from [dev.mysql.com/downloads](https://dev.mysql.com/downloads/installer/)

Then create a database called `quizdb` and run the migration files with the `mysql` commands in [`migrations/README.md`](migrations/README.md). Your port will be `3306` instead of `3307`, and your username and password will be whatever you chose when installing.

Docker is the way we've tested, so use it if you can.
