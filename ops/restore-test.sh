#!/bin/sh
# Restore ONLY into isolated openwatch_restore_check database; never replaces production.
set -eu
cd "$(dirname "$0")/.."
file="${1:?Usage: sh ops/restore-test.sh backups/file.dump}"
docker compose exec -T db createdb -U openwatch openwatch_restore_check
trap 'docker compose exec -T db dropdb -U openwatch openwatch_restore_check' EXIT
docker compose exec -T db pg_restore -U openwatch -d openwatch_restore_check --exit-on-error < "$file"
docker compose exec -T db psql -U openwatch -d openwatch_restore_check -c 'SELECT count(*) FROM articles;'
