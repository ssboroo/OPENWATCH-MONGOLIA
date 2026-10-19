#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
umask 077
mkdir -p backups
file="backups/openwatch-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker compose exec -T db pg_dump -U openwatch -d openwatch -Fc > "$file.tmp"
mv "$file.tmp" "$file"
find backups -name 'openwatch-*.dump' -mtime +14 -delete
printf 'Saved %s\n' "$file"
