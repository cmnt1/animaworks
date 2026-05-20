from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock


def test_chroma_vector_store_close_is_idempotent(tmp_path: Path) -> None:
    from core.memory.rag.store import ChromaVectorStore

    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store.client = MagicMock()
    store.persist_dir = tmp_path
    store._closed = False

    store.close()
    store.close()

    store.client.close.assert_called_once()


def test_reset_vector_store_closes_cached_chroma_store() -> None:
    from core.memory.rag import singleton

    singleton._reset_for_testing()
    store = MagicMock()
    singleton._vector_stores["sora"] = store

    singleton.reset_vector_store("sora")

    store.close.assert_called_once()
    assert "sora" not in singleton._vector_stores
