#!/bin/sh
set -eu
if [ "$(id -u)" = 0 ]; then
  mkdir -p "${OLLAMA_MODELS:-/models/models}"
  chown -R 10001:10001 /models
  exec gosu 10001:10001 /bin/sh "$0"
fi
# Numeric UID has no passwd entry; gosu otherwise sets HOME to /.
export HOME=/tmp/openwatch-ollama
mkdir -p "$HOME"
mkdir -p "${OLLAMA_MODELS:-/models/models}"
ollama serve &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true; wait "$server_pid" || true' TERM INT EXIT
# CLI connects to local IPv4 even when the server listens on IPv6 wildcard.
export OLLAMA_HOST=http://127.0.0.1:11434
while ! ollama list >/dev/null 2>&1; do
  kill -0 "$server_pid" || exit 1
  sleep 2
done
for model in "${GENERATION_MODEL:-qwen3:8b}" "${EMBEDDING_MODEL:-bge-m3}"; do
  echo "OPENWATCH downloading model: $model"
  ollama pull "$model" > /tmp/model-pull.log 2>&1 &
  pull_pid=$!
  while kill -0 "$pull_pid" 2>/dev/null; do
    echo "OPENWATCH model download in progress: $model"
    sleep 10
  done
  if ! wait "$pull_pid"; then tail -c 1000 /tmp/model-pull.log; exit 1; fi
  echo "OPENWATCH model installed: $model"
done
echo 'OPENWATCH models ready; inference will be validated by the worker'
wait "$server_pid"
