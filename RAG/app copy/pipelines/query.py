from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List, Optional

import numpy as np
from haystack import Document
from haystack.components.builders import PromptBuilder
from haystack.components.embedders import OpenAITextEmbedder
from haystack.components.generators import OpenAIGenerator
from haystack.components.rankers import SentenceTransformersSimilarityRanker

from app.core.config import get_settings
from app.core.document_store import get_document_store
from app.guardrails import get_topic_gate

logger = logging.getLogger(__name__)

PROMPT_TEMPLATE = """
You are a customer-support teammate speaking on behalf of the company. Answer using the context passages only.
If the context does not contain the answer, reply with "I don't have that information yet."

Context:
{% for doc in documents %}
[{{ doc.index }}] Title: {{ doc.title }}
URL: {{ doc.url or "N/A" }}
Passage: {{ doc.content }}

{% endfor %}
Question: {{query}}

Instructions:
- Speak in first person plural (we/our) and keep the answer to a few short sentences.
- Only use bullet lists when enumerating items or steps; otherwise respond in prose.
- Stay factual and avoid speculation.
{% if include_references %}
- End the answer with "References:" followed by Markdown links [n](URL) that match the numbered context entries you relied on.
{% else %}
- Do not include any reference list.
{% endif %}
"""

_PROMPT_BUILDER = PromptBuilder(
    template=PROMPT_TEMPLATE,
    required_variables={"query", "documents", "include_references"},
)

SIMPLE_KEYWORDS = {
    "price",
    "cost",
    "recommend",
    "suggest",
    "popular",
    "best",
    "favorite",
    "top",
    "buy",
    "purchase",
    "order",
}

COMPLEX_KEYWORDS = {
    "refund",
    "return",
    "policy",
    "guarantee",
    "warranty",
    "material",
    "ingredient",
    "composition",
    "privacy",
    "security",
    "store data",
    "personal information",
    "shipping",
    "support",
    "contact",
    "terms",
}

OFF_TOPIC_KEYWORDS = {
    "weather",
    "stock",
    "finance",
    "politics",
    "recipe",
    "movie",
    "sports",
    "news",
    "science",
    "technology",
    "music",
    "song",
    "currency",
    "bitcoin",
    "crypto",
}

GUARDRAIL_MESSAGE = (
    "I'm here to help with questions about our products and services. "
    "Please ask something related to the business."
)

NO_CONTEXT_MESSAGE = (
    "I couldn't find any information on that in our knowledge base yet. "
    "Try rephrasing or ingest the relevant content."
)


def _is_complex_question(question: str) -> bool:
    normalized = question.lower()
    if any(keyword in normalized for keyword in COMPLEX_KEYWORDS):
        return True
    if any(keyword in normalized for keyword in SIMPLE_KEYWORDS):
        return False
    return True


def _looks_off_topic(question: str) -> bool:
    normalized = question.lower()
    return any(keyword in normalized for keyword in OFF_TOPIC_KEYWORDS)


