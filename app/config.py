from functools import lru_cache
from pydantic import AnyHttpUrl, BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class RateCap(BaseModel):
    max_refund: int = 5_000
    max_quote: int = 250_000


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str | None = None
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/nova"
    elastic_url: AnyHttpUrl | str = "http://localhost:9200"
    redis_url: str = "redis://localhost:6379/0"
    playwright_browse: bool = False
    embedding_provider: str = "openai"
    rerank_enabled: bool = True
    max_refund_cap: int = 5_000
    max_quote_cap: int = 250_000
    default_timezone: str = "America/Los_Angeles"
    api_host: str = "http://localhost:8000"
    log_level: str = "INFO"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    def rate_cap(self) -> RateCap:
        return RateCap(max_refund=self.max_refund_cap, max_quote=self.max_quote_cap)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
