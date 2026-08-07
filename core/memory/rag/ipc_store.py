"""VectorStore reads over root IPC, with writes left on the HTTP worker."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from core.memory.rag.http_store import HttpVectorStore, _parse_documents, _parse_search_results

logger = logging.getLogger(__name__)

MemoryRequester = Callable[[str, dict[str, Any]], dict[str, Any]]


class IpcVectorStore(HttpVectorStore):
    """Split backend: root IPC for reads, existing server proxy for writes."""

    def __init__(self, base_url: str, anima_name: str | None, requester: MemoryRequester) -> None:
        super().__init__(base_url, anima_name)
        self._requester = requester

    def _read(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return self._requester(method, params)
        except Exception as exc:
            logger.warning("IPC vector read failed: method=%s anima=%s error=%s", method, self._anima_name, exc)
            return None

    def list_collections(self) -> list[str]:
        data = self._read("memory.list_collections_checked", {})
        collections = data.get("collections") if data else None
        return (
            list(collections)
            if isinstance(collections, list) and all(isinstance(name, str) for name in collections)
            else []
        )

    def list_collections_checked(self) -> list[str] | None:
        data = self._read("memory.list_collections_checked", {})
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
        data = self._read("memory.query", params)
        return _parse_search_results(data["results"]) if data and isinstance(data.get("results"), list) else []

    def get_by_metadata(
        self,
        collection: str,
        where: dict[str, str | int | float],
        limit: int = 20,
    ):
        data = self._read(
            "memory.get_by_metadata",
            {"collection": collection, "where": where, "limit": limit},
        )
        return _parse_search_results(data["results"]) if data and isinstance(data.get("results"), list) else []

    def get_by_ids(self, collection: str, ids: list[str]):
        if not ids:
            return []
        data = self._read("memory.get_by_ids", {"collection": collection, "ids": ids})
        return _parse_documents(data["documents"]) if data and isinstance(data.get("documents"), list) else []
