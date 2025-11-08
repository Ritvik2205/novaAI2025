from __future__ import annotations

import logging
import csv
import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from haystack import Document
from haystack.components.builders import PromptBuilder
from haystack.components.embedders import OpenAITextEmbedder
from haystack.components.generators import OpenAIGenerator
from haystack.components.rankers import SentenceTransformersSimilarityRanker
from openai import OpenAI
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
import joblib

from app.core.config import get_settings
from app.core.document_store import get_document_store

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

MAX_ANCHOR_DOCS = 200
DENSE_PASS_THRESHOLD = 0.38
DENSE_REJECT_THRESHOLD = 0.25
HYBRID_PASS_THRESHOLD = 0.32
HYBRID_REJECT_THRESHOLD = 0.18
TRANSFORMER_ON_TOPIC_THRESHOLD = 0.55
TRANSFORMER_OFF_TOPIC_THRESHOLD = 0.25
LLM_DENSE_BAND = (0.28, 0.38)
LLM_TRANSFORMER_LOWER = 0.40
LLM_TRANSFORMER_UPPER = 0.60
CLASSIFIER_DATASET = Path("data/topic_gate_dataset.csv")


@dataclass
class NamespaceContext:
    anchor_vectors: List[np.ndarray]
    bm25: Optional[BM25Okapi]
    doc_count: int


_namespace_context_cache: Dict[str, NamespaceContext] = {}
_classifier_cache: Optional[Tuple[SentenceTransformer, StandardScaler, LogisticRegression]] = None
_openai_client: Optional[OpenAI] = None


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
    "shipping time",
    "delivery time",
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
    "data",
    "compliance",
    "cancellation",
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


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _normalize_vector(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def _load_documents_from_store(document_store, limit: int) -> List[Document]:
    try:
        docs = document_store.filter_documents(filters={}, limit=limit, return_embedding=True)
        if isinstance(docs, list) and docs:
            return docs
    except Exception:
        pass

    try:
        docs = document_store.filter_documents(filters={}, top_k=limit)
        if isinstance(docs, list) and docs:
            return docs
    except Exception:
        pass

    chroma_collection = getattr(document_store, "_collection", None)
    if chroma_collection is not None:
        try:
            raw = chroma_collection.get(
                limit=limit,
                include=["metadatas", "documents", "embeddings"],
            )
            docs: List[Document] = []
            for doc_id, text, meta, embedding in zip(
                raw.get("ids", []),
                raw.get("documents", []),
                raw.get("metadatas", []),
                raw.get("embeddings", []),
            ):
                docs.append(
                    Document(
                        id=doc_id,
                        content=text,
                        meta=meta or {},
                        embedding=embedding,
                    )
                )
            if docs:
                return docs
        except Exception:
            pass

    return []


def _get_namespace_context(document_store, embedder: OpenAITextEmbedder, namespace: Optional[str]) -> NamespaceContext:
    cache_key = namespace or "__default__"
    try:
        current_count = document_store.count_documents()
    except Exception:  # pragma: no cover - backend differences
        current_count = -1
    cached = _namespace_context_cache.get(cache_key)
    if cached and cached.doc_count == current_count and cached.anchor_vectors:
        return cached

    docs = _load_documents_from_store(document_store, MAX_ANCHOR_DOCS)

    anchors: List[np.ndarray] = []
    corpus_tokens: List[List[str]] = []
    collected = 0
    for doc in docs:
        if collected >= MAX_ANCHOR_DOCS:
            break
        text = (doc.content or "").strip()
        if not text:
            continue
        tokens = _tokenize(text)
        if not tokens:
            continue
        corpus_tokens.append(tokens)
        if doc.embedding:
            vec = np.asarray(doc.embedding, dtype=np.float32)
        else:
            # Fallback: embed lightweight summary
            snippet = " ".join(tokens[:128])
            vec = np.asarray(embedder.run(text=snippet)["embedding"], dtype=np.float32)
        anchors.append(_normalize_vector(vec))
        collected += 1

    bm25 = BM25Okapi(corpus_tokens) if corpus_tokens else None
    context = NamespaceContext(anchor_vectors=anchors, bm25=bm25, doc_count=current_count)
    _namespace_context_cache[cache_key] = context
    return context


def _compute_anchor_scores(query_vec: np.ndarray, context: NamespaceContext, question: str) -> Tuple[float, float, float]:
    max_dense = 0.0
    if context.anchor_vectors:
        normalized_query = _normalize_vector(query_vec)
        sims = [float(np.dot(normalized_query, anchor)) for anchor in context.anchor_vectors]
        if sims:
            max_dense = max(sims)

    bm25_norm = 0.0
    if context.bm25:
        tokens = _tokenize(question)
        if tokens:
            scores = context.bm25.get_scores(tokens)
            if scores.size > 0:
                bm25_raw = float(np.max(scores))
                bm25_norm = math.tanh(bm25_raw / 5.0)

    hybrid = 0.6 * max_dense + 0.4 * bm25_norm
    return max_dense, bm25_norm, hybrid


def _get_classifier() -> Tuple[SentenceTransformer, StandardScaler, LogisticRegression]:
    global _classifier_cache
    if _classifier_cache is not None:
        return _classifier_cache

    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    if (Path(__file__).resolve().parent / "topic_classifier.joblib").exists():
        data = joblib.load(Path(__file__).resolve().parent / "topic_classifier.joblib")
        scaler = data["scaler"]
        classifier = data["classifier"]
    else:
        scaler = StandardScaler()
        classifier = LogisticRegression(max_iter=500)
        if CLASSIFIER_DATASET.exists():
            texts: List[str] = []
            labels: List[int] = []
            with CLASSIFIER_DATASET.open() as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    text = (row.get("query") or "").strip()
                    label = (row.get("label") or "").strip().lower()
                    if not text or label not in {"on_topic", "off_topic"}:
                        continue
                    texts.append(text)
                    labels.append(1 if label == "on_topic" else 0)
            if texts and len(set(labels)) > 1:
                embeddings = model.encode(texts, batch_size=64, convert_to_numpy=True)
                scaler.fit(embeddings)
                emb_scaled = scaler.transform(embeddings)
                classifier.fit(emb_scaled, labels)
        joblib.dump({"scaler": scaler, "classifier": classifier}, Path(__file__).resolve().parent / "topic_classifier.joblib")

    _classifier_cache = (model, scaler, classifier)
    return _classifier_cache


def _transformer_confidence(question: str) -> float:
    model, scaler, classifier = _get_classifier()
    embedding = model.encode(question, convert_to_numpy=True)
    emb_scaled = scaler.transform([embedding])
    prob = classifier.predict_proba(emb_scaled)[0][1]
    return float(prob)


def _get_openai_client(settings) -> Optional[OpenAI]:
    global _openai_client
    if not settings.openai_api_key.get_secret_value():
        return None
    if _openai_client is None:
        _openai_client = OpenAI(api_key=settings.openai_api_key.get_secret_value())
    return _openai_client


def _llm_on_topic(question: str, settings) -> Optional[bool]:
    client = _get_openai_client(settings)
    if client is None:
        return None

    schema = {
        "name": "on_topic_classification",
        "schema": {
            "type": "object",
            "properties": {
                "on_topic": {"type": "boolean"},
                "reason": {"type": "string"},
            },
            "required": ["on_topic"],
            "additionalProperties": False,
        },
    }

    try:
        response = client.responses.create(
            model=settings.openai_guard_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You classify if a question is about the company's products, services, or policies. "
                        "Respond strictly with JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {question}\nRespond with JSON only.",
                },
            ],
            response_format={"type": "json_schema", "json_schema": schema},
        )
        raw = response.output[0].content[0].text  # type: ignore[index]
        data = json.loads(raw)
        return bool(data.get("on_topic"))
    except Exception as exc:  # pragma: no cover - network issues
        logger.warning("LLM guardrail failed: %s", exc)
        return None


