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

        assert result == []
        mock_driver.execute_write.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_candidates_partial_contradiction(
        self, invalidator: EdgeInvalidator, mock_driver: AsyncMock
    ) -> None:
        mock_driver.execute_query = AsyncMock(
            side_effect=[
                [
                    _make_candidate("fact-a", "Alice lives in Tokyo"),
                    _make_candidate("fact-b", "Alice likes sushi"),
                ],
                [],
            ]
        )

        llm_resp = MagicMock()
        llm_resp.choices = [MagicMock()]
        llm_resp.choices[0].message.content = json.dumps({"contradicted_uuids": ["fact-a"]})

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_resp):
            result = await invalidator.find_and_invalidate(**COMMON_KWARGS)

        assert result == ["fact-a"]
        assert mock_driver.execute_write.call_count == 1
        assert mock_driver.execute_write.call_args[0][1]["uuid"] == "fact-a"

    @pytest.mark.asyncio
    async def test_reverse_direction_candidates(self, invalidator: EdgeInvalidator, mock_driver: AsyncMock) -> None:
        mock_driver.execute_query = AsyncMock(
            side_effect=[
                [],
                [_make_candidate("rev-fact-1", "Tokyo is home to Alice")],
            ]
        )

        llm_resp = MagicMock()
        llm_resp.choices = [MagicMock()]
        llm_resp.choices[0].message.content = json.dumps({"contradicted_uuids": ["rev-fact-1"]})

        with patch("litellm.acompletion", new_callable=AsyncMock, return_value=llm_resp):
            result = await invalidator.find_and_invalidate(**COMMON_KWARGS)

        assert result == ["rev-fact-1"]
        assert mock_driver.execute_query.call_count == 2
        mock_driver.execute_write.assert_called_once()


# ── TestParseInvalidationResponse ───────────────────────────


class TestParseInvalidationResponse:
    def test_parse_valid_json(self) -> None:
        text = '{"contradicted_uuids": ["abc"]}'
        assert EdgeInvalidator._parse_invalidation_response(text) == ["abc"]

    def test_parse_json_in_fence(self) -> None:
        text = '```json\n{"contradicted_uuids": ["abc"]}\n```'
        assert EdgeInvalidator._parse_invalidation_response(text) == ["abc"]

    def test_parse_empty_list(self) -> None:
        text = '{"contradicted_uuids": []}'
        assert EdgeInvalidator._parse_invalidation_response(text) == []

    def test_parse_invalid_json(self) -> None:
        text = "this is not json at all"
        assert EdgeInvalidator._parse_invalidation_response(text) == []

    def test_parse_list_format(self) -> None:
        text = '["abc", "def"]'
        assert EdgeInvalidator._parse_invalidation_response(text) == ["abc", "def"]


# ── TestTemporalQueries ─────────────────────────────────────


class TestTemporalQueries:
    def test_find_active_facts_query_has_null_check(self) -> None:
        assert "invalid_at IS NULL" in FIND_ACTIVE_FACTS_FOR_PAIR

    def test_invalidate_fact_query_sets_invalid_at(self) -> None:
        assert "SET r.invalid_at" in INVALIDATE_FACT

    def test_find_valid_facts_has_temporal_filter(self) -> None:
        assert "invalid_at IS NULL OR r.invalid_at >" in FIND_VALID_FACTS_BY_GROUP


# ── TestIngestIntegration ───────────────────────────────────


class TestIngestIntegration:
    @pytest.mark.asyncio
    async def test_ingest_text_calls_invalidator(self, tmp_path) -> None:
        from core.memory.backend.neo4j_graph import Neo4jGraphBackend

        anima_dir = tmp_path / "animas" / "test-anima"
        anima_dir.mkdir(parents=True)

        backend = Neo4jGraphBackend(anima_dir, group_id="test_group")

        mock_driver = AsyncMock()
        mock_driver.execute_write = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[])
        backend._driver = mock_driver
        backend._schema_ensured = True
        backend._embed_texts = AsyncMock(return_value=[[0.0]])


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

        mock_driver = AsyncMock()
        mock_driver.execute_write = AsyncMock()
        mock_driver.execute_query = AsyncMock(return_value=[])
        backend._driver = mock_driver
        backend._schema_ensured = True
        backend._embed_texts = AsyncMock(return_value=[[0.0]])

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