def run_query(
    question: str,
    namespace: Optional[str] = None,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute retrieval-augmented generation for the supplied question."""
    settings = get_settings()
    if not settings.openai_api_key.get_secret_value():
        raise RuntimeError("OPENAI_API_KEY must be set to run the query pipeline.")

    if filters:
        logger.warning("Metadata filters are not yet implemented in the Haystack 2 pipeline. Ignoring filters: %s", filters)

    topic_gate = get_topic_gate()
    if topic_gate:
        verdict = topic_gate.evaluate(question)
        if not verdict.allow:
            logger.info(
                "Guardrails blocked question '%s' (detail=%s)",
                question,
                verdict.detail,
            )
            return {"answer": GUARDRAIL_MESSAGE, "documents": []}
    elif _looks_off_topic(question):
        return {"answer": GUARDRAIL_MESSAGE, "documents": []}

    document_store = get_document_store(namespace=namespace)

    embedder = _get_text_embedder(settings.openai_embedding_model)
    embedding_result = embedder.run(text=question)
    query_embedding = embedding_result["embedding"]

    if hasattr(document_store, "search_embeddings"):
        retrieved = document_store.search_embeddings(
            query_embeddings=[query_embedding],
            top_k=settings.max_retriever_results,
        )
        documents = retrieved[0] if retrieved else []
    else:
        # Fallback for document stores without specialized search API (e.g. InMemory).
        all_docs = document_store.filter_documents(filters=None)  # type: ignore[attr-defined]
        if not all_docs:
            return {"answer": NO_CONTEXT_MESSAGE, "documents": []}
        query_vec = np.array(query_embedding)
        scored: List[Document] = []
        for doc in all_docs:
            if doc.embedding is None:
                continue
            doc_vec = np.array(doc.embedding)
            if doc_vec.shape != query_vec.shape:
                continue
            score = float(np.dot(doc_vec, query_vec) / (np.linalg.norm(doc_vec) * np.linalg.norm(query_vec)))
            doc.score = score
            scored.append(doc)
        scored.sort(key=lambda d: getattr(d, "score", 0.0), reverse=True)
        documents = scored[: settings.max_retriever_results]

    if not documents:
        return {"answer": NO_CONTEXT_MESSAGE, "documents": []}

    top_score = getattr(documents[0], "score", None)
    if top_score is not None and top_score < 0.25:
        return {"answer": NO_CONTEXT_MESSAGE, "documents": []}

    ranker = _get_ranker(settings.reranker_model, settings.max_reranked_results)
    rank_result = ranker.run(query=question, documents=documents)
    ranked_documents: List[Document] = rank_result["documents"]
    ranked_documents = ranked_documents[: settings.max_reranked_results]

    should_include_references = _is_complex_question(question)

    formatted_docs = [
        {
            "index": idx,
            "title": doc.meta.get("title") if doc.meta else None,
            "url": doc.meta.get("url") if doc.meta else None,
            "content": doc.content,
        }
        for idx, doc in enumerate(ranked_documents, start=1)
    ]

    prompt = _PROMPT_BUILDER.run(
        query=question,
        documents=formatted_docs,
        include_references=should_include_references,
    )["prompt"]
    generator = _get_generator(settings.openai_model, settings.max_generation_tokens)
    completion = generator.run(prompt=prompt)["replies"][0]

    if should_include_references:
        documents_for_citations = ranked_documents[:1]
    else:
        documents_for_citations = []

    return {"answer": completion, "documents": documents_for_citations}


def list_namespaces() -> List[Dict[str, object]]:
    """Return available namespaces (collections) in the document store."""
    settings = get_settings()
    backend = settings.vector_store.lower()

    if backend == "chroma":
        try:
            import chromadb  # type: ignore
        except ImportError:  # pragma: no cover - defensive
            logger.warning("chromadb not available; returning default namespace only")
            return [
                {
                    "namespace": settings.default_namespace,
                    "pages_indexed": None,
                    "chunks_indexed": None,
                }
            ]

        client = chromadb.PersistentClient(path=settings.chroma_persist_path)
        summaries: List[Dict[str, object]] = []
        for collection in client.list_collections():
            coll = client.get_collection(name=collection.name)
            try:
                chunk_count = coll.count()
            except Exception:  # pragma: no cover - chroma edge cases
                chunk_count = None
            summaries.append(
                {
                    "namespace": collection.name,
                    "chunks_indexed": chunk_count,
                    "pages_indexed": None,
                }
            )
        return summaries

    return [{"namespace": settings.default_namespace, "pages_indexed": None, "chunks_indexed": None}]


@lru_cache(maxsize=1)
def _get_text_embedder(model_name: str) -> OpenAITextEmbedder:
    return OpenAITextEmbedder(model=model_name)


@lru_cache(maxsize=1)
def _get_ranker(model_name: str, top_k: int) -> SentenceTransformersSimilarityRanker:
    ranker = SentenceTransformersSimilarityRanker(model=model_name, top_k=top_k)
    ranker.warm_up()
    return ranker


@lru_cache(maxsize=1)
def _get_generator(model_name: str, max_output_tokens: int) -> OpenAIGenerator:
    generation_kwargs = {"max_tokens": max_output_tokens} if max_output_tokens else None
    return OpenAIGenerator(model=model_name, generation_kwargs=generation_kwargs)
