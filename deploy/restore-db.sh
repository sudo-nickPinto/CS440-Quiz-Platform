#!/usr/bin/env bash
# Restores an encrypted backup made by deploy/backup-db.sh into the
# Docker-hosted database. It replaces the database's current contents.
#
#   deploy/restore-db.sh backups/quizburg-<time>.sql.gz.enc
#
# Uses the passphrase in deploy/backup-passphrase (or BACKUP_PASSPHRASE_FILE);
# COMPOSE overrides how Docker Compose is called, as in backup-db.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

file=${1:?usage: deploy/restore-db.sh <backup .sql.gz.enc file>}
pass_file=${BACKUP_PASSPHRASE_FILE:-deploy/backup-passphrase}
compose=${COMPOSE:-docker compose --env-file deploy/.env -f compose.yaml -f compose.mysql.yaml}

openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$pass_file" -in "$file" \
  | gunzip \
  | $compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot'

echo "Restored $file"
