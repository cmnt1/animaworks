"""E2E coverage for Sakura Neo4j memory recovery behavior."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_llm_response(content: str) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_custom_endpoint_entity_extraction_routes_through_openai_provider() -> None:
    """A bare model id with api_base should reach LiteLLM as openai/<model>."""
    from core.memory.extraction.extractor import FactExtractor

    payload = {
        "entities": [
            {"name": "FutureSync", "entity_type": "Organization", "summary": "A company"},
        ]
    }
    cfg = MagicMock()
    cfg.consolidation.llm_model = "anthropic/claude-sonnet-4-6"
    cfg.credentials = {}

    extractor = FactExtractor(
        model="deepseek-v4-flash",
        max_retries=1,
        llm_extra={
            "api_base": "http://localhost:4000/v1",
            "api_key": "dummy",
            "timeout": 120,
        },
    )

    with (
        patch("core.memory._llm_utils.ensure_credentials_in_env"),
        patch("core.config.load_config", return_value=cfg),
        patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion,
    ):
        mock_acompletion.return_value = _make_llm_response(json.dumps(payload, ensure_ascii=False))
        entities = await extractor.extract_entities("FutureSyncについて")

    assert [entity.name for entity in entities] == ["FutureSync"]
    kwargs = mock_acompletion.call_args.kwargs
    assert kwargs["model"] == "openai/deepseek-v4-flash"
    assert kwargs["api_base"] == "http://localhost:4000/v1"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_neo4j_backend_all_scope_retrieves_and_formats_mixed_results(tmp_path) -> None:
    """Neo4jGraphBackend.retrieve(scope='all') should use HybridSearch end to end."""
    from core.memory.backend.neo4j_graph import Neo4jGraphBackend

    async def _mock_execute(query, params=None, **kw):
        q = query.strip()
        if "queryRelationships('fact_embedding'" in q:
            return [
                {
                    "uuid": "fact-1",
                    "fact": "FutureSync uses Neo4j memory",
                    "source_name": "FutureSync",
                    "target_name": "Neo4j",
                    "valid_at": "2026-05-14T00:00:00Z",
                }
            ]
        if "queryNodes('episode_content_embedding'" in q:
            return [
                {
                    "uuid": "episode-1",
                    "content": "Recent Sakura episode about Neo4j",
                    "source": "chat:sakura",
                    "valid_at": "2026-05-14T00:00:00Z",
                }
            ]
        if "queryNodes('entity_name_embedding'" in q and "score >= $min_score" not in q:
            return [
                {
                    "uuid": "entity-1",
                    "name": "Sakura",
                    "summary": "An Anima using Neo4j memory",
                    "entity_type": "Agent",
                }
            ]
        if "score >= $min_score" in q:
            return []
        return []

    async def _passthrough_rerank(query, items, **kw):
        return [{**item, "ce_score": 0.5} for item in items]

    driver = AsyncMock()
    driver.execute_query = AsyncMock(side_effect=_mock_execute)
    backend = Neo4jGraphBackend(tmp_path)

    mock_reranker = AsyncMock()
    mock_reranker.rerank = _passthrough_rerank

    with (
        patch.object(backend, "_ensure_driver", new_callable=AsyncMock, return_value=driver),
        patch.object(backend, "_embed_texts", new_callable=AsyncMock, return_value=[[0.1] * 384]),
        patch("core.memory.graph.reranker.get_reranker", return_value=mock_reranker),
    ):
        memories = await backend.retrieve("Sakura Neo4j", scope="all", limit=10)

    sources = {memory.source for memory in memories}
    assert {"fact:fact-1", "episode:episode-1", "entity:entity-1"} <= sources
    assert any("FutureSync -[RELATES_TO]-> Neo4j" in memory.content for memory in memories)
    assert any(memory.content == "Recent Sakura episode about Neo4j" for memory in memories)
    assert any(memory.content == "Sakura: An Anima using Neo4j memory" for memory in memories)
