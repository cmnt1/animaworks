"""Tests for Issue #18 — Realtime conversation ingest to Neo4j.

Covers:
- MemoryConfig.neo4j_realtime_ingest field
- _maybe_neo4j_realtime_ingest routing logic
- Episode deduplication via CHECK_EPISODE_EXISTS
- Fire-and-forget error resilience
"""

from __future__ import annotations

from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

# ── TestMemoryConfigField ────────────────────────────────


class TestMemoryConfigField:
    def test_default_is_false(self) -> None:
        from core.config.schemas import MemoryConfig

        cfg = MemoryConfig()
        assert cfg.neo4j_realtime_ingest is False

    def test_can_enable(self) -> None:
        from core.config.schemas import MemoryConfig

        cfg = MemoryConfig(neo4j_realtime_ingest=True)
        assert cfg.neo4j_realtime_ingest is True

    def test_backend_default_unchanged(self) -> None:
        from core.config.schemas import MemoryConfig

        cfg = MemoryConfig()
        assert cfg.backend == "legacy"


# ── TestCheckEpisodeExistsQuery ──────────────────────────


class TestCheckEpisodeExistsQuery:
    def test_query_exists(self) -> None:
        from core.memory.graph.queries import CHECK_EPISODE_EXISTS

        assert "$uuid" in CHECK_EPISODE_EXISTS
        assert "$group_id" in CHECK_EPISODE_EXISTS
        assert "Episode" in CHECK_EPISODE_EXISTS


# ── TestEpisodeDeduplication ─────────────────────────────


class TestEpisodeDeduplication:
    @pytest.mark.asyncio
    async def test_skips_existing_episode(self, tmp_path) -> None:
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)
        backend = Neo4jGraphBackend(anima_dir, group_id="test")

        mock_driver = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[{"uuid": "existing-ep"}])
        mock_driver.execute_write = AsyncMock()
        backend._driver = mock_driver
        backend._schema_ensured = True

        result = await backend.ingest_text(
            "test text",
            source="chat",
            metadata={"episode_uuid": "existing-ep"},
        )
        assert result == 0
        mock_driver.execute_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_proceeds_for_new_episode(self, tmp_path) -> None:
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)
        backend = Neo4jGraphBackend(anima_dir, group_id="test")

        mock_driver = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[])
        mock_driver.execute_write = AsyncMock()
        backend._driver = mock_driver
        backend._schema_ensured = True

        mock_extractor = MagicMock()
        mock_extractor.extract_entities = AsyncMock(return_value=[])
        mock_extractor.extract_facts = AsyncMock(return_value=[])
        backend._extractor = mock_extractor

        result = await backend.ingest_text("new content", source="chat")
        assert result >= 1
        assert mock_driver.execute_write.call_count >= 1

    @pytest.mark.asyncio
    async def test_auto_generates_uuid_without_metadata(self, tmp_path) -> None:
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)
        backend = Neo4jGraphBackend(anima_dir, group_id="test")

        mock_driver = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[])
        mock_driver.execute_write = AsyncMock()
        backend._driver = mock_driver
        backend._schema_ensured = True

        mock_extractor = MagicMock()
        mock_extractor.extract_entities = AsyncMock(return_value=[])
        mock_extractor.extract_facts = AsyncMock(return_value=[])
        backend._extractor = mock_extractor

        result = await backend.ingest_text("content", source="chat")
        assert result >= 1


# ── TestMaybeNeo4jRealtimeIngest ─────────────────────────


