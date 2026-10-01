from __future__ import annotations

import inspect
from pathlib import Path

import pytest


def test_environment_variable_does_not_authorize_direct_chroma(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.memory.rag.store import ChromaVectorStore

    monkeypatch.setenv("ANIMAWORKS_ALLOW_DIRECT_CHROMA", "1")

    with pytest.raises(RuntimeError, match="owner capability"):
        ChromaVectorStore(persist_dir=tmp_path / "forbidden")


def test_boolean_allow_direct_does_not_bypass_guard(tmp_path: Path) -> None:
    from core.memory.rag.store import ChromaVectorStore

    with pytest.raises(RuntimeError, match="owner capability"):
        ChromaVectorStore(persist_dir=tmp_path / "forbidden", allow_direct=True)  # type: ignore[arg-type]


def test_persist_dir_is_required() -> None:
    from core.memory.rag.store import ChromaVectorStore

    assert inspect.signature(ChromaVectorStore).parameters["persist_dir"].default is inspect.Parameter.empty


def test_none_persist_dir_is_rejected(tmp_path: Path) -> None:
    from core.memory.rag.direct_access import OWNER_CAPABILITY
    from core.memory.rag.store import ChromaVectorStore

    with pytest.raises(ValueError, match="persist_dir is required"):
        ChromaVectorStore(persist_dir=None, allow_direct=OWNER_CAPABILITY)  # type: ignore[arg-type]


def test_owner_capability_opens_store_without_enabling_process_wide_access(tmp_path: Path) -> None:
    from core.memory.rag.direct_access import OWNER_CAPABILITY
    from core.memory.rag.store import ChromaVectorStore, create_chroma_vector_store

    store = create_chroma_vector_store(
        persist_dir=tmp_path / "vectordb",
        anima_name="sakura",
        allow_direct=OWNER_CAPABILITY,
    )
    try:
        assert store.client is not None
        with pytest.raises(RuntimeError, match="owner capability"):
            ChromaVectorStore(persist_dir=tmp_path / "still-forbidden")
    finally:
        store.close()
