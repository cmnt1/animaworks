"""Unit tests for post-consolidation Neo4j ingest hook.

Verifies that ConsolidationEngine.ingest_recent_to_backend()
correctly ingests episodes/knowledge to Neo4j when configured,
and is a no-op for legacy backend.  All tests are fully mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.memory.consolidation import ConsolidationEngine

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_engine(tmp_path: Path) -> ConsolidationEngine:
    """Create engine with episodes/ and knowledge/ dirs."""
    anima_dir = tmp_path / "test_anima"
    anima_dir.mkdir()
    (anima_dir / "episodes").mkdir()
    (anima_dir / "knowledge").mkdir()
    return ConsolidationEngine(anima_dir, "test_anima")


def _write_recent_file(path: Path, content: str = "# Test content\nSome text") -> None:
    """Write a file and ensure mtime is recent."""
    path.write_text(content, encoding="utf-8")


def _write_old_file(path: Path, content: str = "# Old content") -> None:
    """Write a file with mtime 7 days ago."""
    import os
    import time

    path.write_text(content, encoding="utf-8")
    old_time = time.time() - 7 * 86400
    os.utime(path, (old_time, old_time))


# ── TestIngestRecentToBackend ──────────────────────────────────────────────


class TestIngestRecentToBackend:
    """Tests for ingest_recent_to_backend()."""

    async def test_neo4j_backend_ingests_recent_episodes(self, tmp_path: Path) -> None:
        engine = _make_engine(tmp_path)
        ep_file = engine.episodes_dir / "2026-04-23.md"
        _write_recent_file(ep_file)

        mock_backend = MagicMock()
        mock_backend.ingest_file = AsyncMock(return_value=3)
        mock_backend.clear_resolver_cache = MagicMock()
        mock_backend.close = AsyncMock()

        with (
            patch("core.config.models.load_config") as mock_cfg,
            patch("core.memory.backend.registry.get_backend", return_value=mock_backend),
        ):
            mock_cfg.return_value = MagicMock(memory=MagicMock(backend="neo4j"))
            stats = await engine.ingest_recent_to_backend(hours=48)

        assert stats["episodes"] == 1
        assert stats["errors"] == 0
        mock_backend.ingest_file.assert_awaited_once_with(ep_file)
        mock_backend.clear_resolver_cache.assert_called_once()

    async def test_neo4j_backend_ingests_recent_knowledge(self, tmp_path: Path) -> None:
        engine = _make_engine(tmp_path)
        kn_file = engine.knowledge_dir / "topic.md"
        _write_recent_file(kn_file)

        mock_backend = MagicMock()
        mock_backend.ingest_file = AsyncMock(return_value=2)
        mock_backend.clear_resolver_cache = MagicMock()
        mock_backend.close = AsyncMock()

        with (
            patch("core.config.models.load_config") as mock_cfg,
            patch("core.memory.backend.registry.get_backend", return_value=mock_backend),
        ):
            mock_cfg.return_value = MagicMock(memory=MagicMock(backend="neo4j"))
            stats = await engine.ingest_recent_to_backend(hours=48)

        assert stats["knowledge"] == 1
        assert stats["errors"] == 0

    async def test_legacy_backend_noop(self, tmp_path: Path) -> None:
        engine = _make_engine(tmp_path)
        _write_recent_file(engine.episodes_dir / "2026-04-23.md")

        with patch("core.config.models.load_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(memory=MagicMock(backend="legacy"))
            stats = await engine.ingest_recent_to_backend()

        assert stats == {"episodes": 0, "knowledge": 0, "errors": 0}

    async def test_no_memory_config_noop(self, tmp_path: Path) -> None:
        engine = _make_engine(tmp_path)

        with patch("core.config.models.load_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(memory=None)
            stats = await engine.ingest_recent_to_backend()

        assert stats == {"episodes": 0, "knowledge": 0, "errors": 0}

    async def test_config_load_failure_noop(self, tmp_path: Path) -> None:
        engine = _make_engine(tmp_path)

        with patch("core.config.models.load_config", side_effect=RuntimeError("no config")):
            stats = await engine.ingest_recent_to_backend()

        assert stats == {"episodes": 0, "knowledge": 0, "errors": 0}

    async def test_skips_old_files(self, tmp_path: Path) -> None:
        engine = _make_engine(tmp_path)
        _write_old_file(engine.episodes_dir / "2026-04-10.md")
        _write_recent_file(engine.episodes_dir / "2026-04-23.md")

        mock_backend = MagicMock()
        mock_backend.ingest_file = AsyncMock(return_value=1)
        mock_backend.clear_resolver_cache = MagicMock()
        mock_backend.close = AsyncMock()

        with (
            patch("core.config.models.load_config") as mock_cfg,
            patch("core.memory.backend.registry.get_backend", return_value=mock_backend),
        ):
            mock_cfg.return_value = MagicMock(memory=MagicMock(backend="neo4j"))
            stats = await engine.ingest_recent_to_backend(hours=48)

        assert stats["episodes"] == 1
        assert mock_backend.ingest_file.await_count == 1

    async def test_ingest_failure_continues(self, tmp_path: Path) -> None:
        engine = _make_engine(tmp_path)
        _write_recent_file(engine.episodes_dir / "a.md")
        _write_recent_file(engine.episodes_dir / "b.md")

        call_count = 0

        async def side_effect(path: Path) -> int:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Neo4j connection lost")
            return 1

        mock_backend = MagicMock()
        mock_backend.ingest_file = AsyncMock(side_effect=side_effect)
        mock_backend.clear_resolver_cache = MagicMock()
        mock_backend.close = AsyncMock()

        with (
            patch("core.config.models.load_config") as mock_cfg,
            patch("core.memory.backend.registry.get_backend", return_value=mock_backend),
        ):
            mock_cfg.return_value = MagicMock(memory=MagicMock(backend="neo4j"))
            stats = await engine.ingest_recent_to_backend(hours=48)

        assert stats["episodes"] == 1
        assert stats["errors"] == 1
        assert mock_backend.ingest_file.await_count == 2

    async def test_skips_archived_knowledge(self, tmp_path: Path) -> None:
        engine = _make_engine(tmp_path)
        archive_dir = engine.knowledge_dir / "archive"
        archive_dir.mkdir()
        _write_recent_file(archive_dir / "old_topic.md")
        _write_recent_file(engine.knowledge_dir / "active_topic.md")

        mock_backend = MagicMock()
        mock_backend.ingest_file = AsyncMock(return_value=1)
        mock_backend.clear_resolver_cache = MagicMock()
        mock_backend.close = AsyncMock()

        with (
            patch("core.config.models.load_config") as mock_cfg,
            patch("core.memory.backend.registry.get_backend", return_value=mock_backend),
        ):
            mock_cfg.return_value = MagicMock(memory=MagicMock(backend="neo4j"))
            stats = await engine.ingest_recent_to_backend(hours=48)

        assert stats["knowledge"] == 1

    async def test_backend_init_failure(self, tmp_path: Path) -> None:
        engine = _make_engine(tmp_path)
        _write_recent_file(engine.episodes_dir / "test.md")

        with (
            patch("core.config.models.load_config") as mock_cfg,
            patch(
                "core.memory.backend.registry.get_backend",
                side_effect=ImportError("neo4j not installed"),
            ),
        ):
            mock_cfg.return_value = MagicMock(memory=MagicMock(backend="neo4j"))
            stats = await engine.ingest_recent_to_backend(hours=48)

        assert stats == {"episodes": 0, "knowledge": 0, "errors": 0}

    async def test_clear_resolver_cache_called(self, tmp_path: Path) -> None:
        engine = _make_engine(tmp_path)
        _write_recent_file(engine.episodes_dir / "test.md")

        mock_backend = MagicMock()
        mock_backend.ingest_file = AsyncMock(return_value=1)
        mock_backend.clear_resolver_cache = MagicMock()
        mock_backend.close = AsyncMock()

        with (
            patch("core.config.models.load_config") as mock_cfg,
            patch("core.memory.backend.registry.get_backend", return_value=mock_backend),
        ):
            mock_cfg.return_value = MagicMock(memory=MagicMock(backend="neo4j"))
            await engine.ingest_recent_to_backend(hours=48)

        mock_backend.clear_resolver_cache.assert_called_once()

    async def test_multiple_files_batch(self, tmp_path: Path) -> None:
        engine = _make_engine(tmp_path)
        _write_recent_file(engine.episodes_dir / "ep1.md")
        _write_recent_file(engine.episodes_dir / "ep2.md")
        _write_recent_file(engine.knowledge_dir / "k1.md")
        _write_recent_file(engine.knowledge_dir / "k2.md")
        _write_recent_file(engine.knowledge_dir / "k3.md")

        mock_backend = MagicMock()
        mock_backend.ingest_file = AsyncMock(return_value=1)
        mock_backend.clear_resolver_cache = MagicMock()
        mock_backend.close = AsyncMock()

        with (
            patch("core.config.models.load_config") as mock_cfg,
            patch("core.memory.backend.registry.get_backend", return_value=mock_backend),
        ):
            mock_cfg.return_value = MagicMock(memory=MagicMock(backend="neo4j"))
            stats = await engine.ingest_recent_to_backend(hours=48)

        assert stats["episodes"] == 2
        assert stats["knowledge"] == 3
        assert mock_backend.ingest_file.await_count == 5
