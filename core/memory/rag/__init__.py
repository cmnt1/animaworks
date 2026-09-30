from __future__ import annotations

"""RAG APIs, loaded only when explicitly requested."""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "MemoryIndexer": "core.memory.rag.indexer",
    "MemoryRetriever": "core.memory.rag.retriever",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value


__all__ = sorted(_EXPORTS)
