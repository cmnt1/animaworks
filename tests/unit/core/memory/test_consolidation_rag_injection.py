from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.memory.maintenance.consolidation import ConsolidationEngine


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    """Create a minimal anima directory structure."""
    d = tmp_path / "animas" / "test_anima"
    d.mkdir(parents=True)
    return d


def _write_merge_candidates(engine: ConsolidationEngine) -> None:
    (engine.knowledge_dir / "first.md").write_text("First knowledge.", encoding="utf-8")
    (engine.knowledge_dir / "second.md").write_text("Second knowledge.", encoding="utf-8")


class TestConsolidationRagStoreConstructor:
    def test_default_rag_store_is_none(self, anima_dir: Path) -> None:
        engine = ConsolidationEngine(anima_dir, "test")
        assert engine._rag_store is None

    def test_injected_rag_store_is_stored(self, anima_dir: Path) -> None:
        mock_store = MagicMock()
        engine = ConsolidationEngine(anima_dir, "test", rag_store=mock_store)
        assert engine._rag_store is mock_store

    def test_rag_store_keyword_only(self, anima_dir: Path) -> None:
        mock_store = MagicMock()
        with pytest.raises(TypeError):
            ConsolidationEngine(anima_dir, "test", mock_store)  # type: ignore[misc]


class TestMergeCandidateRagStoreInjection:
    def test_uses_injected_store(self, anima_dir: Path) -> None:
        mock_store = MagicMock()
        engine = ConsolidationEngine(anima_dir, "test", rag_store=mock_store)
        _write_merge_candidates(engine)

        with (
            patch("core.memory.rag.MemoryIndexer") as mock_indexer,
            patch("core.memory.rag.retriever.MemoryRetriever") as mock_retriever,
            patch("core.memory.rag.vector_registry.get_vector_store") as mock_get_store,
        ):
            mock_retriever.return_value.search.return_value = []
            assert engine._find_merge_candidates() == []

        mock_get_store.assert_not_called()
        mock_indexer.assert_called_once_with(mock_store, "test", anima_dir)

    def test_falls_back_to_singleton_store(self, anima_dir: Path) -> None:
        engine = ConsolidationEngine(anima_dir, "test")
        _write_merge_candidates(engine)
        singleton_store = MagicMock()

        with (
            patch("core.memory.rag.MemoryIndexer") as mock_indexer,
            patch("core.memory.rag.retriever.MemoryRetriever") as mock_retriever,
            patch("core.memory.rag.vector_registry.get_vector_store", return_value=singleton_store) as mock_get_store,
        ):
            mock_retriever.return_value.search.return_value = []
            assert engine._find_merge_candidates() == []

        mock_get_store.assert_called_once_with("test")
        mock_indexer.assert_called_once_with(singleton_store, "test", anima_dir)
