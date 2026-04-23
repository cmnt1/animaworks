"""Tests for Issue #19 — Neo4j delete implementation.

Covers:
- Soft-delete for episodes, entities, facts
- Prefix parsing (episode:, entity:, fact:)
- Search query deleted_at filters
- PURGE_DELETED query
- Error resilience
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


# ── TestDeleteMethod ─────────────────────────────────────


class TestDeleteMethod:
    @pytest.fixture
    def backend(self, tmp_path):
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)
        b = Neo4jGraphBackend(anima_dir, group_id="test")
        mock_driver = AsyncMock()
        mock_driver.execute_write = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[])
        b._driver = mock_driver
        b._schema_ensured = True
        return b, mock_driver

    @pytest.mark.asyncio
    async def test_delete_episode(self, backend) -> None:
        b, driver = backend
        await b.delete("episode:ep-123")
        driver.execute_write.assert_called_once()
        args = driver.execute_write.call_args[0]
        assert args[1]["uuid"] == "ep-123"
        assert args[1]["group_id"] == "test"
        assert "deleted_at" in args[1]

    @pytest.mark.asyncio
    async def test_delete_entity(self, backend) -> None:
        b, driver = backend
        await b.delete("entity:ent-456")
        driver.execute_write.assert_called_once()
        args = driver.execute_write.call_args[0]
        assert args[1]["uuid"] == "ent-456"

    @pytest.mark.asyncio
    async def test_delete_fact(self, backend) -> None:
        b, driver = backend
        await b.delete("fact:fact-789")
        driver.execute_write.assert_called_once()
        args = driver.execute_write.call_args[0]
        assert args[1]["uuid"] == "fact-789"

    @pytest.mark.asyncio
    async def test_unprefixed_defaults_to_episode(self, backend) -> None:
        b, driver = backend
        await b.delete("some-uuid-no-prefix")
        driver.execute_write.assert_called_once()
        args = driver.execute_write.call_args[0]
        assert args[1]["uuid"] == "some-uuid-no-prefix"
        assert "Episode" in args[0] or "episode" in args[0].lower()

    @pytest.mark.asyncio
    async def test_unknown_prefix_skips(self, backend) -> None:
        b, driver = backend
        await b.delete("unknown:xyz")
        driver.execute_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_failure_doesnt_raise(self, backend) -> None:
        b, driver = backend
        driver.execute_write = AsyncMock(side_effect=RuntimeError("Neo4j down"))
        await b.delete("episode:ep-err")


# ── TestSoftDeleteQueries ────────────────────────────────


class TestSoftDeleteQueries:
    def test_soft_delete_episode_exists(self) -> None:
        from core.memory.graph.queries import SOFT_DELETE_EPISODE

        assert "$uuid" in SOFT_DELETE_EPISODE
        assert "$group_id" in SOFT_DELETE_EPISODE
        assert "$deleted_at" in SOFT_DELETE_EPISODE
        assert "MENTIONS" in SOFT_DELETE_EPISODE

    def test_soft_delete_entity_invalidates_facts(self) -> None:
        from core.memory.graph.queries import SOFT_DELETE_ENTITY

        assert "$uuid" in SOFT_DELETE_ENTITY
        assert "invalid_at" in SOFT_DELETE_ENTITY
        assert "deleted_at" in SOFT_DELETE_ENTITY

    def test_soft_delete_fact_exists(self) -> None:
        from core.memory.graph.queries import SOFT_DELETE_FACT

        assert "$uuid" in SOFT_DELETE_FACT
        assert "deleted_at" in SOFT_DELETE_FACT

    def test_purge_deleted_exists(self) -> None:
        from core.memory.graph.queries import PURGE_DELETED

        assert "$group_id" in PURGE_DELETED
        assert "DETACH DELETE" in PURGE_DELETED
        assert "deleted_at IS NOT NULL" in PURGE_DELETED


# ── TestSearchDeletedAtFilters ───────────────────────────


class TestSearchDeletedAtFilters:
    def test_vector_search_facts_filters_deleted(self) -> None:
        from core.memory.graph.queries import VECTOR_SEARCH_FACTS

        assert "deleted_at IS NULL" in VECTOR_SEARCH_FACTS

    def test_fulltext_search_facts_filters_deleted(self) -> None:
        from core.memory.graph.queries import FULLTEXT_SEARCH_FACTS

        assert "deleted_at IS NULL" in FULLTEXT_SEARCH_FACTS

    def test_vector_search_entities_filters_deleted(self) -> None:
        from core.memory.graph.queries import VECTOR_SEARCH_ENTITIES

        assert "deleted_at IS NULL" in VECTOR_SEARCH_ENTITIES

    def test_fulltext_search_entities_filters_deleted(self) -> None:
        from core.memory.graph.queries import FULLTEXT_SEARCH_ENTITIES

        assert "deleted_at IS NULL" in FULLTEXT_SEARCH_ENTITIES

    def test_bfs_filters_deleted(self) -> None:
        from core.memory.graph.queries import BFS_FACTS_FROM_ENTITY

        assert "deleted_at IS NULL" in BFS_FACTS_FROM_ENTITY

    def test_community_entities_filters_deleted(self) -> None:
        from core.memory.graph.queries import FETCH_ENTITIES_FOR_COMMUNITY

        assert "deleted_at IS NULL" in FETCH_ENTITIES_FOR_COMMUNITY


# ── TestResetUnchanged ───────────────────────────────────


class TestResetUnchanged:
    @pytest.mark.asyncio
    async def test_reset_still_works(self, tmp_path) -> None:
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)
        b = Neo4jGraphBackend(anima_dir, group_id="test")
        mock_driver = AsyncMock()
        mock_driver.execute_write = AsyncMock()
        b._driver = mock_driver
        b._schema_ensured = True

        await b.reset()
        mock_driver.execute_write.assert_called_once()
        args = mock_driver.execute_write.call_args[0]
        assert "DETACH DELETE" in args[0]
