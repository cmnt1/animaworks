from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from core.memory.retrieval.unified_search import UnifiedMemorySearch


class StaticRAGSearch:
    def __init__(self, anima_dir: Path) -> None:
        self._anima_dir = anima_dir
        self.queries: list[str] = []

    def _load_rag_pipeline_settings(self) -> dict[str, object]:
        return {
            "rerank_enabled": False,
            "rerank_candidate_pool": 10,
            "cross_encoder_model": "dummy",
            "abstain_on_low_confidence": False,
            "confidence_threshold": 0.35,
            "rrf_confidence_threshold": 0.02,
        }

    def _get_indexer(self) -> object:
        return object()

    def _vector_search_primary(self, query: str, scope: str, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.queries.append(query)
        if scope != "episodes":
            return []
        return [
            {
                "doc_id": "outside",
                "source_file": "outside.md",
                "chunk_index": 0,
                "memory_type": "episodes",
                "content": "Caroline discussed an unrelated trip.",
                "score": 0.99,
                "event_time_iso": "2023-04-20T10:00:00+00:00",
                "access_count": 100,
            },
            {
                "doc_id": "inside-low",
                "source_file": "inside-low.md",
                "chunk_index": 0,
                "memory_type": "episodes",
                "content": "Caroline visited the library.",
                "score": 0.7,
                "event_time_iso": "2023-05-07T10:00:00+00:00",
            },
            {
                "doc_id": "inside-high",
                "source_file": "inside-high.md",
                "chunk_index": 0,
                "memory_type": "episodes",
                "content": "Caroline visited the bookstore.",
                "score": 0.7,
                "event_time_iso": "2023-05-07T12:00:00+00:00",
            },
        ]

    def _graph_episodes_search(self, query: str, pool_k: int, knowledge_dir: Path) -> list[dict[str, Any]]:
        return []

    def _keyword_search_fallback(self, query: str, scope: str, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []


@pytest.mark.e2e
def test_unified_legacy_retrieval_expands_temporal_query_filters_without_score_boosts(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir(parents=True)
    rag = StaticRAGSearch(anima_dir)
    searcher = UnifiedMemorySearch(anima_dir, rag_search=rag)

    results = searcher.search(
        "What did Caroline do yesterday?",
        scope="episodes",
        limit=2,
        trigger="chat",
        reference_time=datetime(2023, 5, 8, 12, 0, tzinfo=UTC),
    )

    query_expansion = searcher.last_search_meta["query_expansion"]
    assert rag.queries[0] == "What did Caroline do yesterday?"
    assert "2023-05-07" in query_expansion["search_text"]
    assert query_expansion["time_hint_start"] == "2023-05-07"
    assert query_expansion["time_hint_end"] == "2023-05-07"
    assert [item["doc_id"] for item in results] == ["inside-low", "inside-high"]
    assert all(item["doc_id"] != "outside" for item in results)
    assert all("access_boost" not in item for item in results)
