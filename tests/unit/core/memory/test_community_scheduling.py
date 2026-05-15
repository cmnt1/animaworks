"""Tests for Issue #17 — Community Detection scheduling.

Covers:
- Batch community detection in system consolidation
- Dynamic community update in ingest_text
- Backend check (legacy vs neo4j)
- Error resilience
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── TestDynamicCommunityUpdateInIngest ────────────────────


class TestDynamicCommunityUpdateInIngest:
    """Test that ingest_text calls dynamic_update for new entities."""

    @pytest.fixture
    def _setup_backend(self, tmp_path):
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)
        backend = Neo4jGraphBackend(anima_dir, group_id="test")

        mock_driver = AsyncMock()
        mock_driver.execute_write = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[])
        backend._driver = mock_driver
        backend._schema_ensured = True

        mock_entity = MagicMock()
        mock_entity.name = "Alice"
        mock_entity.entity_type = "Person"
        mock_entity.summary = "A person"

        mock_extractor = MagicMock()
        mock_extractor.extract_entities = AsyncMock(return_value=[mock_entity])
        mock_extractor.extract_facts = AsyncMock(return_value=[])

        mock_resolved = MagicMock()
        mock_resolved.uuid = "ent-alice"
        mock_resolved.name = "Alice"
        mock_resolved.summary = "A person"
        mock_resolved.is_new = True

        mock_resolver = MagicMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_resolved)

        backend._extractor = mock_extractor
        backend._resolver = mock_resolver

        return backend, mock_driver

    @pytest.mark.asyncio
    async def test_ingest_calls_dynamic_update(self, _setup_backend) -> None:
        backend, mock_driver = _setup_backend

        with patch.object(backend, "_dynamic_community_update", new_callable=AsyncMock) as mock_update:
            await backend.ingest_text("Alice is a person", source="test")
            mock_update.assert_called_once()
            args = mock_update.call_args[0]
            assert args[0] is mock_driver
            assert "ent-alice" in args[1]

    @pytest.mark.asyncio
    async def test_ingest_skips_update_when_no_new_entities(self, tmp_path) -> None:
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)
        backend = Neo4jGraphBackend(anima_dir, group_id="test")

        mock_driver = AsyncMock()
        mock_driver.execute_write = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[])
        backend._driver = mock_driver
        backend._schema_ensured = True

        mock_entity = MagicMock()
        mock_entity.name = "Alice"
        mock_entity.entity_type = "Person"
        mock_entity.summary = "A person"

        mock_extractor = MagicMock()
        mock_extractor.extract_entities = AsyncMock(return_value=[mock_entity])
        mock_extractor.extract_facts = AsyncMock(return_value=[])

        mock_resolved = MagicMock()
        mock_resolved.uuid = "ent-alice"
        mock_resolved.name = "Alice"
        mock_resolved.summary = "A person"
        mock_resolved.is_new = False

        mock_resolver = MagicMock()
        mock_resolver.resolve = AsyncMock(return_value=mock_resolved)

        backend._extractor = mock_extractor
        backend._resolver = mock_resolver

        with patch.object(backend, "_dynamic_community_update", new_callable=AsyncMock) as mock_update:
            await backend.ingest_text("Alice is a person", source="test")
            mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_dynamic_update_failure_doesnt_break_ingest(self, _setup_backend) -> None:
        backend, _ = _setup_backend

        with patch.object(
            backend,
            "_dynamic_community_update",
            new_callable=AsyncMock,
            side_effect=RuntimeError("community error"),
        ):
            result = await backend.ingest_text("Alice is here", source="test")
            assert result >= 1


# ── TestDynamicCommunityUpdateMethod ─────────────────────


class TestDynamicCommunityUpdateMethod:
    """Test _dynamic_community_update method directly."""

    @pytest.mark.asyncio
    async def test_finds_neighbors_and_calls_detector(self, tmp_path) -> None:
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)
        backend = Neo4jGraphBackend(anima_dir, group_id="test")

        mock_driver = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[{"uuid": "neighbor-1"}])
        mock_driver.execute_write = AsyncMock()

        with patch("core.memory.graph.community.CommunityDetector") as MockDetector:
            mock_detector = MagicMock()
            mock_detector.dynamic_update = AsyncMock(return_value="comm-1")
            MockDetector.return_value = mock_detector

            await backend._dynamic_community_update(mock_driver, ["ent-new"])

            mock_detector.dynamic_update.assert_called_once_with("ent-new", ["neighbor-1"])

    @pytest.mark.asyncio
    async def test_no_neighbors_skips_update(self, tmp_path) -> None:
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)
        backend = Neo4jGraphBackend(anima_dir, group_id="test")

        mock_driver = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[])

        with patch("core.memory.graph.community.CommunityDetector") as MockDetector:
            mock_detector = MagicMock()
            mock_detector.dynamic_update = AsyncMock()
            MockDetector.return_value = mock_detector

            await backend._dynamic_community_update(mock_driver, ["ent-new"])

            mock_detector.dynamic_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_dynamic_update_does_not_run_full_detection_when_no_assignment(self, tmp_path) -> None:
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)
        backend = Neo4jGraphBackend(anima_dir, group_id="test")

        mock_driver = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[{"uuid": "neighbor-1"}])

        with patch("core.memory.graph.community.CommunityDetector") as MockDetector:
            mock_detector = MagicMock()
            mock_detector.dynamic_update = AsyncMock(return_value=None)
            mock_detector.detect_and_store = AsyncMock()
            MockDetector.return_value = mock_detector

            await backend._dynamic_community_update(mock_driver, ["ent-new"])

            mock_detector.dynamic_update.assert_called_once_with("ent-new", ["neighbor-1"])
            mock_detector.detect_and_store.assert_not_called()


# ── TestFindEntityNeighborsQuery ─────────────────────────


class TestFindEntityNeighborsQuery:
    def test_query_exists(self) -> None:
        from core.memory.graph.queries import FIND_ENTITY_NEIGHBORS

        assert "$entity_uuid" in FIND_ENTITY_NEIGHBORS
        assert "$group_id" in FIND_ENTITY_NEIGHBORS
        assert "RELATES_TO" in FIND_ENTITY_NEIGHBORS


# ── TestDetectCommunitiesIfNeo4j ─────────────────────────


class TestDetectCommunitiesIfNeo4j:
    """Test _detect_communities_if_neo4j in SystemConsolidationMixin."""

    @pytest.mark.asyncio
    async def test_skips_when_legacy_backend(self, tmp_path) -> None:
        from core.lifecycle.system_consolidation import SystemConsolidationMixin

        mock_anima = MagicMock()
        mock_anima.memory.anima_dir = tmp_path

        with (
            patch("core.memory.backend.registry.resolve_backend_type", return_value="legacy"),
            patch("core.memory.backend.registry.get_backend") as mock_get_backend,
        ):
            await SystemConsolidationMixin._detect_communities_if_neo4j(mock_anima)

        mock_get_backend.assert_not_called()

    @pytest.mark.asyncio
    async def test_global_legacy_per_anima_neo4j_runs(self, tmp_path) -> None:
        from core.lifecycle.system_consolidation import SystemConsolidationMixin

        (tmp_path / "status.json").write_text('{"memory_backend": "neo4j"}', encoding="utf-8")
        mock_anima = MagicMock()
        mock_anima.name = "test"
        mock_anima.memory.anima_dir = tmp_path

        mock_backend = MagicMock()
        mock_backend._group_id = "test"
        mock_backend._resolve_background_model.return_value = "test-model"
        mock_backend._resolve_locale.return_value = "ja"
        mock_backend._ensure_driver = AsyncMock()
        mock_backend.close = AsyncMock()

        with (
            patch("core.memory.backend.registry.get_backend", return_value=mock_backend) as mock_get_backend,
            patch("core.memory.graph.community.CommunityDetector") as MockDetector,
        ):
            mock_detector = MagicMock()
            mock_detector.detect_and_store = AsyncMock(return_value=[])
            mock_detector.get_community_stats = AsyncMock(return_value={"communities": 0, "memberships": 0})
            MockDetector.return_value = mock_detector

            await SystemConsolidationMixin._detect_communities_if_neo4j(mock_anima)

        mock_get_backend.assert_called_once_with("neo4j", tmp_path)
        mock_detector.detect_and_store.assert_awaited_once()
        mock_detector.get_community_stats.assert_awaited_once()
        mock_backend.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_global_neo4j_per_anima_legacy_skips(self, tmp_path) -> None:
        from core.lifecycle.system_consolidation import SystemConsolidationMixin

        (tmp_path / "status.json").write_text('{"memory_backend": "legacy"}', encoding="utf-8")
        mock_anima = MagicMock()
        mock_anima.memory.anima_dir = tmp_path

        with patch("core.memory.backend.registry.get_backend") as mock_get_backend:
            await SystemConsolidationMixin._detect_communities_if_neo4j(mock_anima)

        mock_get_backend.assert_not_called()

    @pytest.mark.asyncio
    async def test_runs_when_neo4j_backend(self, tmp_path) -> None:
        from core.lifecycle.system_consolidation import SystemConsolidationMixin

        mock_anima = MagicMock()
        mock_anima.name = "test"
        mock_anima.memory.anima_dir = tmp_path

        mock_backend = MagicMock()
        mock_backend._group_id = "test"
        mock_backend._resolve_background_model.return_value = "test-model"
        mock_backend._resolve_locale.return_value = "ja"
        mock_backend._ensure_driver = AsyncMock()
        mock_backend.close = AsyncMock()

        with (
            patch("core.memory.backend.registry.resolve_backend_type", return_value="neo4j"),
            patch("core.memory.backend.registry.get_backend", return_value=mock_backend),
            patch("core.memory.graph.community.CommunityDetector") as MockDetector,
        ):
            mock_detector = MagicMock()
            mock_detector.detect_and_store = AsyncMock(return_value=[object(), object()])
            mock_detector.get_community_stats = AsyncMock(return_value={"communities": 2, "memberships": 5})
            MockDetector.return_value = mock_detector

            await SystemConsolidationMixin._detect_communities_if_neo4j(mock_anima)

            mock_detector.detect_and_store.assert_called_once()
            mock_detector.get_community_stats.assert_awaited_once()
            mock_backend.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_doesnt_propagate(self) -> None:
        from core.lifecycle.system_consolidation import SystemConsolidationMixin

        mock_anima = MagicMock()
        mock_anima.name = "test"

        with patch("core.memory.backend.registry.resolve_backend_type", side_effect=RuntimeError("cfg error")):
            await SystemConsolidationMixin._detect_communities_if_neo4j(mock_anima)


# ── TestCliDetectCommunities ─────────────────────────────


class TestCliDetectCommunities:
    """Test CLI community detection runtime output."""

    def test_cmd_detect_communities_single_anima_runs(self, tmp_path) -> None:
        from cli.commands.anima_communities import cmd_anima_detect_communities

        args = MagicMock()
        args.detect_all = False
        args.anima = "sakura"

        with (
            patch("core.paths.get_animas_dir", return_value=tmp_path),
            patch("cli.commands.anima_communities.asyncio.run") as mock_run,
        ):
            cmd_anima_detect_communities(args)

        coroutine = mock_run.call_args.args[0]
        coroutine.close()
        mock_run.assert_called_once()

    def test_cmd_detect_communities_requires_target(self, tmp_path, capsys) -> None:
        from cli.commands.anima_communities import cmd_anima_detect_communities

        args = MagicMock()
        args.detect_all = False
        args.anima = None

        with (
            patch("core.paths.get_animas_dir", return_value=tmp_path),
            pytest.raises(SystemExit),
        ):
            cmd_anima_detect_communities(args)

        assert "specify anima name or --all" in capsys.readouterr().out

    @pytest.mark.asyncio
    async def test_cli_skips_missing_and_non_neo4j_animas(self, tmp_path, capsys) -> None:
        from cli.commands.anima_communities import _run_detect_communities

        legacy_dir = tmp_path / "legacy"
        legacy_dir.mkdir()

        with (
            patch("core.memory.backend.registry.resolve_backend_type", return_value="legacy"),
            patch("core.memory.backend.registry.get_backend") as mock_get_backend,
        ):
            await _run_detect_communities(["missing", "legacy"], tmp_path)

        output = capsys.readouterr().out
        assert "missing: not found" in output
        assert "legacy: not using Neo4j" in output
        mock_get_backend.assert_not_called()

    @pytest.mark.asyncio
    async def test_cli_prints_stored_community_stats(self, tmp_path, capsys) -> None:
        from cli.commands.anima_communities import _run_detect_communities

        anima_dir = tmp_path / "sakura"
        anima_dir.mkdir()

        mock_backend = MagicMock()
        mock_backend._group_id = "sakura"
        mock_backend._resolve_background_model.return_value = "test-model"
        mock_backend._resolve_locale.return_value = "ja"
        mock_backend._ensure_driver = AsyncMock()
        mock_backend.close = AsyncMock()

        with (
            patch("core.memory.backend.registry.resolve_backend_type", return_value="neo4j"),
            patch("core.memory.backend.registry.get_backend", return_value=mock_backend),
            patch("core.memory.graph.community.CommunityDetector") as MockDetector,
        ):
            mock_detector = MagicMock()
            mock_detector.detect_and_store = AsyncMock(return_value=[object(), object()])
            mock_detector.get_community_stats = AsyncMock(return_value={"communities": 2, "memberships": 6})
            MockDetector.return_value = mock_detector

            await _run_detect_communities(["sakura"], tmp_path)

        output = capsys.readouterr().out
        assert "sakura: 2 communities detected" in output
        assert "stored=2" in output
        assert "memberships=6" in output
        mock_backend.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cli_prints_error_when_detection_fails(self, tmp_path, capsys) -> None:
        from cli.commands.anima_communities import _run_detect_communities

        anima_dir = tmp_path / "sakura"
        anima_dir.mkdir()

        with (
            patch("core.memory.backend.registry.resolve_backend_type", return_value="neo4j"),
            patch("core.memory.backend.registry.get_backend", side_effect=RuntimeError("db unavailable")),
        ):
            await _run_detect_communities(["sakura"], tmp_path)

        assert "sakura: ERROR - db unavailable" in capsys.readouterr().out
