"""Conversion between vector API requests and the MemoryService wire format."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Any

from core.memory.rag.vector_client import VectorStoreRetryableError, VectorTransport

# Endpoints that mirror a MemoryService method. Reset / repair / health are
# intentionally absent because they must not open a second native owner.
_PATH_TO_METHOD: dict[str, str] = {
    "/query": "memory.query",
    "/upsert": "memory.upsert",
    "/update-metadata": "memory.update_metadata",
    "/delete-documents": "memory.delete_documents",
    "/get-by-metadata": "memory.get_by_metadata",
    "/get-all": "memory.get_all",
    "/count": "memory.count",
    "/get-by-ids": "memory.get_by_ids",
    "/create-collection": "memory.create_collection",
    "/delete-collection": "memory.delete_collection",
    "/list-collections": "memory.list_collections",
}

_REQUEST_TIMEOUT_SECONDS = 125.0


class UnsupportedVectorPath(ValueError):
    """Raised when an endpoint has no MemoryService equivalent."""


def request_payload(params: dict[str, Any]) -> dict[str, Any]:
    """Memory-service params with the routing-only ``anima_name`` removed."""
    payload = dict(params)
    payload.pop("anima_name", None)
    return payload


def to_owner_interaction(path: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Translate an endpoint (path, payload) into a MemoryService request."""
    method = _PATH_TO_METHOD.get(path)
    if method is None:
        raise UnsupportedVectorPath(f"no MemoryService method for vector endpoint: {path}")
    return method, request_payload(payload)


MemoryHandler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def bridge_transport(
    handler: MemoryHandler,
    loop: asyncio.AbstractEventLoop,
    *,
    timeout: float = _REQUEST_TIMEOUT_SECONDS,
) -> VectorTransport:
    """Bridge synchronous VectorStore calls to an async memory handler."""
    loop_thread = threading.get_ident()

    def transport(path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if threading.get_ident() == loop_thread:
            raise RuntimeError("synchronous memory operation attempted on the root event loop")
        if loop.is_closed() or not loop.is_running():
            raise VectorStoreRetryableError("memory event loop is unavailable")

        method, params = to_owner_interaction(path, payload)
        future = asyncio.run_coroutine_threadsafe(handler(method, params), loop)
        try:
            result = future.result(timeout=timeout)
        except TimeoutError as exc:
            future.cancel()
            raise VectorStoreRetryableError("memory bridge request timed out") from exc
        except Exception as exc:
            raise VectorStoreRetryableError(f"memory bridge request failed: {exc}") from exc

        if isinstance(result, dict) and result.get("ok") is False:
            raise VectorStoreRetryableError(str(result.get("error") or "memory service unavailable"))
        return result

    return transport
