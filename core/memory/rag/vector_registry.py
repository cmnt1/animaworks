from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Registry and cache for remote vector clients."""

import logging
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.memory.rag.store import VectorStore
    from core.memory.rag.vector_client import VectorClient, VectorTransport

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_http_stores: dict[tuple[str, str], VectorClient] = {}
_owner_transport: VectorTransport | None = None
_owner_anima: str | None = None
_owner_stores: dict[str, VectorClient] = {}
_server_send_request: Callable[..., Any] | None = None
_server_loop = None
_server_stores: dict[str, VectorClient] = {}
_no_backend_warned = False
_shared_store_disabled_warned = False


def _get_http_store(base_url: str, anima_name: str) -> VectorClient:
    """Return the cached HTTP VectorClient for the given URL and owner."""
    normalized_url = base_url.rstrip("/")
    key = (normalized_url, anima_name)
    with _lock:
        store = _http_stores.get(key)
        if store is None:
            from core.memory.rag.vector_client import VectorClient

            store = VectorClient(anima_name, base_url=normalized_url)
            _http_stores[key] = store
        return store


def configure_owner_vector_access(transport: VectorTransport | None, *, anima_name: str | None = None) -> None:
    """Install the root's in-process bridge to its MemoryService."""
    global _owner_transport, _owner_anima

    with _lock:
        _owner_transport = transport
        _owner_anima = anima_name if transport is not None else None
        _owner_stores.clear()


def configure_owner_transport(transport: VectorTransport | None, *, anima_name: str | None = None) -> None:
    """Alias emphasizing that the owner bridge is a transport configuration."""
    configure_owner_vector_access(transport, anima_name=anima_name)


def _get_owner_store(anima_name: str) -> VectorClient | None:
    transport = _owner_transport
    if transport is None:
        return None
    if _owner_anima is not None and anima_name != _owner_anima:
        logger.warning("Root vector store owner mismatch: requested=%s owner=%s", anima_name, _owner_anima)
        return None
    with _lock:
        store = _owner_stores.get(anima_name)
        if store is None:
            from core.memory.rag.vector_client import VectorClient

            store = VectorClient(anima_name, transport=transport)
            _owner_stores[anima_name] = store
        return store


def configure_server_vector_access(send_request: Callable[..., Any] | None, loop: Any = None) -> None:
    """Configure this server process to forward vector operations to roots."""
    global _server_send_request, _server_loop
    with _lock:
        _server_send_request = send_request
        _server_loop = loop if send_request is not None else None
        _server_stores.clear()


def _get_server_store(anima_name: str) -> VectorClient | None:
    send_request = _server_send_request
    loop = _server_loop
    if send_request is None or loop is None:
        return None
    with _lock:
        store = _server_stores.get(anima_name)
        if store is None:
            from core.memory.rag.vector_client import VectorClient
            from core.memory.rag.vector_ops import bridge_transport

            async def send_memory(method: str, params: dict[str, Any]) -> dict[str, Any]:
                return await send_request(anima_name, "memory", {"method": method, "params": params})

            store = VectorClient(anima_name, transport=bridge_transport(send_memory, loop))
            _server_stores[anima_name] = store
        return store


def get_vector_store(anima_name: str | None = None) -> VectorStore | None:
    """Return a cached vector client using configured in-process or HTTP access.

    Native Chroma stores are owned exclusively by ``MemoryService``. Without
    a configured bridge or vector URL, this returns ``None`` rather than
    opening a local database.
    """
    global _no_backend_warned, _shared_store_disabled_warned

    if not anima_name:
        with _lock:
            if not _shared_store_disabled_warned:
                logger.warning("Shared vector store access is disabled; use an Anima-owned vector store")
                _shared_store_disabled_warned = True
        return None

    # An explicitly configured root transport owns the routing decision,
    # including rejecting a request for another anima.
    if _owner_transport is not None:
        return _get_owner_store(anima_name)
    if _server_send_request is not None and _server_loop is not None:
        return _get_server_store(anima_name)

    from core.memory.rag.endpoints import get_endpoints

    vector_url = get_endpoints().vector_url
    if vector_url:
        return _get_http_store(vector_url, anima_name)

    with _lock:
        if not _no_backend_warned:
            logger.warning("Vector store unavailable: no in-process owner transport or vector URL is configured")
            _no_backend_warned = True
    return None


def _reset_for_testing() -> None:
    """Clear process-local client caches and configuration for test isolation."""
    global _no_backend_warned, _shared_store_disabled_warned
    global _owner_transport, _owner_anima, _server_send_request, _server_loop

    with _lock:
        _http_stores.clear()
        _owner_stores.clear()
        _server_stores.clear()
        _owner_transport = None
        _owner_anima = None
        _server_send_request = None
        _server_loop = None
        _no_backend_warned = False
        _shared_store_disabled_warned = False

    from core.memory.rag.endpoints import configure_endpoints

    configure_endpoints(None)
