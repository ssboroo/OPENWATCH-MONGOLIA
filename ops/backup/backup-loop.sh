#!/bin/sh
set -eu
umask 077
while :; do
  file="/backups/openwatch-$(date -u +%Y%m%dT%H%M%SZ).dump"
  if pg_dump -Fc > "$file.tmp" && pg_restore --list "$file.tmp" >/dev/null; then
    mv "$file.tmp" "$file"
    sha256sum "$file" > "$file.sha256"
    touch /backups/last-success
    if [ "${RECORD_BACKUP_EVIDENCE:-false}" = true ]; then
      psql -v ON_ERROR_STOP=1 -c "INSERT INTO system_state (name,value,updated_at) VALUES ('backup','{\"status\":\"completed\"}',CURRENT_TIMESTAMP) ON CONFLICT (name) DO UPDATE SET value=EXCLUDED.value,updated_at=EXCLUDED.updated_at;" >/dev/null
    fi
    if [ "${RESTORE_CHECK_ENABLED:-false}" = true ]; then
      if sh /ops/restore-check.sh "$file"; then
        psql -v ON_ERROR_STOP=1 -c "INSERT INTO system_state (name,value,updated_at) VALUES ('restore_check','{\"status\":\"completed\"}',CURRENT_TIMESTAMP) ON CONFLICT (name) DO UPDATE SET value=EXCLUDED.value,updated_at=EXCLUDED.updated_at;" >/dev/null
      else
        psql -v ON_ERROR_STOP=1 -c "INSERT INTO system_state (name,value,updated_at) VALUES ('restore_check','{\"status\":\"failed\"}',CURRENT_TIMESTAMP) ON CONFLICT (name) DO UPDATE SET value=EXCLUDED.value,updated_at=EXCLUDED.updated_at;" >/dev/null
      fi
    fi
    printf '{"service":"backup","status":"completed"}\n'
    find /backups/openwatch-*.dump* -type f -mtime +14 -delete || printf '{\"service\":\"backup_retention\",\"status\":\"failed\"}\n' >&2
  else
    rm -f "$file.tmp"
    if [ "${RECORD_BACKUP_EVIDENCE:-false}" = true ]; then
      psql -v ON_ERROR_STOP=1 -c "INSERT INTO system_state (name,value,updated_at) VALUES ('backup','{\"status\":\"failed\"}',CURRENT_TIMESTAMP) ON CONFLICT (name) DO UPDATE SET value=EXCLUDED.value,updated_at=EXCLUDED.updated_at;" >/dev/null || true
    fi
    printf '{"service":"backup","status":"failed"}\n' >&2
  fi
  sleep "${BACKUP_INTERVAL_SECONDS:-86400}"
done
