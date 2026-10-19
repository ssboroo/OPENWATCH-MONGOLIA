FROM ollama/ollama:latest
RUN mkdir -p /models/models && chown -R 10001:10001 /models
ENV OLLAMA_MODELS=/models/models HOME=/tmp
USER 10001:10001
