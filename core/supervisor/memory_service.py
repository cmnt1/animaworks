"""Root-owned vector memory service."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from core.memory.rag.store import Document, SearchResult, VectorStore

logger = logging.getLogger(__name__)


class MemoryServiceUnavailable(RuntimeError):
    """The root memory service cannot safely answer a request."""


class MemoryService:
    """Serialize one anima's native vector operations on one bounded worker."""

    def __init__(
        self,
        anima_name: str,
        anima_dir: Path,
        *,
        queue_limit: int = 64,
        opener: Callable[[], VectorStore] | None = None,
        repair_fenced: Callable[[], bool] | None = None,
    ) -> None:
        if queue_limit < 1:
            raise ValueError("queue_limit must be >= 1")
        self.anima_name = anima_name
        self.anima_dir = anima_dir
        self.queue_limit = queue_limit
        self._opener = opener or self._open_native_store
        self._repair_fenced = repair_fenced or self._has_active_repair_fence
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"memory-{anima_name}")
        self._store: VectorStore | None = None
        self._open_error: Exception | None = None
        self._pending = 0
        self._started = False

    async def start(self) -> None:
        """Open Chroma off the root event loop; failure leaves root available."""
        if self._started:
            return
        self._started = True
        try:
            self._store = await asyncio.get_running_loop().run_in_executor(self._executor, self._opener)
        except Exception as exc:
            self._open_error = exc
            logger.warning("Root memory store open failed for %s: %s", self.anima_name, exc)

    async def handle(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Run one checked operation or raise an explicit unavailable error."""
        if not self._started:
            await self.start()
        if self._store is None:
            raise MemoryServiceUnavailable(f"memory store unavailable: {self._open_error or 'not open'}")
        try:
            fenced = self._repair_fenced()
        except Exception as exc:
            raise MemoryServiceUnavailable(f"repair fence state unavailable: {exc}") from exc
        if fenced:
            raise MemoryServiceUnavailable("RAG repair in progress")
        if self._pending >= self.queue_limit:
            raise MemoryServiceUnavailable("memory queue is full")

        self._pending += 1
        try:
            return await asyncio.get_running_loop().run_in_executor(
                self._executor,
                self._dispatch,
                method,
                params,
            )
        except MemoryServiceUnavailable:
            raise
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("Root memory operation failed for %s: %s", self.anima_name, exc)
            raise MemoryServiceUnavailable(f"memory operation failed: {exc}") from exc
        finally:
            self._pending -= 1

    def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        store = self._store
        if store is None:
            raise MemoryServiceUnavailable("memory store unavailable")
        if method == "memory.query":
            collection = self._string(params, "collection")
            embedding = params.get("embedding")
            top_k = params.get("top_k", 10)
            filter_metadata = params.get("filter_metadata")
            if not isinstance(embedding, list) or not all(isinstance(value, (int, float)) for value in embedding):
                raise ValueError("embedding must be a list of numbers")
            if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
                raise ValueError("top_k must be an integer >= 1")
            if filter_metadata is not None and not isinstance(filter_metadata, dict):
                raise ValueError("filter_metadata must be an object or null")
            query = getattr(store, "_query_once", store.query)
            return {"results": self._search_results(query(collection, embedding, top_k, filter_metadata))}
        if method == "memory.list_collections_checked":
            listing = getattr(store, "_list_collections_once", store.list_collections)
            return {"collections": list(listing())}
        if method == "memory.get_by_metadata":
            collection = self._string(params, "collection")
            where = params.get("where")
            limit = params.get("limit", 20)
            if not isinstance(where, dict):
                raise ValueError("where must be an object")
            if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
                raise ValueError("limit must be an integer >= 1")
            get = getattr(store, "_get_by_metadata_once", store.get_by_metadata)
            return {"results": self._search_results(get(collection, where, limit))}
        if method == "memory.get_by_ids":
            collection = self._string(params, "collection")
            ids = params.get("ids")
            if not isinstance(ids, list) or not all(isinstance(value, str) for value in ids):
                raise ValueError("ids must be a list of strings")
            get = getattr(store, "_get_by_ids_once", store.get_by_ids)
            return {"documents": self._documents(get(collection, ids))}
        if method == "memory.create_collection":
            collection = self._string(params, "collection")
            create = getattr(store, "_create_collection_once", store.create_collection)
            return {"ok": bool(create(collection))}
        if method == "memory.delete_collection":
            collection = self._string(params, "collection")
            delete = getattr(store, "_delete_collection_once", store.delete_collection)
            return {"ok": bool(delete(collection))}
        if method == "memory.upsert":
            collection = self._string(params, "collection")
            documents = self._document_params(params.get("documents"))
            upsert = getattr(store, "_upsert_once", store.upsert)
            return {"ok": bool(upsert(collection, documents))}
        if method == "memory.delete_documents":
            collection = self._string(params, "collection")
            ids = self._strings(params.get("ids"), "ids")
            delete = getattr(store, "_delete_documents_once", store.delete_documents)
            return {"ok": bool(delete(collection, ids))}
        if method == "memory.update_metadata":
            collection = self._string(params, "collection")
            ids = self._strings(params.get("ids"), "ids")
            metadatas = params.get("metadatas")
            if not isinstance(metadatas, list) or not all(isinstance(item, dict) for item in metadatas):
                raise ValueError("metadatas must be a list of objects")
            if len(ids) != len(metadatas):
                raise ValueError("ids and metadatas must have the same length")
            update = getattr(store, "_update_metadata_once", store.update_metadata)
            return {"ok": bool(update(collection, ids, metadatas))}
        raise ValueError(f"unsupported memory method: {method}")

    @staticmethod
    def _string(params: dict[str, Any], key: str) -> str:
        value = params.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{key} must be a non-empty string")
        return value

    @staticmethod
    def _strings(value: Any, key: str) -> list[str]:
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{key} must be a list of strings")
        return value

    @staticmethod
    def _document_params(value: Any) -> list[Document]:
        if not isinstance(value, list):
            raise ValueError("documents must be a list")
        documents: list[Document] = []
        for item in value:
            if not isinstance(item, dict):
                raise ValueError("documents must contain objects")
            doc_id = item.get("id")
            content = item.get("content", "")
            embedding = item.get("embedding")
            metadata = item.get("metadata", {})
            if not isinstance(doc_id, str) or not doc_id:
                raise ValueError("document id must be a non-empty string")
            if not isinstance(content, str):
                raise ValueError("document content must be a string")
            if embedding is not None and (
                not isinstance(embedding, list)
                or not all(isinstance(number, (int, float)) and not isinstance(number, bool) for number in embedding)
            ):
                raise ValueError("document embedding must be a list of numbers or null")
            if not isinstance(metadata, dict):
                raise ValueError("document metadata must be an object")
            documents.append(Document(id=doc_id, content=content, embedding=embedding, metadata=metadata))
        return documents

    @staticmethod
    def _documents(documents: list[Document]) -> list[dict[str, Any]]:
        return [{"id": doc.id, "content": doc.content, "metadata": doc.metadata} for doc in documents]

    @classmethod
    def _search_results(cls, results: list[SearchResult]) -> list[dict[str, Any]]:
        return [{"document": cls._documents([result.document])[0], "score": result.score} for result in results]

    def _open_native_store(self) -> VectorStore:
        from core.memory.rag.direct_access import enable_direct_chroma_for_process
        from core.memory.rag.store import create_chroma_vector_store
        from core.paths import get_anima_vectordb_dir

        enable_direct_chroma_for_process()
        return create_chroma_vector_store(
            persist_dir=get_anima_vectordb_dir(self.anima_name),
            anima_name=self.anima_name,
        )

    def _has_active_repair_fence(self) -> bool:
        from core.memory.rag import repair_state

        state = repair_state.read_state(self.anima_name, animas_dir=self.anima_dir.parent)
        return state.get("status") in repair_state.ACTIVE_REPAIR_STATUSES

    async def close(self) -> None:
        """Close the sole native handle after queued operations drain."""
        store, self._store = self._store, None
        if store is not None:
            try:
                await asyncio.get_running_loop().run_in_executor(self._executor, store.close)
            except Exception:
                logger.warning("Failed to close root memory store for %s", self.anima_name, exc_info=True)
        self._executor.shutdown(wait=False)
