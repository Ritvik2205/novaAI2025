from sqlmodel import Session, SQLModel, create_engine

from app.db import Chunk, Document
from app.search.retrieval import HybridRetriever


def test_hybrid_retrieval_returns_chunk(monkeypatch):
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine, tables=[Document.__table__, Chunk.__table__])
    with Session(engine) as session:
        doc = Document(tenant_id=1, source_type="web", url_or_name="https://demo", mime="text/html", sha256="abc")
        session.add(doc)
        session.commit()
        session.refresh(doc)
        chunk = Chunk(document_id=doc.id, text="Our deck pricing starts at 100", meta_json={"url": "https://demo"})
        session.add(chunk)
        session.commit()
        session.refresh(chunk)
        retriever = HybridRetriever(session)
        retriever.elastic.client = None
        retriever.elastic._local_store[chunk.id] = {"tenant_id": 1, "text": chunk.text}
        results = retriever.retrieve(tenant_id=1, query="pricing", top_k=1, rerank=False)
        assert results, "retriever should return chunks"
        assert results[0].chunk_id == chunk.id
