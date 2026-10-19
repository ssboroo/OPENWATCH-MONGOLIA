from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = 'postgresql+psycopg://openwatch:openwatch@db/openwatch'
    @field_validator('database_url', mode='before')
    @classmethod
    def postgres_driver(cls, value):
        # Railway exports a standard Postgres URL; this app installs psycopg 3.
        if isinstance(value,str):
            for prefix in ('postgres://','postgresql://'):
                if value.startswith(prefix):return 'postgresql+psycopg://'+value[len(prefix):]
        return value

    admin_token: str = ''
    allowed_hosts: str = ''
    max_feed_bytes: int = 2_000_000
    collection_interval: int = 900
    retention_days: int = 90
    ai_enabled: bool = False
    ollama_url: str = 'http://ollama:11434'
    ollama_model: str = 'qwen3:8b'
    embedding_model: str = 'bge-m3'
    ai_timeout: float = 90
    ai_retries: int = 1
    ai_batch_size: int = 10
    ai_retry_seconds: int = 1800
    semantic_threshold: float = 0.88
    worker_tick_seconds: int = 60
    cluster_candidates: int = 150
    collection_concurrency: int = 4
    source_timeout_seconds: int = 40
    catalog_bootstrap: bool = False
    catalog_concurrency: int = 8
    catalog_site_timeout: int = 35
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings()
