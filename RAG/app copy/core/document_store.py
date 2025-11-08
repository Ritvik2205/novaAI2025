import logging
from functools import lru_cache
from pathlib import Path
from typing import Optional

from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.document_stores.types import DocumentStore

try:  # pragma: no cover - optional integration
    from haystack_integrations.document_stores.chroma import ChromaDocumentStore
except ImportError:  # pragma: no cover
    ChromaDocumentStore = None  # type: ignore

try:  # pragma: no cover - optional integration
    from haystack_integrations.document_stores.pinecone import PineconeDocumentStore
except ImportError:  # pragma: no cover
    PineconeDocumentStore = None  # type: ignore

from .config import get_settings

EMBEDDING_DIMENSION = 3072  # OpenAI text-embedding-3-large output size
logger = logging.getLogger(__name__)


@lru_cache(maxsize=32)
def get_document_store(namespace: Optional[str] = None) -> DocumentStore:
    """Return the configured document store instance."""
    settings = get_settings()
    backend = settings.vector_store.lower()
    effective_namespace = namespace or settings.default_namespace

    if backend == "pinecone":
        if not settings.pinecone_api_key.get_secret_value():
            raise ValueError("Pinecone selected but PINECONE_API_KEY not provided.")
        return _build_pinecone_store(
            index=settings.pinecone_index,
            namespace=effective_namespace,
            dimension=EMBEDDING_DIMENSION,
            metric="cosine",
        )

    if backend == "chroma":
        try:
            return _build_chroma_store(
                persist_path=settings.chroma_persist_path,
                collection_name=effective_namespace,
            )
        except ImportError as exc:
            raise RuntimeError(
                "Chroma backend requested but the haystack-integrations package is missing. "
                "Install it via `pip install \"haystack-ai[chromadb]\"`."
            ) from exc

    # Fallback to in-memory for local development or tests.
    return _build_in_memory_store(collection_name=effective_namespace)


def _build_chroma_store(persist_path: str, collection_name: str) -> ChromaDocumentStore:
    if ChromaDocumentStore is None:  # pragma: no cover - configuration guard
        raise ImportError(
            "ChromaDocumentStore requested but haystack-integrations is not installed. "
            "Install via `pip install \"haystack-ai[chromadb]\"`."
        )
    Path(persist_path).mkdir(parents=True, exist_ok=True)
    return ChromaDocumentStore(
        collection_name=collection_name,
        persist_path=persist_path,
        embedding_function="default",
    )


def _build_in_memory_store(collection_name: str) -> InMemoryDocumentStore:
    return InMemoryDocumentStore(
        embedding_similarity_function="cosine",
        index=f"document-{collection_name}",
    )


def _build_pinecone_store(
    *,
    index: str,
    namespace: str,
    dimension: int,
    metric: str,
) -> PineconeDocumentStore:
    """Create the Pinecone-backed document store with sensible defaults."""
    if PineconeDocumentStore is None:  # pragma: no cover - configuration guard
        raise ImportError(
            "PineconeDocumentStore requested but haystack-integrations is not installed. "
            "Install via `pip install \"haystack-ai[pinecone]\"`."
        )
    return PineconeDocumentStore(
        index=index,
        namespace=namespace,
        dimension=dimension,
        metric=metric,
    )
