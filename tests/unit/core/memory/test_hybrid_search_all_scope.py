"""Unit tests for Neo4j hybrid search all-scope behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_fact(uuid: str, fact: str = "test") -> dict:
    return {
        "uuid": uuid,
        "fact": fact,
        "source_name": "A",
        "target_name": "B",
        "valid_at": "2024-01-01T00:00:00Z",
    }


def _make_episode(uuid: str, content: str = "episode text") -> dict:
    return {
        "uuid": uuid,
        "content": content,
        "source": "chat:test",
        "valid_at": "2024-01-01T00:00:00Z",
    }


def _make_entity(uuid: str, name: str = "Entity", summary: str = "summary") -> dict:
    return {
        "uuid": uuid,
        "name": name,
        "summary": summary,
        "entity_type": "Concept",
    }


def _patch_reranker():
    mock_reranker = AsyncMock()

    async def _passthrough(query, items, **kw):
        return [{**it, "ce_score": 0.5} for it in items]

    mock_reranker.rerank = _passthrough
    return patch("core.memory.graph.reranker.get_reranker", return_value=mock_reranker)


@pytest.mark.asyncio
async def test_reranker_accepts_callable_text_resolver():
    from core.memory.graph.reranker import CrossEncoderReranker

    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict.return_value = [0.1, 0.9]
    reranker._model = mock_model
    reranker._available = True
    items = [
        {"type": "fact", "fact": "fact text"},
        {"type": "episode", "content": "episode text"},
    ]

    result = await reranker.rerank(
        "query",
        items,
        text_field=lambda item: item.get("fact") or item.get("content", ""),
    )

    assert result[0]["type"] == "episode"
    assert result[1]["type"] == "fact"


@pytest.mark.asyncio
async def test_search_all_includes_fact_entity_and_episode_sources():
    from core.memory.graph.search import HybridSearch

    async def _mock_execute(query, params=None, **kw):
        q = query.strip()
        if "queryRelationships('fact_embedding'" in q:
            return [_make_fact("fact-vector")]
        if "queryNodes('episode_content_embedding'" in q:
            return [_make_episode("episode-vector")]
        if "queryNodes('entity_name_embedding'" in q and "score >= $min_score" not in q:
            return [_make_entity("entity-vector", name="Vector Entity")]
        if "fulltext.queryRelationships" in q:
            return [_make_fact("fact-fulltext")]
        if "fulltext.queryNodes" in q:
            return [_make_entity("entity-fulltext", name="Fulltext Entity")]
        if "score >= $min_score" in q:
            return []
        return []

    driver = AsyncMock()
    driver.execute_query = AsyncMock(side_effect=_mock_execute)

    search = HybridSearch(driver, "test_group")
    with _patch_reranker():
        result = await search.search("query", scope="all", query_embedding=[0.1] * 384, limit=10)

    result_types = {r["type"] for r in result}
    assert {"fact", "entity", "episode"} <= result_types


@pytest.mark.asyncio
async def test_search_all_reranks_with_per_item_text():
    from core.memory.graph.search import HybridSearch

    async def _mock_execute(query, params=None, **kw):
        q = query.strip()
        if "queryRelationships('fact_embedding'" in q:
            return [_make_fact("fact-vector", fact="fact text")]
        if "queryNodes('episode_content_embedding'" in q:
            return [_make_episode("episode-vector", content="episode text")]
        if "queryNodes('entity_name_embedding'" in q and "score >= $min_score" not in q:
            return [_make_entity("entity-vector", name="Entity Name", summary="entity summary")]
        return []

    captured_texts: list[str] = []
    mock_reranker = AsyncMock()

    async def _capture_rerank(query, items, **kw):
        resolver = kw["text_field"]
        captured_texts.extend(resolver(item) for item in items)
        return [{**item, "ce_score": 0.5} for item in items]

    mock_reranker.rerank = _capture_rerank
    driver = AsyncMock()
    driver.execute_query = AsyncMock(side_effect=_mock_execute)

    search = HybridSearch(driver, "test_group")
    with patch("core.memory.graph.reranker.get_reranker", return_value=mock_reranker):
        await search.search("query", scope="all", query_embedding=[0.1] * 384, limit=10)

    assert "fact text" in captured_texts
    assert "episode text" in captured_texts
    assert "Entity Name entity summary" in captured_texts


@pytest.mark.asyncio
async def test_search_all_edge_type_filter_keeps_only_matching_facts():
    from core.memory.graph.search import HybridSearch

    async def _mock_execute(query, params=None, **kw):
        q = query.strip()
        if "queryRelationships('fact_embedding'" in q:
            return [{**_make_fact("fact-vector"), "edge_type": "HAS_PROPERTY"}]
        if "queryNodes('episode_content_embedding'" in q:
            return [_make_episode("episode-vector")]
        if "queryNodes('entity_name_embedding'" in q and "score >= $min_score" not in q:
            return [_make_entity("entity-vector")]
        return []

    driver = AsyncMock()
    driver.execute_query = AsyncMock(side_effect=_mock_execute)

    search = HybridSearch(driver, "test_group")
    with _patch_reranker():
        result = await search.search(
            "query",
            scope="all",
            query_embedding=[0.1] * 384,
            edge_type_filter="HAS_PROPERTY",
            limit=10,
        )

    assert [r["uuid"] for r in result] == ["fact-vector"]


@pytest.mark.asyncio
async def test_retrieve_all_scope_formats_mixed_result_types(tmp_path):
    from core.memory.backend.neo4j_graph import Neo4jGraphBackend

    backend = Neo4jGraphBackend(tmp_path)
    mock_results = [
        {**_make_fact("f1", "likes coffee"), "type": "fact", "ce_score": 0.9},
        {**_make_episode("ep1", "episode content"), "type": "episode", "ce_score": 0.8},
        {**_make_entity("e1", "Alice", "A software engineer"), "type": "entity", "ce_score": 0.7},
    ]

    mock_hs = AsyncMock()
    mock_hs.search = AsyncMock(return_value=mock_results)

    with (
        patch.object(backend, "_ensure_driver", new_callable=AsyncMock),
        patch("core.memory.graph.search.HybridSearch", return_value=mock_hs),
    ):
        result = await backend.retrieve("coffee", scope="all")

    assert [mem.source for mem in result] == ["fact:f1", "episode:ep1", "entity:e1"]
    assert "likes coffee" in result[0].content
    assert result[1].content == "episode content"
    assert result[2].content == "Alice: A software engineer"
