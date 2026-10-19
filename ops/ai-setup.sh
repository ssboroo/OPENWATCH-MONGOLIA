#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull qwen3:8b
docker compose exec ollama ollama pull bge-m3
printf 'Models downloaded. Set AI_ENABLED=true in .env, then recreate backend and worker.\n'
