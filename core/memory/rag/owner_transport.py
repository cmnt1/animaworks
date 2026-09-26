"""In-process owner transport for a phase3 root's own MemoryService.

A phase3 root owns the native Chroma handle. Its inbox and tool code run
in this same process, so routing those reads/writes through HTTP would add
a needless round trip to itself. ``owner_transport`` turns the root's
async ``MemoryService.handle`` into a ``VectorTransport`` that
``HttpVectorStore`` can consume like any other transport — the single
client class, with only the destination swapped.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Awaitable, Callable
from typing import Any

from core.memory.rag.http_store import VectorStoreRetryableError
from core.memory.rag.vector_ops import to_owner_interaction

MemoryHandle = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

_REQUEST_TIMEOUT_SECONDS = 125.0


def owner_transport(handle_memory: MemoryHandle, loop: asyncio.AbstractEventLoop) -> Callable[[str, dict], dict | None]:
    """Return a VectorTransport that routes to the owner MemoryService.

    Bridges synchronous off-loop callers (tool threads) to the owner's
    event loop, preserving the old thread-bridge semantics.
    ``MemoryServiceUnavailable`` is surfaced as a retryable signal so the
    shared client retry logic applies uniformly to HTTP and owner paths.
    """
    loop_thread = threading.get_ident()

    def transport(path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        if threading.get_ident() == loop_thread:
            raise RuntimeError("synchronous memory operation attempted on the root event loop")
        if loop.is_closed() or not loop.is_running():
            raise RuntimeError("root memory event loop is unavailable")
        method, params = to_owner_interaction(path, payload)
        future = asyncio.run_coroutine_threadsafe(handle_memory(method, params), loop)
        try:
            return future.result(timeout=_REQUEST_TIMEOUT_SECONDS)
        except TimeoutError:
            future.cancel()
            raise
        except Exception as exc:
            _maybe_retryable(exc)
            raise

    return transport


def _maybe_retryable(exc: BaseException) -> None:
    """Translate the owner's unavailable signal into a retryable error."""
    from core.supervisor.memory_service import MemoryServiceUnavailable

    if isinstance(exc, MemoryServiceUnavailable):
        raise VectorStoreRetryableError(str(exc)) from exc
