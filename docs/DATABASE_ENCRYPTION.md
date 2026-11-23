# Database encryption at rest

With the Docker-hosted MySQL (`compose.mysql.yaml`), QuizBurg's data is
encrypted on disk. Someone who gets a copy of the database files, the data
volume or a backup, without the key, can't read names, emails, quizzes or
scores from them.

## What is and isn't protected

| Situation | Protected? |
|---|---|
| A copy or snapshot of the `mysql-data` volume leaks on its own | Yes. Tables, redo/undo logs and binary logs are encrypted, and the key is in the separate `mysql-keyring` volume. |
| The whole server disk is taken | No, on a single Docker node: both volumes are on that disk, so the key goes with the data. Only storage encryption by the host (ask Reclaim) covers this. |
| A backup made with `deploy/backup-db.sh` leaks | Yes. Backups are encrypted with a passphrase. |
| Someone logs in to MySQL with a valid password | No. MySQL decrypts for any logged-in user, so keep the database off the internet and its passwords secret. |
| Someone takes over the server itself (both volumes and the running containers) | No. They have the key too. |

This is encryption at rest. It complements the deployment's other
protections: the database is only reachable on the private Docker network (it
publishes no port), the app connects as its own `quiz_app` user, and secrets
live in `deploy/.env`, which isn't committed.

## How it works

- `deploy/mysql/Dockerfile` builds `mysql:8.0` with MySQL's
  `component_keyring_file`, which holds the master key in
  `/var/lib/mysql-keyring/component_keyring_file`.
- That path is the separate `mysql-keyring` volume, not `mysql-data`.
- `compose.mysql.yaml` starts MySQL with:
  - `--default-table-encryption=ON`: new databases and tables are encrypted.
  - `--table-encryption-privilege-check=ON`: the app user can't create an
    unencrypted table.
  - `--innodb-redo-log-encrypt`, `--innodb-undo-log-encrypt`,
    `--binlog-encryption`: the logs that record recent changes are encrypted
    too.
- The app needs no changes. It reads and writes normally.

## New deployment

Nothing extra is needed. Follow "Reclaim with Docker-hosted MySQL" in
[DEPLOYMENT.md](DEPLOYMENT.md). The first `up --build` builds the MySQL image,
creates the key, and every table the migrations create is encrypted.

Then back up the key (below) before entering real course data.

## Existing deployment (created before this change)

Existing tables stay unencrypted until they're converted, once:

1. Take a backup first (`deploy/backup-db.sh`, below).
2. Pull this change and redeploy with the usual
   `docker compose --env-file deploy/.env -f compose.yaml -f compose.mysql.yaml up --build -d`.
   The new `mysql-keyring` volume is created and MySQL starts with encryption on.
3. Encrypt the existing tables (and MySQL's own system tables). Run it when no
   live session is running, since each table is rewritten:

   ```bash
   docker compose --env-file deploy/.env -f compose.yaml -f compose.mysql.yaml \
     exec -T db sh < deploy/mysql/encrypt-existing.sh
   ```

   It prints each table it encrypts and ends with
   `Unencrypted tables left: 0`. Running it again is safe.
4. Back up the key (below).

## Back up the key

**Without the key file the data can't be read by anyone, including you.** If
the `mysql-keyring` volume is lost, the database is lost. Copy the key off the
server once, after the first start, and keep it somewhere safe and separate
from the database backups (a password manager or another machine):

```bash
docker compose --env-file deploy/.env -f compose.yaml -f compose.mysql.yaml \
  exec -T db cat /var/lib/mysql-keyring/component_keyring_file > quizburg-mysql-keyring
```

To restore it onto a new server, put the file back into the `mysql-keyring`
volume (owned by the container's `mysql` user, mode 600) before starting `db`.

## Encrypted backups

A plain `mysqldump` would write the data out unencrypted, so use the scripts:

```bash
# Once: a random passphrase. Keep a copy off the server, apart from the backups.
openssl rand -base64 48 > deploy/backup-passphrase && chmod 600 deploy/backup-passphrase

# Each backup: backups/quizburg-<UTC time>.sql.gz.enc (gzip + AES-256)
deploy/backup-db.sh

# Restore one (replaces the database's current contents)
deploy/restore-db.sh backups/quizburg-20261120T185935Z.sql.gz.enc
```

`backups/` and `deploy/backup-passphrase` are ignored by Git. A backup can be
restored without the MySQL key file (it's a dump, not the encrypted files), so
the passphrase is what protects it.

## Separate MySQL node

With "Reclaim with a separate MySQL node" ([DEPLOYMENT.md](DEPLOYMENT.md)) the
MySQL server isn't configured by this repository. Ask Reclaim whether the
node's storage is encrypted, or enable a keyring and `default_table_encryption`
on that node the same way. The encrypted backup scripts assume the Docker
overlay.

## Checking it

```bash
# Every QuizBurg table should say Y.
docker compose --env-file deploy/.env -f compose.yaml -f compose.mysql.yaml \
  exec db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -uroot -e \
  "SELECT NAME, ENCRYPTION FROM information_schema.INNODB_TABLESPACES WHERE NAME LIKE \"$MYSQL_DATABASE/%\";"'
```

Tested with MySQL 8.0.46: the backend's full test suite (including the MySQL
integration tests) passes on the encrypted database, a student's name can't be
found in the raw table file, redo log or binary log, and MySQL won't start on
the data volume without the right key.
