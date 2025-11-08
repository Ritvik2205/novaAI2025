from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sentence_transformers import CrossEncoder
from sqlmodel import Session, select

from app.config import get_settings
from app.db import Chunk, Document
from app.search.elasticsearch import ElasticHelper
from app.search.embeddings import EmbeddingProvider, get_embedding_provider


@dataclass
class Retrieved:
    chunk_id: int
    text: str
    meta: dict[str, Any]
    score: float


class HybridRetriever:
    def __init__(self, session: Session, embedding_provider: EmbeddingProvider | None = None) -> None:
        self.session = session
        self.elastic = ElasticHelper()
        self.elastic.ensure_index()
        self.embedder = embedding_provider or get_embedding_provider()
        self.settings = get_settings()
        self._cross_encoder: CrossEncoder | None = None

    def _dense_search(self, tenant_id: int, query: str, top_k: int) -> list[Retrieved]:
        statement = select(Chunk, Document).join(Document, Chunk.document_id == Document.id).where(
            Document.tenant_id == tenant_id
        ).limit(200)
        rows = self.session.exec(statement).all()
        if not rows:
            return []
        query_vec = self.embedder.embed([query])[0]
        chunk_texts = [chunk.text for chunk, _doc in rows]
        chunk_vectors = self.embedder.embed(chunk_texts)
        results: list[Retrieved] = []
        for (chunk, _doc), vec in zip(rows, chunk_vectors):
            score = self._cosine(query_vec, vec)
            results.append(Retrieved(chunk.id, chunk.text, chunk.meta_json, score))
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _bm25(self, tenant_id: int, query: str, top_k: int) -> list[Retrieved]:
        hits = self.elastic.search(tenant_id=tenant_id, query=query, top_k=top_k)
        return [Retrieved(hit["chunk_id"], hit.get("text", ""), hit, hit.get("score", 0.0)) for hit in hits]

    def _reciprocal_rank_fusion(self, lists: Iterable[list[Retrieved]]) -> list[Retrieved]:
        scores: dict[int, Retrieved] = {}
        for lst in lists:
            for rank, item in enumerate(lst, start=1):
                boost = 1 / (rank + 60)
                if item.chunk_id not in scores:
                    scores[item.chunk_id] = Retrieved(item.chunk_id, item.text, item.meta, item.score)
                scores[item.chunk_id].score += boost
        return sorted(scores.values(), key=lambda r: r.score, reverse=True)

    def _load_cross_encoder(self) -> CrossEncoder:
        if not self._cross_encoder:
            self._cross_encoder = CrossEncoder("sentence-transformers/ms-marco-MiniLM-L-6-v2")
        return self._cross_encoder

    def retrieve(self, tenant_id: int, query: str, top_k: int = 5, rerank: bool | None = None) -> list[Retrieved]:
        dense = self._dense_search(tenant_id, query, top_k * 2)
        sparse = self._bm25(tenant_id, query, top_k * 2)
        fused = self._reciprocal_rank_fusion([dense, sparse])
        fused = fused[: top_k * 2]
        rerank = self.settings.rerank_enabled if rerank is None else rerank
        if rerank and fused:
            model = self._load_cross_encoder()
            pairs = [[query, item.text] for item in fused]
            scores = model.predict(pairs)
            for item, score in zip(fused, scores):
                item.score = float(score)
            fused.sort(key=lambda r: r.score, reverse=True)
        return fused[:top_k]

    @staticmethod
    def _cosine(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
