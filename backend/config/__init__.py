"""
Configuration management for the agentic CRM backend.
"""

from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseModel):
    """Settings for individual OpenRouter models used by the agents."""

    name: str = Field(..., description="Model slug, e.g. openrouter/anthropic/claude-3-haiku")
    temperature: float = Field(0.2, ge=0, le=2.0)
    max_tokens: int = Field(1200, gt=0)


class Settings(BaseSettings):
    """Application level configuration pulled from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        arbitrary_types_allowed=True,
    )

    environment: str = Field(default="development")
    base_data_dir: Path = Field(default=Path("backend/data"))
    uploads_dir: Path = Field(default=Path("backend/static/uploads"))

    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: HttpUrl = Field(
        default="https://openrouter.ai/api/v1/chat/completions",
        alias="OPENROUTER_BASE_URL",
    )
    default_model: ModelConfig = Field(
        default_factory=lambda: ModelConfig(
            name="openai/gpt-5-chat",
            temperature=0.3,
            max_tokens=1600,
        )
    )
    high_intent_model: ModelConfig = Field(
        default_factory=lambda: ModelConfig(
            name="openai/gpt-5-chat",
            temperature=0.1,
            max_tokens=1800,
        )
    )

    agentuity_api_key: str = Field(default="", alias="AGENTUITY_API_KEY")
    agentuity_base_url: Optional[HttpUrl] = Field(
        default="https://api.agentuity.com/v1",
        alias="AGENTUITY_BASE_URL",
    )

    calendar_provider: str = Field(default="local", alias="CALENDAR_PROVIDER")
    calendar_credentials_path: Optional[Path] = Field(default=None)

    chroma_persist_path: Path = Field(
        default=Path("backend/data/vector_store"),
        alias="CHROMA_PERSIST_PATH",
    )
    embedder_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")
    chunk_size: int = Field(default=400)
    chunk_overlap: int = Field(default=50)

    crawler_max_pages: int = Field(default=250)
    crawler_max_depth: int = Field(default=3)
    crawler_concurrency: int = Field(default=5)
    crawler_timeout: float = Field(default=15.0)

    # Safety and guardrail options
    enable_guardrails: bool = Field(default=True)
    blocked_domains: List[str] = Field(default_factory=list)

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""

    settings = Settings()
    settings.base_data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.chroma_persist_path.mkdir(parents=True, exist_ok=True)
    return settings
