#!/usr/bin/env bash
# Encrypted backup of the Docker-hosted QuizBurg database (compose.mysql.yaml).
#
#   deploy/backup-db.sh [output-dir]            # default: backups/
#
# Writes backups/quizburg-<UTC time>.sql.gz.enc: a mysqldump, gzipped, then
# encrypted (AES-256, PBKDF2) with the passphrase in deploy/backup-passphrase
# (or BACKUP_PASSPHRASE_FILE). A plain dump would undo encryption at rest, so
# this script never writes one. Keep the passphrase somewhere other than the
# server and the backups; restore with deploy/restore-db.sh.
#
# COMPOSE overrides how Docker Compose is called (default: the production
# files with deploy/.env).
set -euo pipefail
cd "$(dirname "$0")/.."

out_dir=${1:-backups}
pass_file=${BACKUP_PASSPHRASE_FILE:-deploy/backup-passphrase}
compose=${COMPOSE:-docker compose --env-file deploy/.env -f compose.yaml -f compose.mysql.yaml}

if [ ! -s "$pass_file" ]; then
  echo "No passphrase in $pass_file. Create one first, for example:" >&2
  echo "  openssl rand -base64 48 > $pass_file && chmod 600 $pass_file" >&2
  exit 1
fi

umask 077
mkdir -p "$out_dir"
file="$out_dir/quizburg-$(date -u +%Y%m%dT%H%M%SZ).sql.gz.enc"
# A failed dump must not leave a partial file that looks like a backup.
trap 'rm -f "$file"' ERR

$compose exec -T db sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot \
    --single-transaction --routines --triggers --no-tablespaces \
    --databases "$MYSQL_DATABASE"' \
  | gzip \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass "file:$pass_file" -out "$file"

echo "Encrypted backup written to $file"
