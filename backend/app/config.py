from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = 'postgresql+psycopg://openwatch:openwatch@db/openwatch'
    admin_token: str = ''
    allowed_hosts: str = ''
    max_feed_bytes: int = 2_000_000
    collection_interval: int = 900
    retention_days: int = 90
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')

settings = Settings()
