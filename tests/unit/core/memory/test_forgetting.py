from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Tests for the active forgetting mechanism.

Tests cover:
- ForgettingEngine._is_protected() classification
- Synaptic downscaling (Stage 1)
- Forgetting candidate listing (model-driven weekly review, Stage 2)
- Integration with ConsolidationEngine (daily hook)
"""

from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from core.memory.forgetting import (
    ForgettingEngine,
)
from core.time_utils import now_jst

# ── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    """Create a temporary anima directory structure."""
    anima_dir = tmp_path / "test_anima"
    anima_dir.mkdir()
    (anima_dir / "knowledge").mkdir()
    (anima_dir / "episodes").mkdir()
    (anima_dir / "procedures").mkdir()
    (anima_dir / "skills").mkdir()
    return anima_dir


@pytest.fixture
def forgetting_engine(anima_dir: Path) -> ForgettingEngine:
    """Create a ForgettingEngine instance."""
    return ForgettingEngine(anima_dir=anima_dir, anima_name="test_anima")


def _make_chunk(
    doc_id: str = "chunk1",
    content: str = "test content",
    memory_type: str = "knowledge",
    importance: str = "normal",
    access_count: int = 0,
    last_accessed_at: str = "",
    updated_at: str = "",
    activation_level: str = "normal",
    low_activation_since: str = "",
    source_file: str = "knowledge/test.md",
) -> dict[str, Any]:
    """Helper to create a chunk dict matching _get_all_chunks format."""
    return {
        "id": doc_id,
        "content": content,
        "metadata": {
            "memory_type": memory_type,
            "importance": importance,
            "access_count": access_count,
            "last_accessed_at": last_accessed_at,
            "updated_at": updated_at,
            "activation_level": activation_level,
            "low_activation_since": low_activation_since,
            "source_file": source_file,
        },
    }


# ── _is_protected Tests ─────────────────────────────────────────────


class TestIsProtected:
    """Test _is_protected() classification of chunks."""

    def test_is_protected_procedures_not_blanket(self, forgetting_engine):
        """Verify that memory_type='procedures' is NOT blanket-protected.

        Procedures are no longer in PROTECTED_MEMORY_TYPES. They use
        utility-based protection via _is_protected_procedure instead.
        A basic procedure with importance='normal' and version=1 is not protected.
        """
        meta = {"memory_type": "procedures", "importance": "normal", "version": 1}
        assert forgetting_engine._is_protected(meta) is False

    def test_is_protected_skills(self, forgetting_engine):
        """Verify that memory_type='skills' is protected from forgetting."""
        meta = {"memory_type": "skills", "importance": "normal"}
        assert forgetting_engine._is_protected(meta) is True

    def test_is_protected_shared_users(self, forgetting_engine):
        """Verify that memory_type='shared_users' is protected from forgetting."""
        meta = {"memory_type": "shared_users", "importance": "normal"}
        assert forgetting_engine._is_protected(meta) is True

    def test_is_protected_important(self, forgetting_engine):
        """Verify that importance='important' is protected regardless of type."""
        meta = {"memory_type": "knowledge", "importance": "important"}
        assert forgetting_engine._is_protected(meta) is True

    def test_is_protected_expired_important_knowledge_can_forget(self, forgetting_engine):
        """[IMPORTANT] knowledge becomes eligible after the safety-net window."""
        old_date = (now_jst() - timedelta(days=370)).isoformat()
        meta = {
            "memory_type": "knowledge",
            "importance": "important",
            "access_count": 0,
            "updated_at": old_date,
        }
        assert forgetting_engine._is_protected(meta) is False

    def test_is_protected_expired_important_procedure_can_forget(self, forgetting_engine):
        """[IMPORTANT] procedures lose tag protection after the safety-net window."""
        old_date = (now_jst() - timedelta(days=370)).isoformat()
        meta = {
            "memory_type": "procedures",
            "importance": "important",
            "access_count": 0,
            "updated_at": old_date,
            "version": 1,
            "protected": False,
        }
        assert forgetting_engine._is_protected(meta) is False

    def test_is_protected_expired_important_skills_and_users_stay_protected(self, forgetting_engine):
        """Permanent memory types stay protected even when [IMPORTANT] expires."""
        old_date = (now_jst() - timedelta(days=370)).isoformat()
        base = {
            "importance": "important",
            "access_count": 0,
            "updated_at": old_date,
        }
        assert forgetting_engine._is_protected({**base, "memory_type": "skills"}) is True
        assert forgetting_engine._is_protected({**base, "memory_type": "shared_users"}) is True

    def test_is_protected_normal_knowledge(self, forgetting_engine):
        """Verify that memory_type='knowledge', importance='normal' is NOT protected."""
        meta = {"memory_type": "knowledge", "importance": "normal"}
        assert forgetting_engine._is_protected(meta) is False

    def test_is_protected_normal_episodes(self, forgetting_engine):
        """Verify that memory_type='episodes', importance='normal' is NOT protected."""
        meta = {"memory_type": "episodes", "importance": "normal"}
        assert forgetting_engine._is_protected(meta) is False


# ── Synaptic Downscaling Tests ──────────────────────────────────────


class TestSynapticDownscaling:
    """Test synaptic_downscaling() (Stage 1: daily mark low-activation)."""

    def test_synaptic_downscaling_marks_old_chunks(self, forgetting_engine):
        """Test that old chunks with no access are marked as low activation.

        Chunks that are >90 days old with access_count=0 should be marked
        with activation_level='low'.
        """
        old_date = (now_jst() - timedelta(days=120)).isoformat()
        knowledge_chunks = [
            _make_chunk(
                doc_id="old_chunk",
                access_count=0,
                last_accessed_at="",
                updated_at=old_date,
                activation_level="normal",
            ),
        ]

        def get_chunks(collection_name):
            if "knowledge" in collection_name:
                return knowledge_chunks
            return []  # No episode chunks

        mock_store = MagicMock()
        mock_store.update_metadata = MagicMock()

        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=mock_store),
            patch.object(forgetting_engine, "_get_all_chunks", side_effect=get_chunks),
        ):
            result = forgetting_engine.synaptic_downscaling()

        assert result["scanned"] == 1
        assert result["marked_low"] == 1

        # Verify update_metadata was called with correct args
        mock_store.update_metadata.assert_called_once()
        call_args = mock_store.update_metadata.call_args[0]
        assert call_args[0] == "test_anima_knowledge"
        assert call_args[1] == ["old_chunk"]
        assert call_args[2][0]["activation_level"] == "low"
        assert call_args[2][0]["low_activation_since"] != ""

    def test_synaptic_downscaling_skips_protected(self, forgetting_engine):
        """Test that chunks with importance='important' are NOT marked.

        Protected chunks should be skipped even if they are old and unaccessed.
        """
        old_date = (now_jst() - timedelta(days=120)).isoformat()
        knowledge_chunks = [
            _make_chunk(
                doc_id="important_chunk",
                importance="important",
                access_count=0,
                last_accessed_at="",
                updated_at=old_date,
                activation_level="normal",
            ),
        ]

        def get_chunks(collection_name):
            if "knowledge" in collection_name:
                return knowledge_chunks
            return []

        mock_store = MagicMock()
        mock_store.update_metadata = MagicMock()

        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=mock_store),
            patch.object(forgetting_engine, "_get_all_chunks", side_effect=get_chunks),
        ):
            result = forgetting_engine.synaptic_downscaling()

        assert result["scanned"] == 1
        assert result["marked_low"] == 0
        mock_store.update_metadata.assert_not_called()

    def test_synaptic_downscaling_skips_frequently_accessed(self, forgetting_engine):
        """Test that chunks with access_count >= threshold are NOT marked.

        Frequently accessed chunks (access_count >= DOWNSCALING_ACCESS_THRESHOLD)
        should be skipped even if they are old.
        """
        old_date = (now_jst() - timedelta(days=120)).isoformat()
        chunks = [
            _make_chunk(
                doc_id="accessed_chunk",
                access_count=5,  # Above threshold of 3
                last_accessed_at="",
                updated_at=old_date,
                activation_level="normal",
            ),
        ]

        mock_store = MagicMock()
        mock_store.update_metadata = MagicMock()

        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=mock_store),
            patch.object(forgetting_engine, "_get_all_chunks", return_value=chunks),
        ):
            result = forgetting_engine.synaptic_downscaling()

        assert result["marked_low"] == 0
        mock_store.update_metadata.assert_not_called()

    def test_synaptic_downscaling_protects_retrieved_only_chunks(self, forgetting_engine):
        """F11: automatic recall (access_count) protects a chunk from downscaling.

        A chunk that is retrieved frequently but never explicitly "used" still
        counts as recently used (``used_count + access_count`` and
        ``max(last_used_at, last_accessed_at)``), so it must NOT be marked
        low-activation.
        """
        old_date = (now_jst() - timedelta(days=120)).isoformat()
        recent_retrieval = (now_jst() - timedelta(days=1)).isoformat()
        chunks = [
            _make_chunk(
                doc_id="retrieved_only",
                access_count=50,
                last_accessed_at=recent_retrieval,
                updated_at=old_date,
                activation_level="normal",
            ),
        ]
        chunks[0]["metadata"].update(
            {
                "retrieved_count": 250,
                "used_count": 0,
                "last_retrieved_at": recent_retrieval,
                "last_used_at": "",
            }
        )

        mock_store = MagicMock()
        mock_store.update_metadata = MagicMock()

        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=mock_store),
            patch.object(forgetting_engine, "_get_all_chunks", return_value=chunks),
        ):
            result = forgetting_engine.synaptic_downscaling()

        assert result["marked_low"] == 0
        mock_store.update_metadata.assert_not_called()

    def test_synaptic_downscaling_skips_recent(self, forgetting_engine):
        """Test that recently accessed chunks are NOT marked.

        Chunks accessed within the last 90 days should not be marked
        regardless of access_count.
        """
        recent_date = (now_jst() - timedelta(days=30)).isoformat()
        chunks = [
            _make_chunk(
                doc_id="recent_chunk",
                access_count=0,
                last_accessed_at=recent_date,
                updated_at=recent_date,
                activation_level="normal",
            ),
        ]

        mock_store = MagicMock()
        mock_store.update_metadata = MagicMock()

        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=mock_store),
            patch.object(forgetting_engine, "_get_all_chunks", return_value=chunks),
        ):
            result = forgetting_engine.synaptic_downscaling()

        assert result["marked_low"] == 0
        mock_store.update_metadata.assert_not_called()

    def test_synaptic_downscaling_skips_already_low(self, forgetting_engine):
        """Test that chunks already at low activation are skipped."""
        old_date = (now_jst() - timedelta(days=120)).isoformat()
        chunks = [
            _make_chunk(
                doc_id="already_low",
                access_count=0,
                last_accessed_at="",
                updated_at=old_date,
                activation_level="low",
                low_activation_since=old_date,
            ),
        ]

        mock_store = MagicMock()
        mock_store.update_metadata = MagicMock()

        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=mock_store),
            patch.object(forgetting_engine, "_get_all_chunks", return_value=chunks),
        ):
            result = forgetting_engine.synaptic_downscaling()

        assert result["marked_low"] == 0
        mock_store.update_metadata.assert_not_called()

    def test_synaptic_downscaling_scans_knowledge_episodes_procedures(self, forgetting_engine):
        """Test that downscaling scans knowledge, episodes, and procedures."""
        chunks_knowledge = [
            _make_chunk(doc_id="k1", memory_type="knowledge"),
        ]
        chunks_episodes = [
            _make_chunk(doc_id="e1", memory_type="episodes"),
        ]
        chunks_procedures = [
            _make_chunk(doc_id="p1", memory_type="procedures"),
        ]

        call_count = {"n": 0}

        def side_effect_chunks(collection_name):
            call_count["n"] += 1
            if "knowledge" in collection_name:
                return chunks_knowledge
            if "episodes" in collection_name:
                return chunks_episodes
            return chunks_procedures

        mock_store = MagicMock()
        mock_store.update_metadata = MagicMock()

        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=mock_store),
            patch.object(
                forgetting_engine,
                "_get_all_chunks",
                side_effect=side_effect_chunks,
            ),
        ):
            result = forgetting_engine.synaptic_downscaling()

        # Should have been called for all three collections
        assert call_count["n"] == 3
        assert result["scanned"] == 3


# ── Neurogenesis Source Sync Tests ─────────────────────────────────


# ── Forgetting Candidate Tests ───────────────────────────────────


class TestListForgettingCandidates:
    """Test list_forgetting_candidates() (model-driven weekly review)."""

    def test_lists_eligible_low_activation_chunk(self, forgetting_engine):
        """Low-activation chunk past the threshold becomes a candidate."""
        old_low = (now_jst() - timedelta(days=120)).isoformat()
        chunks = [
            _make_chunk(
                doc_id="forget_me",
                access_count=0,
                activation_level="low",
                low_activation_since=old_low,
                source_file="knowledge/forgotten-topic.md",
            ),
        ]
        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=MagicMock()),
            patch.object(forgetting_engine, "_get_all_chunks", return_value=chunks),
        ):
            result = forgetting_engine.list_forgetting_candidates()
        assert len(result) == 1
        assert result[0].path == "knowledge/forgotten-topic.md"
        assert result[0].days_low > 90
        assert result[0].used_count == 0
        assert "低活性" in result[0].reason

    def test_skips_protected(self, forgetting_engine):
        """Protected (important) chunks are excluded from candidates."""
        old_low = (now_jst() - timedelta(days=120)).isoformat()
        chunks = [
            _make_chunk(
                doc_id="protected_chunk",
                access_count=0,
                activation_level="low",
                low_activation_since=old_low,
                importance="important",
                source_file="knowledge/important.md",
            ),
        ]
        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=MagicMock()),
            patch.object(forgetting_engine, "_get_all_chunks", return_value=chunks),
        ):
            result = forgetting_engine.list_forgetting_candidates()
        assert result == []

    def test_skips_frequently_used(self, forgetting_engine):
        """Chunks with used_count above the cap are excluded."""
        old_low = (now_jst() - timedelta(days=120)).isoformat()
        chunks = [
            _make_chunk(
                doc_id="used_chunk",
                access_count=3,  # > FORGETTING_MAX_ACCESS_COUNT
                activation_level="low",
                low_activation_since=old_low,
                source_file="knowledge/used.md",
            ),
        ]
        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=MagicMock()),
            patch.object(forgetting_engine, "_get_all_chunks", return_value=chunks),
        ):
            result = forgetting_engine.list_forgetting_candidates()
        assert result == []

    def test_skips_recent_low_activation(self, forgetting_engine):
        """Chunks below the low-activation duration threshold are excluded."""
        recent_low = (now_jst() - timedelta(days=10)).isoformat()
        chunks = [
            _make_chunk(
                doc_id="recent_chunk",
                access_count=0,
                activation_level="low",
                low_activation_since=recent_low,
                source_file="knowledge/recent.md",
            ),
        ]
        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=MagicMock()),
            patch.object(forgetting_engine, "_get_all_chunks", return_value=chunks),
        ):
            result = forgetting_engine.list_forgetting_candidates()
        assert result == []

    def test_collapses_same_source_file(self, forgetting_engine):
        """Multiple chunks from the same file collapse into one candidate."""
        old_low = (now_jst() - timedelta(days=120)).isoformat()
        chunks = [
            _make_chunk(
                doc_id="a", access_count=0, activation_level="low",
                low_activation_since=old_low, source_file="knowledge/same.md",
            ),
            _make_chunk(
                doc_id="b", access_count=0, activation_level="low",
                low_activation_since=old_low, source_file="knowledge/same.md",
            ),
        ]
        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=MagicMock()),
            patch.object(forgetting_engine, "_get_all_chunks", return_value=chunks),
        ):
            result = forgetting_engine.list_forgetting_candidates()
        assert len(result) == 1
        assert result[0].path == "knowledge/same.md"

    def test_respects_max_items(self, forgetting_engine):
        """Only up to max_items candidates are returned."""
        old_low = (now_jst() - timedelta(days=120)).isoformat()
        chunks = [
            _make_chunk(
                doc_id=f"c{i}", access_count=0, activation_level="low",
                low_activation_since=old_low, source_file=f"knowledge/f{i}.md",
            )
            for i in range(5)
        ]
        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=MagicMock()),
            patch.object(forgetting_engine, "_get_all_chunks", return_value=chunks),
        ):
            result = forgetting_engine.list_forgetting_candidates(max_items=2)
        assert len(result) == 2

    def test_sorts_by_days_low_desc(self, forgetting_engine):
        """Candidates are sorted by low-activation days descending."""
        very_old = (now_jst() - timedelta(days=200)).isoformat()
        old = (now_jst() - timedelta(days=100)).isoformat()
        chunks = [
            _make_chunk(
                doc_id="older", access_count=0, activation_level="low",
                low_activation_since=very_old, source_file="knowledge/older.md",
            ),
            _make_chunk(
                doc_id="younger", access_count=0, activation_level="low",
                low_activation_since=old, source_file="knowledge/younger.md",
            ),
        ]
        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=MagicMock()),
            patch.object(forgetting_engine, "_get_all_chunks", return_value=chunks),
        ):
            result = forgetting_engine.list_forgetting_candidates()
        assert [c.path for c in result] == ["knowledge/older.md", "knowledge/younger.md"]

    def test_rag_unavailable_returns_empty(self, forgetting_engine):
        """Returns an empty list when RAG is unavailable."""
        with patch.object(forgetting_engine, "_get_vector_store", return_value=None):
            assert forgetting_engine.list_forgetting_candidates() == []


# ── F11: usage metrics combine explicit use and automatic recall ───


class TestUsageMetricsCombineAccess:
    """F11: automatic recall (access_count/last_accessed_at) counts as usage."""

    def test_used_count_sums_used_and_access(self, forgetting_engine: ForgettingEngine) -> None:
        assert forgetting_engine._used_count({"used_count": 2, "access_count": 5}) == 7

    def test_used_count_access_only(self, forgetting_engine: ForgettingEngine) -> None:
        """A chunk explicitly used zero times but retrieved often still counts."""
        assert forgetting_engine._used_count({"used_count": 0, "access_count": 4}) == 4

    def test_used_count_legacy_access_only(self, forgetting_engine: ForgettingEngine) -> None:
        """Legacy chunk without used_count → access_count is the usage count."""
        assert forgetting_engine._used_count({"access_count": 3}) == 3

    def test_last_used_at_prefers_latest(self, forgetting_engine: ForgettingEngine) -> None:
        meta = {"last_used_at": "2026-01-01T00:00:00", "last_accessed_at": "2026-06-01T00:00:00"}
        assert forgetting_engine._last_used_at(meta) == "2026-06-01T00:00:00"

    def test_last_used_at_access_only(self, forgetting_engine: ForgettingEngine) -> None:
        assert forgetting_engine._last_used_at({"last_accessed_at": "2026-06-01T00:00:00"}) == "2026-06-01T00:00:00"

    def test_last_used_at_empty_when_missing(self, forgetting_engine: ForgettingEngine) -> None:
        assert forgetting_engine._last_used_at({}) == ""

    def test_downscaling_protects_access_only_chunk(self, forgetting_engine: ForgettingEngine) -> None:
        """An old chunk kept alive purely by recent retrievals is not downscaled."""
        old_date = (now_jst() - timedelta(days=120)).isoformat()
        recent = (now_jst() - timedelta(days=2)).isoformat()
        chunks = [
            _make_chunk(
                doc_id="access_only",
                access_count=5,  # above DOWNSCALING_ACCESS_THRESHOLD
                last_accessed_at=recent,
                updated_at=old_date,
                activation_level="normal",
            ),
        ]

        mock_store = MagicMock()
        with (
            patch.object(forgetting_engine, "_get_vector_store", return_value=mock_store),
            patch.object(forgetting_engine, "_get_all_chunks", return_value=chunks),
        ):
            result = forgetting_engine.synaptic_downscaling()

        assert result["marked_low"] == 0
        mock_store.update_metadata.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
