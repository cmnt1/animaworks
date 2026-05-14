"""Unit tests for Neo4j schema management."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


class TestSchemaConstants:
    """Verify schema definitions are properly structured."""

    def test_constraints_are_list(self):
        from core.memory.graph.schema import CONSTRAINTS

        assert isinstance(CONSTRAINTS, list)
        assert len(CONSTRAINTS) >= 3  # Entity, Episode, Community

    def test_constraints_are_idempotent(self):
        from core.memory.graph.schema import CONSTRAINTS, SCHEMA_META_CONSTRAINTS

        for c in [*CONSTRAINTS, *SCHEMA_META_CONSTRAINTS]:
            assert "IF NOT EXISTS" in c

    def test_schema_version_is_v5(self):
        from core.memory.graph.schema import SCHEMA_VERSION

        assert SCHEMA_VERSION == 5

    def test_schema_meta_constraint_is_keyed(self):
        from core.memory.graph.schema import SCHEMA_META_CONSTRAINTS

        assert any("_SchemaMeta" in c and "m.name IS UNIQUE" in c for c in SCHEMA_META_CONSTRAINTS)

    def test_indexes_are_idempotent(self):
        from core.memory.graph.schema import INDEXES

        for i in INDEXES:
            assert "IF NOT EXISTS" in i

    def test_advanced_indexes_are_idempotent(self):
        from core.memory.graph.schema import ADVANCED_INDEXES

        for i in ADVANCED_INDEXES:
            assert "IF NOT EXISTS" in i

    def test_advanced_indexes_include_community_fulltext(self):
        from core.memory.graph.schema import ADVANCED_INDEXES

        joined = "\n".join(ADVANCED_INDEXES)
        assert "community_fulltext" in joined
        assert "Community" in joined
        assert "n.name" in joined
        assert "n.summary" in joined

    def test_vector_indexes_have_name_and_query(self):
        from core.memory.graph.schema import VECTOR_INDEXES

        for vi in VECTOR_INDEXES:
            assert "name" in vi
            assert "query" in vi


class TestEnsureSchema:
    """Test ensure_schema with mocked driver."""

    @pytest.mark.asyncio
    async def test_executes_all_statements(self):
        from core.memory.graph.schema import (
            ADVANCED_INDEXES,
            CONSTRAINTS,
            INDEXES,
            MIGRATIONS,
            SCHEMA_META_CONSTRAINTS,
            VECTOR_INDEXES,
            ensure_schema,
        )

        mock_driver = AsyncMock()
        mock_driver.execute_write = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[])

        result = await ensure_schema(mock_driver)

        assert "constraints" in result
        assert "indexes" in result
        assert "advanced" in result
        assert "vector" in result
        migration_writes = sum(len(m["queries"]) + 1 for m in MIGRATIONS)
        expected_calls = (
            len(CONSTRAINTS)
            + len(INDEXES)
            + len(ADVANCED_INDEXES)
            + len(VECTOR_INDEXES)
            + 1  # schema meta canonicalization
            + len(SCHEMA_META_CONSTRAINTS)
            + migration_writes
        )
        assert mock_driver.execute_write.call_count == expected_calls

    @pytest.mark.asyncio
    async def test_counts_successes(self):
        from core.memory.graph.schema import (
            ADVANCED_INDEXES,
            CONSTRAINTS,
            INDEXES,
            SCHEMA_META_CONSTRAINTS,
            VECTOR_INDEXES,
            ensure_schema,
        )

        mock_driver = AsyncMock()
        mock_driver.execute_write = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[])

        result = await ensure_schema(mock_driver)

        assert result["constraints"] == len(CONSTRAINTS) + len(SCHEMA_META_CONSTRAINTS)
        assert result["indexes"] == len(INDEXES)
        assert result["advanced"] == len(ADVANCED_INDEXES)
        assert result["vector"] == len(VECTOR_INDEXES)
        assert result["errors"] == 0

    @pytest.mark.asyncio
    async def test_continues_on_error(self):
        """Schema creation should not abort on individual statement failures."""
        from core.memory.graph.schema import (
            ADVANCED_INDEXES,
            CONSTRAINTS,
            INDEXES,
            MIGRATIONS,
            SCHEMA_META_CONSTRAINTS,
            VECTOR_INDEXES,
            ensure_schema,
        )

        migration_writes = sum(len(m["queries"]) + 1 for m in MIGRATIONS)
        total = (
            len(CONSTRAINTS)
            + len(INDEXES)
            + len(ADVANCED_INDEXES)
            + len(VECTOR_INDEXES)
            + 1
            + len(SCHEMA_META_CONSTRAINTS)
            + migration_writes
        )
        effects = [None] + [Exception("fail")] + [None] * (total - 2)

        mock_driver = AsyncMock()
        mock_driver.execute_write = AsyncMock(side_effect=effects)
        mock_driver.execute_query = AsyncMock(return_value=[])

        result = await ensure_schema(mock_driver)
        assert result["errors"] == 1
        assert mock_driver.execute_write.call_count == total

    @pytest.mark.asyncio
    async def test_idempotent_double_call(self):
        """Calling ensure_schema twice should not fail."""
        from core.memory.graph.schema import ensure_schema

        mock_driver = AsyncMock()
        mock_driver.execute_write = AsyncMock()
        mock_driver.execute_query = AsyncMock(side_effect=[[], [{"version": 4}]])

        r1 = await ensure_schema(mock_driver)
        r2 = await ensure_schema(mock_driver)
        assert isinstance(r1, dict)
        assert isinstance(r2, dict)

    @pytest.mark.asyncio
    async def test_canonicalizes_schema_meta_before_meta_constraint(self):
        from core.memory.graph.schema import (
            SCHEMA_META_CANONICALIZATION,
            SCHEMA_META_CONSTRAINTS,
            ensure_schema,
        )

        mock_driver = AsyncMock()
        mock_driver.execute_write = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[{"version": 5}])

        await ensure_schema(mock_driver)

        write_statements = [call.args[0] for call in mock_driver.execute_write.call_args_list]
        canonicalization_index = write_statements.index(SCHEMA_META_CANONICALIZATION)
        meta_constraint_index = write_statements.index(SCHEMA_META_CONSTRAINTS[0])
        assert canonicalization_index < meta_constraint_index

    def test_v5_migration_registers_optional_properties_and_backfills_group_id(self):
        from core.memory.graph.schema import MIGRATIONS

        migration = next(m for m in MIGRATIONS if m["version"] == 5)
        joined = "\n".join(migration["queries"])

        assert "_PropertyKeyRegistry" in joined
        assert "deleted_at = true" in joined
        assert "invalid_at = true" in joined
        assert "expired_at = true" in joined
        assert "MENTIONS" in joined
        assert "HAS_MEMBER" in joined
        assert "SET r.group_id" in joined
