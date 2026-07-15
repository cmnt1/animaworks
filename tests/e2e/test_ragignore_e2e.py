# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""E2E tests for .ragignore support in MemoryIndexer.

Verifies that index_directory() skips files matching .ragignore patterns
using a real MemoryIndexer and ChromaDB store.
"""

from __future__ import annotations

from pathlib import Path

import pytest

chromadb = pytest.importorskip(
    "chromadb",
    reason="ChromaDB not installed. Install with: pip install 'animaworks[rag]'",
)
sentence_transformers = pytest.importorskip(
    "sentence_transformers",
    reason="sentence-transformers not installed. Install with: pip install 'animaworks[rag]'",
)


# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch) -> Path:
    """Create isolated data directory with .ragignore and ANIMAWORKS_DATA_DIR."""
    data_dir = tmp_path / ".animaworks"
    data_dir.mkdir()
    (data_dir / "models").mkdir()
    (data_dir / "shared" / "users").mkdir(parents=True)
    (data_dir / "common_skills").mkdir()

    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(data_dir))

    from core.paths import _prompt_cache

    _prompt_cache.clear()

    yield data_dir


@pytest.fixture
def anima_dir(data_dir: Path) -> Path:
    """Create anima directory with knowledge subdir."""
    anima_dir = data_dir / "animas" / "test_anima"
    anima_dir.mkdir(parents=True)
    (anima_dir / "knowledge").mkdir()
    (anima_dir / "vectordb").mkdir()
    return anima_dir


@pytest.fixture
def vector_store(anima_dir: Path):
    """Create ChromaDB vector store in temp directory."""
    from core.memory.rag.store import ChromaVectorStore

    return ChromaVectorStore(persist_dir=anima_dir / "vectordb")


@pytest.fixture
def indexer(vector_store, anima_dir: Path):
    """Create MemoryIndexer bound to test anima directory."""
    from core.memory.rag.indexer import MemoryIndexer

    return MemoryIndexer(vector_store, "test_anima", anima_dir)


# ── E2E: index_directory respects .ragignore ─────────────────────────


def test_ragignore_excludes_files_from_index(
    data_dir: Path,
    anima_dir: Path,
    indexer,
    vector_store,
) -> None:
    """index_directory() indexes only non-ragignored files.

    1. Creates .ragignore with excluded.md
    2. Creates excluded.md and included.md in knowledge
    3. Runs index_directory() and verifies only included.md was indexed
    """
    # Create .ragignore at data dir (get_data_dir() returns data_dir)
    ragignore = data_dir / ".ragignore"
    ragignore.write_text("excluded.md\n", encoding="utf-8")

    knowledge_dir = anima_dir / "knowledge"

    # Create both files
    (knowledge_dir / "excluded.md").write_text(
        "# Excluded\n\nThis file should NOT be indexed.",
        encoding="utf-8",
    )
    (knowledge_dir / "included.md").write_text(
        "# Included\n\nThis file should be indexed.\n\n## Section\n\nContent here.",
        encoding="utf-8",
    )

    # Clear ragignore cache to ensure fresh load
    from core.memory.rag.indexer import MemoryIndexer

    MemoryIndexer._ragignore_cache = None

    # Index directory
    total = indexer.index_directory(knowledge_dir, "knowledge").chunks_indexed

    # Should have indexed only included.md (at least 1 chunk)
    assert total > 0

    # Verify ChromaDB collection: only included.md chunks present
    coll = vector_store.client.get_collection(name="test_anima_knowledge")
    all_data = coll.get(include=["metadatas"])

    source_files = [m.get("source_file", "") for m in all_data["metadatas"]]
    assert "knowledge/included.md" in source_files
    assert "knowledge/excluded.md" not in source_files