def _coverage_sufficient(documents: List[Document]) -> bool:
    if not documents:
        return False
    top_score = getattr(documents[0], "score", 0.0)
    if top_score >= 0.4:
        return True
    high_docs = [doc for doc in documents if getattr(doc, "score", 0.0) >= 0.33]
    weighted = sum(getattr(doc, "score", 0.0) for doc in high_docs)
    return len(high_docs) >= 2 or weighted >= 0.65


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

    if _looks_off_topic(question):
        return {"answer": GUARDRAIL_MESSAGE, "documents": []}

    document_store = get_document_store(namespace=namespace)

    embedder = _get_text_embedder(settings.openai_embedding_model)
    embedding_result = embedder.run(text=question)
    query_embedding = embedding_result["embedding"]
    query_vec = np.asarray(query_embedding, dtype=np.float32)

    context = _get_namespace_context(document_store, embedder, namespace)
    max_dense_sim, bm25_norm, hybrid_score = _compute_anchor_scores(query_vec, context, question)

    def _maybe_llm(prob: float) -> bool:
        if not (LLM_DENSE_BAND[0] <= max_dense_sim <= LLM_DENSE_BAND[1]):
            return True
        if not (LLM_TRANSFORMER_LOWER <= prob <= LLM_TRANSFORMER_UPPER):
            return True
        llm_result = _llm_on_topic(question, settings)
        return llm_result not in (False, None)

    if max_dense_sim < DENSE_REJECT_THRESHOLD and hybrid_score < HYBRID_REJECT_THRESHOLD:
        transformer_prob = _transformer_confidence(question)
        if transformer_prob <= TRANSFORMER_OFF_TOPIC_THRESHOLD:
            return {"answer": GUARDRAIL_MESSAGE, "documents": []}
        if transformer_prob < TRANSFORMER_ON_TOPIC_THRESHOLD and not _maybe_llm(transformer_prob):
            return {"answer": GUARDRAIL_MESSAGE, "documents": []}
    elif max_dense_sim < DENSE_PASS_THRESHOLD or hybrid_score < HYBRID_PASS_THRESHOLD:
        transformer_prob = _transformer_confidence(question)
        if transformer_prob <= TRANSFORMER_OFF_TOPIC_THRESHOLD:
            return {"answer": GUARDRAIL_MESSAGE, "documents": []}
        if transformer_prob < TRANSFORMER_ON_TOPIC_THRESHOLD and not _maybe_llm(transformer_prob):
            return {"answer": GUARDRAIL_MESSAGE, "documents": []}

    retrieved = document_store.search_embeddings(
        query_embeddings=[query_embedding],
        top_k=settings.max_retriever_results,
    )
    documents = retrieved[0] if retrieved else []

    if not documents:
        return {"answer": GUARDRAIL_MESSAGE, "documents": []}

    top_score = getattr(documents[0], "score", None)
    if top_score is not None and top_score < 0.3:
        return {"answer": GUARDRAIL_MESSAGE, "documents": []}

    ranker = _get_ranker(settings.reranker_model, settings.max_reranked_results)
    rank_result = ranker.run(query=question, documents=documents)
    ranked_documents: List[Document] = rank_result["documents"]
    ranked_documents = ranked_documents[: settings.max_reranked_results]

    if not _coverage_sufficient(ranked_documents):
        return {"answer": GUARDRAIL_MESSAGE, "documents": []}

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
