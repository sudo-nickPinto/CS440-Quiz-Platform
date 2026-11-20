#!/bin/sh
# Encrypts the tables of a QuizBurg database that was created before
# encryption at rest was turned on (docs/DEPLOYMENT.md). Safe to run again:
# tables that are already encrypted are skipped. Run it once after
# redeploying with the encrypted MySQL image:
#
#   docker compose --env-file deploy/.env -f compose.yaml -f compose.mysql.yaml \
#     exec -T db sh < deploy/mysql/encrypt-existing.sh
#
# It runs inside the db container and uses its MYSQL_ROOT_PASSWORD and
# MYSQL_DATABASE. Each ALTER rewrites the table, so expect a short pause on
# large tables; do it when no live session is running.
set -eu

export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"
db="$MYSQL_DATABASE"
run() { mysql -uroot -N -B -e "$1"; }

# New tables in this database default to encrypted from now on.
run "ALTER DATABASE \`$db\` DEFAULT ENCRYPTION='Y';"

# Every table that isn't encrypted yet.
tables=$(run "SELECT t.TABLE_NAME
  FROM information_schema.TABLES t
  JOIN information_schema.INNODB_TABLESPACES s
    ON s.NAME = CONCAT(t.TABLE_SCHEMA, '/', t.TABLE_NAME)
  WHERE t.TABLE_SCHEMA = '$db' AND t.TABLE_TYPE = 'BASE TABLE'
    AND s.ENCRYPTION = 'N';")
for table in $tables; do
  echo "Encrypting $db.$table"
  run "ALTER TABLE \`$db\`.\`$table\` ENCRYPTION='Y';"
done

# MySQL's own system tables (accounts, password hashes, privileges).
run "ALTER TABLESPACE mysql ENCRYPTION='Y';"

left=$(run "SELECT COUNT(*) FROM information_schema.INNODB_TABLESPACES
  WHERE (NAME LIKE '$db/%' OR NAME = 'mysql') AND ENCRYPTION = 'N';")
echo "Done. Unencrypted tables left: $left"
