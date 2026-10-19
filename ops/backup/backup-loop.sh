#!/bin/sh
set -eu
umask 077
while :; do
  file="/backups/openwatch-$(date -u +%Y%m%dT%H%M%SZ).dump"
  if pg_dump -Fc > "$file.tmp" && pg_restore --list "$file.tmp" >/dev/null; then
    mv "$file.tmp" "$file"
    touch /backups/last-success
    printf '{"service":"backup","status":"completed"}\n'
    find /backups -name 'openwatch-*.dump' -mtime +14 -delete
  else
    rm -f "$file.tmp"
    printf '{"service":"backup","status":"failed"}\n' >&2
  fi
  sleep "${BACKUP_INTERVAL_SECONDS:-86400}"
done
