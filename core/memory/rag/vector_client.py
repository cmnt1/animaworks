from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unified synchronous client for HTTP and in-process vector transports."""

import logging
import time
from collections.abc import Callable
from typing import Any

from core.memory.rag.store import Document, SearchResult, VectorStore

logger = logging.getLogger(__name__)

_UPSERT_BATCH_LIMIT = 500
_FAILURE_LOG_INTERVAL_SECONDS = 60.0

# A VectorTransport receives an endpoint path and JSON payload and returns a
# JSON response (or None on unrecoverable failure). HTTP and in-process
# bridges share the same client-side retry and circuit logic.
VectorTransport = Callable[[str, dict[str, Any]], dict[str, Any] | None]

# Cap matches the old root-IPC path: never sleep longer than 500ms on a retry.
_MAX_RETRY_AFTER_MS = 500
_DEFAULT_RETRY_AFTER_MS = 250


class VectorStoreRetryableError(Exception):
    """Raised by a transport when a temporary service failure may recover."""

    def __init__(self, message: str = "", *, retry_after_ms: int = _DEFAULT_RETRY_AFTER_MS) -> None:
        super().__init__(message)
        self.retryable = True
        self.retry_after_ms = retry_after_ms


def _retry_after_ms(exc: BaseException) -> int | None:
    """Return the sleep ms for an explicit retryable failure, else None."""
    if getattr(exc, "retryable", None) is True:
        raw = getattr(exc, "retry_after_ms", _DEFAULT_RETRY_AFTER_MS)
        try:
            ms = int(raw)
        except (TypeError, ValueError):
            ms = _DEFAULT_RETRY_AFTER_MS
        return max(0, min(ms, _MAX_RETRY_AFTER_MS))

    message = str(exc)
    if message.startswith("UNAVAILABLE:") or message.startswith("UNAVAILABLE "):
        # Deterministic failures never heal within one retry window — waiting
        # 250ms per query for a permanently missing collection just burns the
        # priming budget.
        if "does not exist" in message or "already exists" in message:
            return None
        return _DEFAULT_RETRY_AFTER_MS
    return None


def _response_retry_after_ms(resp: Any, retry_after_header: str) -> int:
    """Read ``retry_after_ms`` from the response body or Retry-After header."""
    try:
        body = resp.json()
        if isinstance(body, dict) and body.get("retry_after_ms") is not None:
            return int(body["retry_after_ms"])
    except (ValueError, TypeError):
        logger.debug("503 body has no usable retry_after_ms; using Retry-After header")
    try:
        return int(float(retry_after_header) * 1000)
    except (TypeError, ValueError):
        return _DEFAULT_RETRY_AFTER_MS


def _parse_search_results(data: list[dict[str, Any]]) -> list[SearchResult]:
    """Convert JSON dicts to SearchResult objects.

    Supports both nested format (document + score) and flat format
    (id, content, score, metadata at top level) as returned by the server.
    """
    results: list[SearchResult] = []
    for item in data:
        doc_data = item.get("document")
        if doc_data is None:
            doc_data = {k: v for k, v in item.items() if k != "score"}
        doc = Document(
            id=doc_data.get("id", ""),
            content=doc_data.get("content", ""),
            metadata=doc_data.get("metadata") or {},
        )
        score = float(item.get("score", 1.0))
        results.append(SearchResult(document=doc, score=score))
    return results


def _parse_documents(data: list[dict[str, Any]]) -> list[Document]:
    """Convert JSON dicts to Document objects."""
    return [
        Document(
            id=d.get("id", ""),
            content=d.get("content", ""),
            metadata=d.get("metadata") or {},
        )
        for d in data
    ]


class VectorClient(VectorStore):
    """VectorStore client using either the internal HTTP API or an in-process bridge."""

    def __init__(
        self,
        anima_name: str,
        *,
        base_url: str | None = None,
        transport: VectorTransport | None = None,
    ) -> None:
        """Initialize with exactly one destination: HTTP URL or synchronous transport."""
        if not anima_name:
            raise ValueError("anima_name is required")
        if (base_url is None) == (transport is None):
            raise ValueError("exactly one of base_url or transport must be provided")
        if base_url is not None and not base_url.strip():
            raise ValueError("base_url must be non-empty")
        self._base_url = base_url.strip().rstrip("/") if base_url is not None else ""
        self._anima_name = anima_name
        self._transport: VectorTransport = transport if transport is not None else self._http_transport
        self._client: Any = None
        self._write_circuit_retry_at: dict[str, float] = {}
        self._write_circuit_warned: set[str] = set()
        self._write_circuit_suppressed: dict[str, int] = {}
        self._post_failure_states: dict[tuple[str, int | str, str], dict[str, Any]] = {}

    def _get_client(self):
        """Lazy-initialize httpx client."""
        if self._client is None:
            import httpx

            from core.internal_api import internal_api_headers

            # Upserts during bulk reindex can stall behind worker queue
            # pressure; 30s was too tight on a busy fleet.
            self._client = httpx.Client(
                base_url=self._base_url,
                timeout=120.0,
                headers=internal_api_headers(),
            )
        return self._client

    def _write_circuit_open(self, collection: str) -> bool:
        retry_at = self._write_circuit_retry_at.get(collection)
        if retry_at is None:
            return False
        now = time.monotonic()
        if retry_at <= now:
            self._write_circuit_retry_at.pop(collection, None)
            if collection in self._write_circuit_warned:
                logger.info(
                    "Vector write circuit closed; resuming writes: anima=%s collection=%s suppressed=%d writes",
                    self._anima_name or "shared",
                    collection,
                    self._write_circuit_suppressed.pop(collection, 0),
                )
                self._write_circuit_warned.discard(collection)
            return False
        if collection not in self._write_circuit_warned:
            logger.warning(
                "Skipping vector write while service circuit is open: anima=%s collection=%s retry_after=%ss",
                self._anima_name or "shared",
                collection,
                int(retry_at - now),
            )
            self._write_circuit_warned.add(collection)
            self._write_circuit_suppressed[collection] = 0
        else:
            self._write_circuit_suppressed[collection] = self._write_circuit_suppressed.get(collection, 0) + 1
        return True

    def is_transient_write_failure(self, collection: str) -> bool:
        """Return whether the last write failure opened the collection circuit."""
        retry_at = self._write_circuit_retry_at.get(collection)
        return retry_at is not None and retry_at > time.monotonic()

    def _record_write_circuit(self, collection: str, retry_after_seconds: float) -> None:
        delay = max(0.001, retry_after_seconds)
        self._write_circuit_retry_at[collection] = time.monotonic() + delay

    def _clear_post_failures(
        self, path: str, collection: str, *, keep: tuple[str, int | str, str] | None = None
    ) -> None:
        for key in list(self._post_failure_states):
            if key[0] == path and key[2] == collection and key != keep:
                self._post_failure_states.pop(key, None)

    def _log_post_failure(
        self,
        path: str,
        status: int | str,
        collection: str,
        retry_after: str | None,
        error: Exception,
    ) -> None:
        key = (path, status, collection)
        self._clear_post_failures(path, collection, keep=key)
        now = time.monotonic()
        state = self._post_failure_states.get(key)
        if state is None:
            logger.warning(
                "HTTP vector request failed: path=%s status=%s collection=%s retry_after=%s error=%s",
                path,
                status,
                collection or "-",
                retry_after or "-",
                error,
            )
            self._post_failure_states[key] = {
                "last_logged_at": now,
                "suppressed_count": 0,
                "first_retry_after": retry_after,
            }
            return

        state["suppressed_count"] = int(state.get("suppressed_count") or 0) + 1
        if now - float(state.get("last_logged_at") or 0.0) < _FAILURE_LOG_INTERVAL_SECONDS:
            return
        logger.warning(
            "HTTP vector request failures continue: path=%s status=%s collection=%s "
            "retry_after=%s suppressed=%d error=%s",
            path,
            status,
            collection or "-",
            state.get("first_retry_after") or "-",
            state["suppressed_count"],
            error,
        )
        state["last_logged_at"] = now
        state["suppressed_count"] = 0

    def _request(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        write_collection: str | None = None,
        allow_retry: bool = False,
    ) -> dict[str, Any] | None:
        """Dispatch to the configured transport with a single retry on reads.

        Reads (``allow_retry=True``) retry once after the owner's reported
        ``retry_after_ms`` when it answers UNAVAILABLE; writes return False
        immediately so callers can mark transient write failures.
        """

        if write_collection and self._write_circuit_open(write_collection):
            return None

        def dispatch() -> dict[str, Any] | None:
            return self._transport(path, payload)

        try:
            return dispatch()
        except VectorStoreRetryableError as exc:
            if write_collection is not None:
                self._record_write_circuit(write_collection, exc.retry_after_ms / 1000.0)
            delay_ms = _retry_after_ms(exc) if allow_retry else None
            if delay_ms is None:
                return None
            logger.warning(
                "Vector request retryable: path=%s anima=%s retry_after_ms=%s error=%s",
                path,
                self._anima_name or "shared",
                delay_ms,
                exc,
            )
            if delay_ms:
                time.sleep(delay_ms / 1000.0)
            try:
                return dispatch()
            except VectorStoreRetryableError as retry_exc:
                logger.warning(
                    "Vector request failed after retry: path=%s anima=%s error=%s",
                    path,
                    self._anima_name,
                    retry_exc,
                )
                return None
            except Exception as retry_exc:
                logger.warning(
                    "Vector request failed after retry: path=%s anima=%s error=%s",
                    path,
                    self._anima_name,
                    retry_exc,
                )
                return None
        except Exception as exc:
            logger.warning("Vector request failed: path=%s anima=%s error=%s", path, self._anima_name, exc)
            return None

    def _http_transport(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        """POST to the vector endpoint; classify retryable HTTP responses."""
        resp = None
        retry_after = None
        try:
            resp = self._get_client().post(path, json=payload)
            retry_after = resp.headers.get("Retry-After")
            if resp.status_code in {429, 503} or (resp.status_code == 500 and retry_after):
                if retry_after is not None:
                    raise VectorStoreRetryableError(
                        f"vector service unavailable ({resp.status_code})",
                        retry_after_ms=_response_retry_after_ms(resp, retry_after),
                    )
            resp.raise_for_status()
            data = resp.json()
            self._clear_post_failures(path, str(payload.get("collection", "")))
            return data
        except VectorStoreRetryableError:
            raise
        except Exception as e:
            status: int | str = getattr(resp, "status_code", "exception") if resp is not None else "exception"
            self._log_post_failure(path, status, str(payload.get("collection", "")), retry_after, e)
            return None

    def create_collection(self, name: str) -> bool:
        """Create a new collection."""
        return (
            self._request(
                "/create-collection",
                {"anima_name": self._anima_name, "collection": name},
                write_collection=name,
            )
            is not None
        )

    def delete_collection(self, name: str) -> bool:
        """Delete a collection."""
        return (
            self._request(
                "/delete-collection",
                {"anima_name": self._anima_name, "collection": name},
                write_collection=name,
            )
            is not None
        )

    def list_collections(self) -> list[str] | None:
        """List collection names, or return ``None`` when the result is unavailable."""
        data = self._request(
            "/list-collections",
            {"anima_name": self._anima_name},
            allow_retry=True,
        )
        if data is None or "collections" not in data:
            return None
        collections = data["collections"]
        if not isinstance(collections, list) or not all(isinstance(name, str) for name in collections):
            return None
        return list(collections)

    def upsert(self, collection: str, documents: list[Document]) -> bool:
        """Insert or update documents in a collection."""
        if not documents:
            return True
        ok = True
        for i in range(0, len(documents), _UPSERT_BATCH_LIMIT):
            batch = documents[i : i + _UPSERT_BATCH_LIMIT]
            payload = {
                "anima_name": self._anima_name,
                "collection": collection,
                "documents": [
                    {
                        "id": d.id,
                        "content": d.content,
                        "embedding": d.embedding,
                        "metadata": d.metadata,
                    }
                    for d in batch
                ],
            }
            if self._request("/upsert", payload, write_collection=collection) is None:
                ok = False
        return ok

    def query(
        self,
        collection: str,
        embedding: list[float],
        top_k: int = 10,
        filter_metadata: dict[str, str | int | float] | None = None,
    ) -> list[SearchResult]:
        """Query collection by embedding similarity."""
        payload: dict[str, Any] = {
            "anima_name": self._anima_name,
            "collection": collection,
            "embedding": embedding,
            "top_k": top_k,
        }
        if filter_metadata:
            payload["filter_metadata"] = filter_metadata
        data = self._request("/query", payload, allow_retry=True)
        if data and "results" in data:
            return _parse_search_results(data["results"])
        return []

    def delete_documents(self, collection: str, ids: list[str]) -> bool:
        """Delete specific documents by ID."""
        if not ids:
            return True
        return (
            self._request(
                "/delete-documents",
                {"anima_name": self._anima_name, "collection": collection, "ids": ids},
                write_collection=collection,
            )
            is not None
        )

    def update_metadata(self, collection: str, ids: list[str], metadatas: list[dict[str, str | int | float]]) -> bool:
        """Update metadata for existing documents."""
        if not ids:
            return True
        return (
            self._request(
                "/update-metadata",
                {"anima_name": self._anima_name, "collection": collection, "ids": ids, "metadatas": metadatas},
                write_collection=collection,
            )
            is not None
        )

    def get_by_metadata(
        self,
        collection: str,
        where: dict[str, str | int | float],
        limit: int = 20,
    ) -> list[SearchResult]:
        """Retrieve documents by metadata filter without embedding search."""
        data = self._request(
            "/get-by-metadata",
            {"anima_name": self._anima_name, "collection": collection, "where": where, "limit": limit},
            allow_retry=True,
        )
        if data and "results" in data:
            return _parse_search_results(data["results"])
        return []

    def get_by_ids(self, collection: str, ids: list[str]) -> list[Document]:
        """Fetch documents (with metadata) by their IDs."""
        if not ids:
            return []
        data = self._request(
            "/get-by-ids",
            {"anima_name": self._anima_name, "collection": collection, "ids": ids},
            allow_retry=True,
        )
        if data and "documents" in data:
            return _parse_documents(data["documents"])
        return []

    def close(self) -> None:
        """Close the HTTP client if created."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception as e:
                logger.warning("Failed to close HTTP client: %s", e)
            self._client = None
