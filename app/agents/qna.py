from __future__ import annotations

from typing import Any

from app.agents.llm import get_llm_provider
from app.schemas import Citation, QueryResponse, RetrievedChunk
from app.search.retrieval import HybridRetriever


class QnAAgent:
    def __init__(self, retriever: HybridRetriever) -> None:
        self.retriever = retriever
        self.llm = get_llm_provider()

    async def answer(self, tenant_id: int, query: str, top_k: int, rerank: bool | None) -> QueryResponse:
        chunks = self.retriever.retrieve(tenant_id, query, top_k=top_k, rerank=rerank)
        if not chunks:
            followup = "Could you share more specifics so I can search the docs?"
            return QueryResponse(answer=followup, citations=[], retrieved=[])
        context_lines = []
        citations: list[Citation] = []
        retrieved: list[RetrievedChunk] = []
        for idx, chunk in enumerate(chunks, start=1):
            citation = Citation(url=chunk.meta.get("url"), section=chunk.meta.get("section"), score=chunk.score)
            citations.append(citation)
            retrieved.append(RetrievedChunk(chunk_id=chunk.chunk_id, text=chunk.text, meta=chunk.meta, score=chunk.score))
            context_lines.append(f"[{idx}] {chunk.text}\nSOURCE: {citation.url or 'N/A'} {citation.section or ''}")
        context = "\n\n".join(context_lines)
        prompt = (
            "You are a construction support assistant."
            "Use only the provided context to answer."
            "Always cite using [n] that matches the chunk order."
            f"\nQuestion: {query}\nContext:\n{context}"
        )
        answer = await self.llm.chat(prompt)
        if "[" not in answer:
            answer = f"{answer}\n\nSources: " + ", ".join(f"[{i}]" for i in range(1, len(chunks) + 1))
        return QueryResponse(answer=answer, citations=citations, retrieved=retrieved)
