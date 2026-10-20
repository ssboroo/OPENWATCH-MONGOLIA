FROM ollama/ollama:latest
RUN apt-get update && apt-get install -y --no-install-recommends gosu && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /models/models /app && chown -R 10001:10001 /models /app
COPY start.sh /app/start.sh
ENV OLLAMA_MODELS=/models/models HOME=/tmp OLLAMA_HOST=:: OLLAMA_NO_CLOUD=1 OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=2
# The inference API is private-network only; no public domain is configured.
USER root
ENTRYPOINT ["/bin/sh", "/app/start.sh"]