class TestMaybeNeo4jRealtimeIngest:
    def _make_mixin(self):
        from core._anima_messaging import MessagingMixin

        class FakeAnima(MessagingMixin):
            pass

        obj = FakeAnima.__new__(FakeAnima)
        obj.name = "test-anima"
        obj.memory = MagicMock()
        return obj

    def test_skips_when_legacy_backend(self) -> None:
        obj = self._make_mixin()
        obj._neo4j_ingest_turn = AsyncMock()
        with (
            patch("core.memory.backend.registry.resolve_backend_type", return_value="legacy"),
            patch("core.config.models.load_config") as mock_cfg,
        ):
            cfg = MagicMock()
            cfg.memory = MagicMock()
            cfg.memory.backend = "legacy"
            cfg.memory.neo4j_realtime_ingest = True
            mock_cfg.return_value = cfg

            obj._maybe_neo4j_realtime_ingest("user", "hello", "response text", thread_id="thread-a")

        obj._neo4j_ingest_turn.assert_not_awaited()

    def test_skips_when_realtime_disabled(self) -> None:
        obj = self._make_mixin()
        obj._neo4j_ingest_turn = AsyncMock()
        with (
            patch("core.memory.backend.registry.resolve_backend_type", return_value="neo4j"),
            patch("core.config.models.load_config") as mock_cfg,
        ):
            cfg = MagicMock()
            cfg.memory = MagicMock()
            cfg.memory.backend = "neo4j"
            cfg.memory.neo4j_realtime_ingest = False
            mock_cfg.return_value = cfg

            obj._maybe_neo4j_realtime_ingest("user", "hello", "response text", thread_id="thread-a")

        obj._neo4j_ingest_turn.assert_not_awaited()

    def test_skips_when_no_memory_config(self) -> None:
        obj = self._make_mixin()
        obj._neo4j_ingest_turn = AsyncMock()
        with (
            patch("core.memory.backend.registry.resolve_backend_type", return_value="neo4j"),
            patch("core.config.models.load_config") as mock_cfg,
        ):
            cfg = MagicMock(spec=[])
            mock_cfg.return_value = cfg

            obj._maybe_neo4j_realtime_ingest("user", "hello", "response text", thread_id="thread-a")

        obj._neo4j_ingest_turn.assert_not_awaited()

    def test_config_error_doesnt_propagate(self) -> None:
        obj = self._make_mixin()
        with (
            patch("core.memory.backend.registry.resolve_backend_type", return_value="neo4j"),
            patch("core.config.models.load_config", side_effect=RuntimeError("cfg")),
        ):
            obj._maybe_neo4j_realtime_ingest("user", "hello", "response text", thread_id="thread-a")

    def test_skips_empty_response_text(self) -> None:
        obj = self._make_mixin()
        obj._neo4j_ingest_turn = AsyncMock()
        with patch("core.memory.backend.registry.resolve_backend_type") as mock_resolve:
            obj._maybe_neo4j_realtime_ingest("user", "hello", "", thread_id="thread-a")

        mock_resolve.assert_not_called()
        obj._neo4j_ingest_turn.assert_not_awaited()

    def test_ingests_full_turn_with_request_stable_key(self) -> None:
        obj = self._make_mixin()
        obj._neo4j_ingest_turn = AsyncMock()
        with (
            patch("core.memory.backend.registry.resolve_backend_type", return_value="neo4j"),
            patch("core.config.models.load_config") as mock_cfg,
        ):
            cfg = MagicMock()
            cfg.memory = MagicMock()
            cfg.memory.neo4j_realtime_ingest = True
            mock_cfg.return_value = cfg

            obj._maybe_neo4j_realtime_ingest(
                "mio",
                "hello",
                "hi there",
                thread_id="thread-a",
                request_id="req-123",
            )

        obj._neo4j_ingest_turn.assert_awaited_once_with(
            "mio: hello\ntest-anima: hi there",
            source="chat:test-anima:thread-a",
            metadata={
                "stable_key": "chat:test-anima:thread-a:req-123",
                "description": "chat turn thread-a",
                "thread_id": "thread-a",
                "request_id": "req-123",
            },
        )

    def test_hashes_turn_when_request_id_is_absent(self) -> None:
        obj = self._make_mixin()
        obj._neo4j_ingest_turn = AsyncMock()
        with (
            patch("core.memory.backend.registry.resolve_backend_type", return_value="neo4j"),
            patch("core.config.models.load_config") as mock_cfg,
        ):
            cfg = MagicMock()
            cfg.memory = MagicMock()
            cfg.memory.neo4j_realtime_ingest = True
            mock_cfg.return_value = cfg

            obj._maybe_neo4j_realtime_ingest("mio", "hello", "hi there", thread_id="thread-a")

        expected_hash = sha256(b"mio\nthread-a\nhello\nhi there").hexdigest()
        obj._neo4j_ingest_turn.assert_awaited_once_with(
            "mio: hello\ntest-anima: hi there",
            source="chat:test-anima:thread-a",
            metadata={
                "stable_key": f"chat:test-anima:thread-a:{expected_hash}",
                "description": "chat turn thread-a",
                "thread_id": "thread-a",
            },
        )


# ── TestNeo4jIngestTurn ──────────────────────────────────


class TestNeo4jIngestTurn:
    @pytest.mark.asyncio
    async def test_calls_ingest_text(self) -> None:
        from core._anima_messaging import MessagingMixin

        class FakeAnima(MessagingMixin):
            pass

        obj = FakeAnima.__new__(FakeAnima)
        obj.name = "test"

        mock_backend = MagicMock()
        mock_backend.__class__ = type("Neo4jGraphBackend", (), {})
        mock_backend._group_id = "test"
        mock_backend.ingest_text = AsyncMock(return_value=3)
        obj.memory = MagicMock()
        type(obj.memory).memory_backend = PropertyMock(return_value=mock_backend)

        metadata = {"stable_key": "chat:test:thread-a:req-1", "description": "chat turn thread-a"}
        await obj._neo4j_ingest_turn("test text", source="chat:test:thread-a", metadata=metadata)
        mock_backend.ingest_text.assert_awaited_once_with(
            "test text",
            source="chat:test:thread-a",
            metadata=metadata,
        )

    @pytest.mark.asyncio
    async def test_failure_doesnt_propagate(self) -> None:
        from core._anima_messaging import MessagingMixin

        class FakeAnima(MessagingMixin):
            pass

        obj = FakeAnima.__new__(FakeAnima)
        obj.name = "test"

        mock_backend = MagicMock()
        mock_backend.__class__ = type("Neo4jGraphBackend", (), {})
        mock_backend._group_id = "test"
        mock_backend.ingest_text = AsyncMock(side_effect=RuntimeError("boom"))
        obj.memory = MagicMock()
        type(obj.memory).memory_backend = PropertyMock(return_value=mock_backend)

        await obj._neo4j_ingest_turn("test text")

    @pytest.mark.asyncio
    async def test_skips_non_neo4j_backend(self) -> None:
        from core._anima_messaging import MessagingMixin

        class FakeAnima(MessagingMixin):
            pass

        obj = FakeAnima.__new__(FakeAnima)
        obj.name = "test"

        mock_backend = AsyncMock()
        mock_backend.__class__ = type("LegacyRAGBackend", (), {})
        obj.memory = MagicMock()
        type(obj.memory).memory_backend = PropertyMock(return_value=mock_backend)

        await obj._neo4j_ingest_turn("test text")
