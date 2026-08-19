"""ChromaDB cleanup helpers for tests using temporary persistence directories."""

from __future__ import annotations

import gc
from typing import Any


def close_chroma_store(store: Any) -> None:
    """Release native Chroma handles before a temporary directory is removed."""
    store.close()
    from chromadb.api.client import SharedSystemClient

    SharedSystemClient.clear_system_cache()
    gc.collect()
