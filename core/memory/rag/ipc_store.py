"""VectorStore operations over root IPC."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from core.memory.rag.http_store import (
    _UPSERT_BATCH_LIMIT,
    HttpVectorStore,
    _parse_documents,
    _parse_search_results,
)
from core.memory.rag.store import Document

logger = logging.getLogger(__name__)

MemoryRequester = Callable[[str, dict[str, Any]], dict[str, Any]]


class IpcVectorStore(HttpVectorStore):
    """Root IPC backend for one phase3 anima's vector database."""

    def __init__(self, base_url: str, anima_name: str | None, requester: MemoryRequester) -> None:
        super().__init__(base_url, anima_name)
        self._requester = requester
        self._ipc_unavailable_writes: set[str] = set()

    def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return self._requester(method, params)
        except Exception as exc:
            logger.warning("IPC vector request failed: method=%s anima=%s error=%s", method, self._anima_name, exc)
            return None

    def _write(self, method: str, params: dict[str, Any]) -> bool:
        data = self._call(method, params)
        collection = params.get("collection")
        if isinstance(collection, str):
            if data is None:
                self._ipc_unavailable_writes.add(collection)
            elif data.get("ok") is True:
                self._ipc_unavailable_writes.discard(collection)
        return data is not None and data.get("ok") is True

    def is_transient_write_failure(self, collection: str) -> bool:
        return collection in self._ipc_unavailable_writes

    def create_collection(self, name: str) -> bool:
        return self._write("memory.create_collection", {"collection": name})

    def delete_collection(self, name: str) -> bool:
        return self._write("memory.delete_collection", {"collection": name})

    def upsert(self, collection: str, documents: list[Document]) -> bool:
        if not documents:
            return True
        for start in range(0, len(documents), _UPSERT_BATCH_LIMIT):
            batch = documents[start : start + _UPSERT_BATCH_LIMIT]
            if not self._write(
                "memory.upsert",
                {
                    "collection": collection,
                    "documents": [
                        {
                            "id": document.id,
                            "content": document.content,
                            "embedding": document.embedding,
                            "metadata": document.metadata,
                        }
                        for document in batch
                    ],
                },
            ):
                return False
        return True

    def delete_documents(self, collection: str, ids: list[str]) -> bool:
        return not ids or self._write("memory.delete_documents", {"collection": collection, "ids": ids})

    def update_metadata(
        self,
        collection: str,
        ids: list[str],
        metadatas: list[dict[str, str | int | float]],
    ) -> bool:
        return not ids or self._write(
            "memory.update_metadata",
            {"collection": collection, "ids": ids, "metadatas": metadatas},
        )

    def list_collections(self) -> list[str]:
        data = self._call("memory.list_collections_checked", {})
        collections = data.get("collections") if data else None
        return (
            list(collections)
            if isinstance(collections, list) and all(isinstance(name, str) for name in collections)
            else []
        )

    def list_collections_checked(self) -> list[str] | None:
        data = self._call("memory.list_collections_checked", {})
        collections = data.get("collections") if data else None
        if not isinstance(collections, list) or not all(isinstance(name, str) for name in collections):
            return None
        return list(collections)

    def query(
        self,
        collection: str,
        embedding: list[float],
        top_k: int = 10,
        filter_metadata: dict[str, str | int | float] | None = None,
    ):
        params: dict[str, Any] = {"collection": collection, "embedding": embedding, "top_k": top_k}
        if filter_metadata:
            params["filter_metadata"] = filter_metadata
        data = self._call("memory.query", params)
        return _parse_search_results(data["results"]) if data and isinstance(data.get("results"), list) else []

    def get_by_metadata(
        self,
        collection: str,
        where: dict[str, str | int | float],
        limit: int = 20,
    ):
        data = self._call(
            "memory.get_by_metadata",
            {"collection": collection, "where": where, "limit": limit},
        )
        return _parse_search_results(data["results"]) if data and isinstance(data.get("results"), list) else []

    def get_by_ids(self, collection: str, ids: list[str]):
        if not ids:
            return []
        data = self._call("memory.get_by_ids", {"collection": collection, "ids": ids})
        return _parse_documents(data["documents"]) if data and isinstance(data.get("documents"), list) else []
