"""Unit tests for reciprocal-rank fusion and cross-encoder reranking."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

# ── TestRRFMerge ──────────────────────────────────────────────────────────


class TestRRFMerge:
    """Tests for reciprocal rank fusion merge."""

    def _rrf(self, *args, **kwargs):
        from core.memory.retrieval.rrf import rrf_merge

        return rrf_merge(*args, **kwargs)

    def test_single_list(self):
        results = self._rrf([[{"uuid": "a", "fact": "x"}, {"uuid": "b", "fact": "y"}]])
        assert len(results) == 2
        assert all("rrf_score" in r for r in results)
        assert results[0]["rrf_score"] >= results[1]["rrf_score"]

    def test_two_lists_overlap(self):
        list1 = [{"uuid": "a", "fact": "f1"}, {"uuid": "b", "fact": "f2"}]
        list2 = [{"uuid": "a", "fact": "f1"}, {"uuid": "c", "fact": "f3"}]
        results = self._rrf([list1, list2])

        scores = {r["uuid"]: r["rrf_score"] for r in results}
        assert scores["a"] > scores["b"]
        assert scores["a"] > scores["c"]

    def test_deduplication(self):
        list1 = [{"uuid": "a"}, {"uuid": "b"}]
        list2 = [{"uuid": "a"}, {"uuid": "c"}]
        results = self._rrf([list1, list2])
        uuids = [r["uuid"] for r in results]
        assert uuids.count("a") == 1

    def test_empty_input(self):
        assert self._rrf([]) == []
        assert self._rrf([[]]) == []

    def test_top_k_limit(self):
        items = [{"uuid": str(i)} for i in range(20)]
        results = self._rrf([items], top_k=5)
        assert len(results) == 5

    def test_custom_k_constant(self):
        items = [{"uuid": "a"}, {"uuid": "b"}]
        r_k1 = self._rrf([items], k=1)
        r_k60 = self._rrf([items], k=60)
        assert r_k1[0]["rrf_score"] != r_k60[0]["rrf_score"]
        assert r_k1[0]["rrf_score"] > r_k60[0]["rrf_score"]

    def test_key_field(self):
        items = [{"id": "x", "fact": "f1"}, {"id": "y", "fact": "f2"}]
        results = self._rrf([items], key_field="id")
        uuids = {r["id"] for r in results}
        assert uuids == {"x", "y"}


# ── TestCrossEncoderReranker ──────────────────────────────────────────────


def _make_reranker_with_mock(scores: list[float]):
    """Create a CrossEncoderReranker with a pre-injected mock model."""
    from core.memory.retrieval.reranker import CrossEncoderReranker

    reranker = CrossEncoderReranker()
    mock_model = MagicMock()
    mock_model.predict.return_value = scores
    reranker._model = mock_model
    reranker._available = True
    return reranker


class TestCrossEncoderReranker:
    """Tests for cross-encoder reranker with mocked model."""

    @pytest.mark.asyncio
    async def test_rerank_with_mock_model(self):
        reranker = _make_reranker_with_mock([0.1, 0.9, 0.5])
        items = [{"fact": "a"}, {"fact": "b"}, {"fact": "c"}]
        result = await reranker.rerank("query", items)

        assert result[0]["fact"] == "b"
        assert result[1]["fact"] == "c"
        assert result[2]["fact"] == "a"

    @pytest.mark.asyncio
    async def test_rerank_fallback_on_import_error(self):
        from core.memory.retrieval.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker()
        reranker._available = True
        reranker._model = None

        mock_st = MagicMock()
        mock_st.CrossEncoder = MagicMock(side_effect=ImportError("no module"))
        with patch.dict(sys.modules, {"sentence_transformers": mock_st}):
            items = [{"fact": "a"}, {"fact": "b"}, {"fact": "c"}]
            result = await reranker.rerank("query", items)

        assert result == items
        assert all("ce_score" not in r for r in result)

    @pytest.mark.asyncio
    async def test_rerank_fallback_on_scoring_error(self):
        reranker = _make_reranker_with_mock([])
        reranker._model.predict.side_effect = RuntimeError("predict failed")

        items = [{"fact": "a", "rrf_score": 0.4}, {"fact": "b", "rrf_score": 0.3}]
        result = await reranker.rerank("query", items)

        assert result == items
        assert all("ce_score" not in r for r in result)

    @pytest.mark.asyncio
    async def test_rerank_empty_items(self):
        from core.memory.retrieval.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker()
        result = await reranker.rerank("query", [])
        assert result == []

    @pytest.mark.asyncio
    async def test_rerank_adds_ce_score(self):
        reranker = _make_reranker_with_mock([0.7, 0.3])
        result = await reranker.rerank("q", [{"fact": "x"}, {"fact": "y"}])

        assert all("ce_score" in r for r in result)
        assert result[0]["ce_score"] == pytest.approx(0.7)
        assert result[1]["ce_score"] == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_rerank_accepts_callable_text_resolver(self):
        reranker = _make_reranker_with_mock([0.1, 0.9])
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
