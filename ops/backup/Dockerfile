FROM postgres:16-alpine
RUN mkdir -p /backups /ops && chown postgres:postgres /backups /ops
COPY backup-loop.sh /ops/backup-loop.sh
COPY restore-check.sh /ops/restore-check.sh
USER root
CMD ["sh", "-c", "chown postgres:postgres /backups && exec su-exec postgres sh /ops/backup-loop.sh"]
