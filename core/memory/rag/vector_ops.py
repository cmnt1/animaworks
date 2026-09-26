"""Conversion between the HTTP vector API and the MemoryService wire format.

The HTTP vector endpoints (path + JSON payload) and a phase3 root's
``MemoryService.handle`` requests (a ``memory.*`` method + params) carry the
same logical data. Both the server (when it forwards a phase3 request to
that root) and the root's own in-process owner path need to translate
between them, so both directions live here and are defined once.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Any

# Endpoints that mirror a root MemoryService method. These are exactly the
# requests the server forwards for a phase3 owner (see
# server/routes/internal.py). Reset / repair / health are worker-only and
# intentionally absent here — they must not open a second native owner.
_PATH_TO_METHOD: dict[str, str] = {
    "/query": "memory.query",
    "/upsert": "memory.upsert",
    "/update-metadata": "memory.update_metadata",
    "/delete-documents": "memory.delete_documents",
    "/get-by-metadata": "memory.get_by_metadata",
    "/get-by-ids": "memory.get_by_ids",
    "/create-collection": "memory.create_collection",
    "/delete-collection": "memory.delete_collection",
    "/list-collections": "memory.list_collections_checked",
}


class UnsupportedVectorPath(ValueError):
    """Raised when an endpoint has no MemoryService equivalent."""


def request_payload(params: dict[str, Any]) -> dict[str, Any]:
    """Memory-service params with the routing-only ``anima_name`` removed."""
    payload = dict(params)
    payload.pop("anima_name", None)
    return payload


def to_owner_interaction(path: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Translate an endpoint (path, payload) into a MemoryService request.

    Returns ``(method, params)`` suitable for ``MemoryService.handle`` or the
    server's ``send_request(anima, "memory", ...)`` envelope.
    """
    method = _PATH_TO_METHOD.get(path)
    if method is None:
        raise UnsupportedVectorPath(f"no MemoryService method for vector endpoint: {path}")
    return method, request_payload(payload)


SendRequest = Callable[[str, str, dict[str, Any]], Awaitable[dict[str, Any]]]


def supervisor_transport(
    send_request: SendRequest,
    anima_name: str,
) -> Callable[[str, dict[str, Any]], dict[str, Any] | None]:
    """Build a VectorTransport that forwards a phase3 request to its root.

    Used by the daily indexer, which runs on the root's event loop but
    calls the store from worker threads. ``send_request`` is the server's
    async ``supervisor.send_request(anima_name, "memory", envelope)``; the
    transport bridges it to the owning loop when invoked off-thread.
    """
    loop = asyncio.get_running_loop()
    loop_thread = threading.get_ident()

    def transport(path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if threading.get_ident() == loop_thread:
            raise RuntimeError("synchronous memory operation attempted on the root event loop")
        if loop.is_closed() or not loop.is_running():
            raise RuntimeError("root memory event loop is unavailable")
        method, params = to_owner_interaction(path, payload)
        future = asyncio.run_coroutine_threadsafe(
            send_request(anima_name, "memory", {"method": method, "params": params}),
            loop,
        )
        return future.result(timeout=125.0)

    return transport
