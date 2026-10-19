FROM postgres:16-alpine
RUN mkdir -p /backups /ops && chown postgres:postgres /backups /ops
COPY backup-loop.sh /ops/backup-loop.sh
COPY restore-check.sh /ops/restore-check.sh
USER postgres
CMD ["sh", "/ops/backup-loop.sh"]
