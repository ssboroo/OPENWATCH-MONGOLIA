#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python -m pip install --upgrade pip==26.2.1
python -m pip install -r backend/requirements-dev.txt
(cd backend && python -m pytest -q)
pip-audit -r backend/requirements-dev.txt
(cd frontend && npm ci && npm test && BACKEND_URL=http://127.0.0.1:8765 npm run build && npm audit --omit=dev)
python ops/http-e2e.py
for file in ops/*.sh ops/backup/*.sh; do sh -n "$file"; done
# Full container/database/runtime checks require a Docker-capable runner.
if command -v docker >/dev/null 2>&1; then
  docker compose config --quiet
  docker compose build
fi
