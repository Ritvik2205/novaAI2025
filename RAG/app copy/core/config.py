from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ensure environment variables from .env are loaded before settings instantiation.
load_dotenv(dotenv_path=".env", override=False)


class Settings(BaseSettings):
    """Central configuration for the RAG service."""

    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__")

    app_name: str = Field(default="Venture RAG Service")
    log_level: str = Field(default="INFO")

    openai_api_key: SecretStr = Field(default=SecretStr(""), alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4.1-mini")
    openai_embedding_model: str = Field(default="text-embedding-3-large")

    vector_store: str = Field(
        default="chroma",
        alias="VECTOR_STORE",
        description="Vector store backend to use (chroma, pinecone, memory).",
    )
    chroma_persist_path: str = Field(
        default="storage/chroma",
        alias="CHROMA_PERSIST_PATH",
        description="Directory for Chroma persistence when vector_store='chroma'.",
    )

    pinecone_api_key: SecretStr = Field(default=SecretStr(""), alias="PINECONE_API_KEY")
    pinecone_environment: str = Field(default="us-east-1")
    pinecone_index: str = Field(default="venture-rag")
    default_namespace: str = Field(default="default", alias="PINECONE_NAMESPACE")
    pinecone_cloud: str = Field(default="aws")
    pinecone_region: str = Field(default="us-east-1")

    default_base_url: Optional[HttpUrl] = Field(
        default=None,
        description="Optional default site to crawl when ingesting without explicit URL.",
    )

    crawler_max_pages: int = Field(default=2000)
    crawler_max_depth: int = Field(default=4)
    crawler_concurrency: int = Field(default=5)
    crawler_timeout: float = Field(default=15.0)

    reranker_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="Any sentence-transformer compatible reranker model id.",
    )
    chunk_size: int = Field(default=600)
    chunk_overlap: int = Field(default=80)
    max_retriever_results: int = Field(default=15)
    max_reranked_results: int = Field(default=6)
    max_generation_tokens: int = Field(default=600)

    guardrails_enabled: bool = Field(default=True, alias="GUARDRAILS_ENABLED")
    guardrails_model: str = Field(
        default="gpt-4o-mini",
        alias="GUARDRAILS_MODEL",
        description="LLM used by NeMo Guardrails when classifying topic intent.",
    )
    guardrails_model_engine: str = Field(
        default="openai",
        alias="GUARDRAILS_MODEL_ENGINE",
        description="Provider engine name for the guardrails LLM.",
    )
    guardrails_dataset_path: str = Field(
        default="data/topic_gate_dataset.csv",
        alias="GUARDRAILS_DATASET_PATH",
        description="CSV file with labeled on/off-topic examples for the guardrails intent gate.",
    )
    guardrails_examples_per_label: int = Field(
        default=120,
        alias="GUARDRAILS_EXAMPLES_PER_LABEL",
        description="Number of examples to feed each label when building the guardrails classifier.",
    )

    celery_broker_url: str = Field(default="redis://localhost:6379/0")
    celery_result_backend: str = Field(default="redis://localhost:6379/0")


@lru_cache
def get_settings() -> Settings:
    return Settings()
