from __future__ import annotations

from typing import Any, Iterable

from elasticsearch import Elasticsearch

from app.config import get_settings


class ElasticHelper:
    def __init__(self, index: str = "nova-chunks"):
        self.index = index
        try:
            self.client = Elasticsearch(get_settings().elastic_url)
        except Exception:
            self.client = None
        self._local_store: dict[int, dict[str, Any]] = {}

    def ensure_index(self) -> None:
        if self.client is None:
            return
        try:
            if self.client.indices.exists(index=self.index):
                return
            body = {
                "settings": {
                    "analysis": {
                        "analyzer": {
                            "default": {
                                "tokenizer": "standard",
                                "filter": ["lowercase", "asciifolding"]
                            }
                        }
                    }
                },
                "mappings": {
                    "properties": {
                        "tenant_id": {"type": "keyword"},
                        "text": {"type": "text"},
                        "doc_type": {"type": "keyword"},
                        "url": {"type": "keyword"},
                        "section": {"type": "keyword"}
                    }
                }
            }
            self.client.indices.create(index=self.index, body=body)
        except Exception:
            self.client = None

    def index_chunk(self, chunk_id: int, tenant_id: int, body: dict[str, Any]) -> None:
        doc = {"tenant_id": tenant_id, **body}
        if self.client is None:
            self._local_store[chunk_id] = doc
            return
        self.client.index(index=self.index, id=str(chunk_id), document=doc)

    def bulk_index(self, items: Iterable[dict[str, Any]]) -> None:
        actions = []
        for item in items:
            chunk_id = item.pop("chunk_id")
            actions.append({"index": {"_index": self.index, "_id": chunk_id}})
            actions.append(item)
        if self.client and actions:
            self.client.bulk(actions=actions)
        elif not self.client:
            for action, doc in zip(actions[::2], actions[1::2]):
                chunk_id = int(action["index"]["_id"])
                self._local_store[chunk_id] = doc

    def search(self, tenant_id: int, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        body = {
            "query": {
                "bool": {
                    "must": {"match": {"text": query}},
                    "filter": [{"term": {"tenant_id": tenant_id}}]
                }
            },
            "size": top_k
        }
        if self.client is None:
            return [
                {"chunk_id": chunk_id, **doc, "score": 1.0}
                for chunk_id, doc in list(self._local_store.items())[:top_k]
                if doc.get("tenant_id") == tenant_id
            ]
        resp = self.client.search(index=self.index, body=body)
        results = []
        for hit in resp["hits"]["hits"]:
            source = hit["_source"]
            source["score"] = hit["_score"] or 0.0
            source["chunk_id"] = int(hit["_id"])
            results.append(source)
        return results
