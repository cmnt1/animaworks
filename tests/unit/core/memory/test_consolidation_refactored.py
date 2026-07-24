from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.memory.consolidation import ConsolidationEngine
from core.time_utils import now_jst


@pytest.fixture
def anima_dir(tmp_path):
    """Create minimal anima directory."""
    for d in ["episodes", "knowledge", "procedures", "archive"]:
        (tmp_path / d).mkdir()
    return tmp_path


@pytest.fixture
def engine(anima_dir):
    return ConsolidationEngine(anima_dir=anima_dir, anima_name="test-anima")


class TestCollectRecentEpisodes:
    def test_no_episodes(self, engine):
        """Return empty list when no episode files exist."""
        episodes = engine._collect_recent_episodes(hours=24)
        assert episodes == []

    def test_collects_today_episodes(self, engine, anima_dir):
        """Collect episodes from today's file."""
        today = now_jst().strftime("%Y-%m-%d")
        ep_file = anima_dir / "episodes" / f"{today}.md"
        ep_file.write_text("## 10:00 \u2014 Did some work\n\nDetails here\n\n## 14:00 \u2014 Meeting notes\n\nMore details\n", encoding="utf-8")

        episodes = engine._collect_recent_episodes(hours=24)
        assert len(episodes) > 0


class TestListKnowledgeFiles:
    def test_empty_knowledge(self, engine):
        """Return empty list when no knowledge files."""
        files = engine._list_knowledge_files()
        assert files == []

    def test_lists_knowledge_files(self, engine, anima_dir):
        """List markdown files in knowledge directory."""
        (anima_dir / "knowledge" / "topic-a.md").write_text("content a")
        (anima_dir / "knowledge" / "topic-b.md").write_text("content b")
        (anima_dir / "knowledge" / "not-md.txt").write_text("ignored")

        files = engine._list_knowledge_files()
        assert len(files) == 2


class TestRebuildRagIndex:
    def test_rebuild_no_error(self, engine):
        """_rebuild_rag_index should not raise even when RAG is unavailable."""
        # Mock the RAG layer so the test never loads the real embedding model
        # (which would exceed the 30s pytest-timeout on a cold CI cache).
        mock_vs = MagicMock()
        try:
            with (
                patch("core.memory.rag.singleton.get_vector_store", return_value=mock_vs),
                patch("core.memory.rag.MemoryIndexer"),
            ):
                engine._rebuild_rag_index()
        except ImportError:
            pass  # OK if RAG deps not installed


class TestRemovedMethods:
    """Verify that removed methods are actually gone."""

    def test_daily_consolidate_removed(self, engine):
        assert not hasattr(engine, "daily_consolidate")

    def test_weekly_integrate_removed(self, engine):
        assert not hasattr(engine, "weekly_integrate")

    def test_summarize_episodes_removed(self, engine):
        assert not hasattr(engine, "_summarize_episodes")

    def test_merge_to_knowledge_removed(self, engine):
        assert not hasattr(engine, "_merge_to_knowledge")

    def test_validate_consolidation_removed(self, engine):
        assert not hasattr(engine, "_validate_consolidation")

    def test_compress_old_episodes_removed(self, engine):
        assert not hasattr(engine, "_compress_old_episodes")

    def test_merge_knowledge_files_removed(self, engine):
        assert not hasattr(engine, "_merge_knowledge_files")
