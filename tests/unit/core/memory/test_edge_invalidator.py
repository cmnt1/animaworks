from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for fact invalidation removal.

The mechanical ``EdgeInvalidator`` was removed as part of the harness diet
(PR-6): contradiction detection is now deferred to the weekly consolidation
LLM instead of auto-invalidating existing facts at ingest time.  Facts are
therefore appended only during ingestion.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_ingest_text_appends_fact_without_invalidation(tmp_path) -> None:
    from core.memory.backend.neo4j_graph import Neo4jGraphBackend

    anima_dir = tmp_path / "animas" / "test-anima"
    anima_dir.mkdir(parents=True)

    backend = Neo4jGraphBackend(anima_dir, group_id="test_group")

    mock_driver = AsyncMock()
    mock_driver.execute_write = AsyncMock()
    mock_driver.execute_query = AsyncMock(return_value=[])
    backend._driver = mock_driver
    backend._schema_ensured = True

    mock_entity = MagicMock(name="Alice", summary="A person")
    mock_entity.name = "Alice"
    mock_fact = MagicMock()
    mock_fact.source_entity = "Alice"
    mock_fact.target_entity = "Alice"
    mock_fact.fact = "Alice lives in Osaka"
    mock_fact.valid_at = "2025-06-01T00:00:00"

    mock_extractor = MagicMock()
    mock_extractor.extract_entities = AsyncMock(return_value=[mock_entity])
    mock_extractor.extract_facts = AsyncMock(return_value=[mock_fact])

    mock_resolver_result = MagicMock()
    mock_resolver_result.uuid = "entity-alice"
    mock_resolver_result.name = "Alice"
    mock_resolver_result.summary = "A person"
    mock_resolver_result.is_new = True

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_resolver_result)

    backend._extractor = mock_extractor
    backend._resolver = mock_resolver

    # The invalidator is gone: no _invalidator attribute should exist.
    assert not hasattr(backend, "_invalidator")

    result = await backend.ingest_text("Alice moved to Osaka", source="test")
    # 1 episode + 1 entity + 1 fact, with no invalidation pass.
    assert result == 3
    backend._resolver.resolve.assert_called_once()


@pytest.mark.asyncio
async def test_resolver_always_creates_new_entity() -> None:
    from core.memory.extraction.resolver import EntityResolver, ResolvedEntity
    from core.memory.ontology.default import ExtractedEntity

    resolver = EntityResolver(
        AsyncMock(),
        "group",
        model="test-model",
    )

    entity = ExtractedEntity(name="Alice", entity_type="Person", summary="A person")
    result = await resolver.resolve(entity)

    assert isinstance(result, ResolvedEntity)
    assert result.is_new is True
    assert result.merged_with_uuid is None
    assert result.name == "Alice"

    # Cache still works.
    cached = await resolver.resolve(entity)
    assert cached.uuid == result.uuid
