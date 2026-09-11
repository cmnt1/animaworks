from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for the model-driven forgetting pipeline (harness diet PR-7).

The mechanical (delete + archive) forgetting pipeline was removed.  The
engine now only *lists* low-activation candidates for the model to review
during weekly consolidation, so source files and vectors are left intact.
"""

from pathlib import Path

from core.memory.forgetting import ForgettingEngine

_META = {
    "memory_type": "knowledge",
    "activation_level": "low",
    "low_activation_since": "2019-01-01T00:00:00",
    "access_count": 0,
    "source_file": "knowledge/test.md",
    "importance": "",
}


class TestListForgettingCandidates:
    """Verify list_forgetting_candidates() only lists, never deletes/archives."""

    def _engine(self, tmp_path: Path, chunks):
        anima_dir = tmp_path / "test_anima"
        (anima_dir / "knowledge").mkdir(parents=True)
        source = anima_dir / "knowledge" / "test.md"
        source.write_text("test content", encoding="utf-8")

        engine = ForgettingEngine(anima_dir, "test_anima")

        def fake_get_all_chunks(collection_name: str):
            if "knowledge" in collection_name:
                return chunks
            return []

        engine._get_vector_store = lambda: MagicMockStore()  # type: ignore[union-attr]
        engine._get_all_chunks = fake_get_all_chunks
        return engine, source

    def test_lists_eligible_chunk_without_deleting(self, tmp_path: Path) -> None:
        engine, source = self._engine(
            tmp_path,
            [
                {
                    "id": "chunk1",
                    "metadata": dict(_META),
                    "content": "test content",
                }
            ],
        )

        result = engine.list_forgetting_candidates()

        assert len(result) == 1
        assert result[0].path == "knowledge/test.md"
        # Nothing was archived or deleted
        assert source.exists()

    def test_unprotected_low_activation_is_a_candidate(self, tmp_path: Path) -> None:
        engine, _source = self._engine(tmp_path, [])
        engine._get_all_chunks = lambda _collection: [
            {"id": "c", "metadata": dict(_META), "content": "x"}
        ]
        assert len(engine.list_forgetting_candidates()) == 1

    def test_protected_chunk_not_a_candidate(self, tmp_path: Path) -> None:
        protected_meta = dict(_META, importance="important")
        engine, _source = self._engine(
            tmp_path,
            [{"id": "c", "metadata": protected_meta, "content": "x"}],
        )
        assert engine.list_forgetting_candidates() == []

    def test_rag_unavailable_returns_empty(self, tmp_path: Path) -> None:
        anima_dir = tmp_path / "test_anima"
        (anima_dir / "knowledge").mkdir(parents=True)
        engine = ForgettingEngine(anima_dir, "test_anima")
        engine._get_vector_store = lambda: None
        assert engine.list_forgetting_candidates() == []


class MagicMockStore:
    """Minimal stand-in so _get_vector_store() returns a truthy object."""

    def __bool__(self) -> bool:
        return True
