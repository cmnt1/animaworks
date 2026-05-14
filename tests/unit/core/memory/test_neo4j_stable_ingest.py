"""Tests for idempotent Neo4j Episode ingest."""

from __future__ import annotations

import hashlib
from unittest.mock import AsyncMock, patch

import pytest


class TestNeo4jStableEpisodeIds:
    """Test deterministic Episode IDs for idempotent ingest."""

    def test_stable_episode_uuid_is_deterministic_and_group_scoped(self, tmp_path):
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        backend_a = Neo4jGraphBackend(tmp_path / "a", group_id="group-a")
        backend_a2 = Neo4jGraphBackend(tmp_path / "a2", group_id="group-a")
        backend_b = Neo4jGraphBackend(tmp_path / "b", group_id="group-b")

        assert backend_a._stable_episode_uuid("file:notes.md:0:abc") == backend_a2._stable_episode_uuid(
            "file:notes.md:0:abc"
        )
        assert backend_a._stable_episode_uuid("file:notes.md:0:abc") != backend_b._stable_episode_uuid(
            "file:notes.md:0:abc"
        )

    @pytest.mark.asyncio
    async def test_ingest_text_prefers_explicit_uuid_over_stable_key(self, tmp_path):
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        backend = Neo4jGraphBackend(tmp_path, group_id="group-a")
        mock_driver = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[{"uuid": "explicit-uuid"}])
        mock_driver.execute_write = AsyncMock()
        backend._driver = mock_driver
        backend._schema_ensured = True

        result = await backend.ingest_text(
            "existing",
            "source",
            metadata={"episode_uuid": "explicit-uuid", "stable_key": "stable-key"},
        )

        assert result == 0
        assert mock_driver.execute_query.call_args.args[1]["uuid"] == "explicit-uuid"
        mock_driver.execute_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingest_text_uses_stable_key_when_uuid_absent(self, tmp_path):
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        backend = Neo4jGraphBackend(tmp_path, group_id="group-a")
        expected_uuid = backend._stable_episode_uuid("stable-key")
        mock_driver = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[{"uuid": expected_uuid}])
        mock_driver.execute_write = AsyncMock()
        backend._driver = mock_driver
        backend._schema_ensured = True

        result = await backend.ingest_text("existing", "source", metadata={"stable_key": "stable-key"})

        assert result == 0
        assert mock_driver.execute_query.call_args.args[1]["uuid"] == expected_uuid
        mock_driver.execute_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingest_text_falls_back_to_random_uuid(self, tmp_path):
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        backend = Neo4jGraphBackend(tmp_path, group_id="group-a")
        mock_driver = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[{"uuid": "generated-uuid"}])
        mock_driver.execute_write = AsyncMock()
        backend._driver = mock_driver
        backend._schema_ensured = True

        with patch("core.memory.backend.neo4j_graph.uuid4", return_value="generated-uuid"):
            result = await backend.ingest_text("existing", "source")

        assert result == 0
        assert mock_driver.execute_query.call_args.args[1]["uuid"] == "generated-uuid"
        mock_driver.execute_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_ingest_file_uses_normalized_path_source_and_section_metadata(self, tmp_path):
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "sakura"
        target = anima_dir / "knowledge" / "notes.md"
        target.parent.mkdir(parents=True)
        target.write_text("hello neo4j", encoding="utf-8")

        backend = Neo4jGraphBackend(anima_dir, group_id="sakura")
        backend.ingest_text = AsyncMock(return_value=1)  # type: ignore[method-assign]

        result = await backend.ingest_file(target)

        assert result == 1
        backend.ingest_text.assert_awaited_once()
        _, kwargs = backend.ingest_text.call_args
        metadata = kwargs["metadata"]
        expected_hash = hashlib.sha256(b"hello neo4j").hexdigest()
        assert kwargs["source"] == "file:knowledge/notes.md"
        assert metadata == {
            "stable_key": f"file:knowledge/notes.md:0:{expected_hash}",
            "source_path": "knowledge/notes.md",
            "source_hash": expected_hash,
            "section_index": 0,
        }

    @pytest.mark.asyncio
    async def test_ingest_file_skips_duplicate_same_content_on_second_pass(self, tmp_path):
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "sakura"
        target = anima_dir / "knowledge" / "notes.md"
        target.parent.mkdir(parents=True)
        target.write_text("same content", encoding="utf-8")

        backend = Neo4jGraphBackend(anima_dir, group_id="sakura")
        backend._embedding_available = False
        mock_driver = AsyncMock()
        mock_driver.execute_query = AsyncMock(side_effect=[[], [{"uuid": "existing"}]])
        mock_driver.execute_write = AsyncMock()
        backend._driver = mock_driver
        backend._schema_ensured = True
        mock_extractor = AsyncMock()
        mock_extractor.extract_entities = AsyncMock(return_value=[])
        mock_extractor.extract_facts = AsyncMock(return_value=[])
        backend._extractor = mock_extractor

        first = await backend.ingest_file(target)
        second = await backend.ingest_file(target)

        assert first == 1
        assert second == 0
        assert mock_driver.execute_write.call_count == 1

    @pytest.mark.asyncio
    async def test_ingest_file_changed_content_creates_new_episode(self, tmp_path):
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend
        from core.memory.graph.queries import CREATE_EPISODE

        anima_dir = tmp_path / "animas" / "sakura"
        target = anima_dir / "knowledge" / "notes.md"
        target.parent.mkdir(parents=True)
        target.write_text("version one", encoding="utf-8")

        backend = Neo4jGraphBackend(anima_dir, group_id="sakura")
        backend._embedding_available = False
        mock_driver = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[])
        mock_driver.execute_write = AsyncMock()
        backend._driver = mock_driver
        backend._schema_ensured = True
        mock_extractor = AsyncMock()
        mock_extractor.extract_entities = AsyncMock(return_value=[])
        mock_extractor.extract_facts = AsyncMock(return_value=[])
        backend._extractor = mock_extractor

        first = await backend.ingest_file(target)
        target.write_text("version two", encoding="utf-8")
        second = await backend.ingest_file(target)

        episode_calls = [call for call in mock_driver.execute_write.call_args_list if call.args[0] == CREATE_EPISODE]
        assert first == 1
        assert second == 1
        assert len(episode_calls) == 2
        assert episode_calls[0].args[1]["uuid"] != episode_calls[1].args[1]["uuid"]
