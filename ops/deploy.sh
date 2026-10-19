#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 ops/check-config.py
docker compose config --quiet
docker compose build
docker compose up -d db
docker compose run --rm migrate
docker compose up -d
docker compose ps
