#!/bin/sh
# Isolated restoration only. Never replaces the live database.
set -eu
file="${1:?Pass /backups/openwatch-date.dump}"
case "$file" in /backups/openwatch-*.dump) ;; *) echo 'Backup path rejected' >&2; exit 1;; esac
[ "$(dirname "$file")" = /backups ] || exit 1
checkdb="ow_restore_$(date +%s)_$$"
createdb "$checkdb"
trap 'dropdb "$checkdb"' EXIT HUP INT TERM
pg_restore --dbname="$checkdb" --exit-on-error < "$file"
psql --dbname="$checkdb" -v ON_ERROR_STOP=1 -c 'SELECT count(*) FROM articles;' -c 'SELECT count(*) FROM public_reports;'
echo '{"service":"restore-check","status":"completed"}'
