from __future__ import annotations

from pathlib import Path

import pytest


def test_environment_variable_does_not_authorize_direct_chroma(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.memory.rag.store import ChromaVectorStore

    monkeypatch.setenv("ANIMAWORKS_ALLOW_DIRECT_CHROMA", "1")

    with pytest.raises(RuntimeError, match="allow_direct=True"):
        ChromaVectorStore(persist_dir=tmp_path / "forbidden")


def test_allow_direct_opens_store_without_enabling_process_wide_access(tmp_path: Path) -> None:
    from core.memory.rag.store import ChromaVectorStore, create_chroma_vector_store

    store = create_chroma_vector_store(persist_dir=tmp_path / "vectordb", anima_name="sakura", allow_direct=True)
    try:
        assert store.client is not None
        with pytest.raises(RuntimeError, match="allow_direct=True"):
            ChromaVectorStore(persist_dir=tmp_path / "still-forbidden")
    finally:
        store.close()
