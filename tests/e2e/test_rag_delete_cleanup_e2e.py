from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""E2E coverage for source-file RAG cleanup."""

import pytest

chromadb = pytest.importorskip(
    "chromadb",
    reason="ChromaDB not installed. Install with: pip install 'animaworks[rag]'",
)
sentence_transformers = pytest.importorskip(
    "sentence_transformers",
    reason="sentence-transformers not installed. Install with: pip install 'animaworks[rag]'",
)

pytestmark = pytest.mark.e2e


@pytest.fixture
def anima_dir(tmp_path, monkeypatch):
    """Create an isolated anima directory with ANIMAWORKS_DATA_DIR redirected."""
    data_dir = tmp_path / ".animaworks"
    data_dir.mkdir()
    (data_dir / "models").mkdir()

    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(data_dir))

    from core.paths import _prompt_cache

    _prompt_cache.clear()

    anima_dir = data_dir / "animas" / "test_anima"
    anima_dir.mkdir(parents=True)
    for subdir in ("knowledge", "episodes", "skills", "procedures", "state", "vectordb"):
        (anima_dir / subdir).mkdir()
    return anima_dir


@pytest.fixture
def vector_store(anima_dir):
    """Create a ChromaDB vector store persisted under the anima's vectordb dir."""
    from core.memory.rag.store import ChromaVectorStore

    return ChromaVectorStore(persist_dir=anima_dir / "vectordb")


@pytest.fixture
def indexer(vector_store, anima_dir):
    """Create a MemoryIndexer bound to the test anima directory."""
    from core.memory.rag.indexer import MemoryIndexer

    return MemoryIndexer(vector_store, "test_anima", anima_dir)


def test_e2e_delete_indexed_file_removes_source_chunks(anima_dir, indexer, vector_store):
    """Deleting an indexed source removes its chunks from the vector store."""
    source = anima_dir / "knowledge" / "stale-delete.md"
    source.write_text(
        "# Stale source\n\n"
        "## Cleanup\n\n"
        "This document should disappear from the vector store after deletion cleanup.\n",
        encoding="utf-8",
    )

    indexed = indexer.index_file(source, "knowledge", force=True)
    assert indexed > 0

    source_file = "knowledge/stale-delete.md"
    before = vector_store.get_by_metadata(
        "test_anima_knowledge",
        {"source_file": source_file},
        limit=10,
    )
    assert before
    assert source_file in indexer.index_meta

    source.unlink()
    deleted = indexer.delete_indexed_file(source, "knowledge")

    assert deleted == len(before)
    after = vector_store.get_by_metadata(
        "test_anima_knowledge",
        {"source_file": source_file},
        limit=10,
    )
    assert after == []
    assert source_file not in indexer.index_meta
