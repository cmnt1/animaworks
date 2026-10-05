"""Unit tests for reciprocal-rank fusion."""

from __future__ import annotations

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
