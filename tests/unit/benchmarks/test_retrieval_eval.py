from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from benchmarks.retrieval_eval.build_dataset import extract_anima_queries
from benchmarks.retrieval_eval.run_eval import score_query, variant_settings
from core.config.schemas import RAGConfig


def _activity_file(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "2026-09-30.jsonl"
    path.write_text("".join(json.dumps(entry) + "\n" for entry in entries), encoding="utf-8")
    return path


def _search(ts: str, query: str) -> dict:
    return {
        "ts": ts,
        "type": "tool_use",
        "tool": "search_memory",
        "meta": {"args": {"query": query, "scope": "episodes"}},
    }


def _read(ts: str, path: str) -> dict:
    return {
        "ts": ts,
        "type": "tool_use",
        "tool": "mcp__aw__read_memory_file",
        "meta": {"args": {"path": path}},
    }


def test_extracts_gold_with_line_and_time_windows_and_excludes_empty_gold(tmp_path: Path) -> None:
    entries = [
        _search("2026-09-30T10:00:00Z", "first synthetic query"),
        {"ts": "2026-09-30T10:11:00Z", "type": "message", "summary": "fictional"},
        _read("2026-09-30T10:12:00Z", "episodes/first.md"),
        _search("2026-09-30T10:11:00Z", "time-window synthetic query"),
        {"ts": "2026-09-30T10:12:00Z", "type": "message"},
        {"ts": "2026-09-30T10:13:00Z", "type": "message"},
        _read("2026-09-30T10:14:00Z", "episodes/second.md"),
        _search("2026-09-30T10:20:00Z", "no gold synthetic query"),
        *[{"ts": f"2026-09-30T10:21:{second:02d}Z", "type": "message"} for second in range(20)],
    ]
    path = _activity_file(tmp_path, entries)

    queries = extract_anima_queries(
        "fictional-anima",
        [path],
        since=datetime(2026, 9, 1, tzinfo=UTC),
        lookahead_lines=2,
        window_minutes=10,
    )

    assert [item["query"] for item in queries] == ["first synthetic query", "time-window synthetic query"]
    assert queries[0]["gold_paths"] == ["episodes/first.md"]
    assert queries[1]["gold_paths"] == ["episodes/second.md"]
    assert all(item["anima"] == "fictional-anima" for item in queries)


def test_extract_caps_each_anima_to_most_recent_queries(tmp_path: Path) -> None:
    entries: list[dict] = []
    for minute in range(3):
        ts = f"2026-09-30T10:{minute:02d}:00Z"
        entries.extend(
            [
                _search(ts, f"synthetic query {minute}"),
                _read(f"2026-09-30T10:{minute:02d}:01Z", f"episodes/{minute}.md"),
            ]
        )
    path = _activity_file(tmp_path, entries)

    queries = extract_anima_queries(
        "fictional-anima",
        [path],
        since=datetime(2026, 9, 1, tzinfo=UTC),
        per_anima_limit=2,
    )

    assert [item["query"] for item in queries] == ["synthetic query 1", "synthetic query 2"]


def test_recall_mrr_and_hit_metrics_use_gold_file_paths() -> None:
    metrics = score_query(
        ["episodes/a.md", "episodes/c.md"],
        ["episodes/x.md", "episodes/a.md", "episodes/c.md"],
    )

    assert metrics == {"recall@5": 1.0, "recall@10": 1.0, "mrr": 0.5, "hit@10": 1.0}
    assert score_query(["episodes/missing.md"], ["episodes/a.md"])["mrr"] == 0.0


def test_variant_settings_do_not_mutate_schema_config() -> None:
    config = RAGConfig()

    settings = variant_settings(config, "minimal")

    assert settings["rerank_enabled"] is False
    assert settings["entity_registry_enabled"] is False
    assert not any("graph" in key or "spreading" in key for key in settings)
    assert config.rerank_enabled is True
    assert not hasattr(config, "enable_spreading_activation")


def test_read_only_search_does_not_flush_access_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from core.memory.rag.retriever import AccessBatch, RetrievalResult
    from core.memory.retrieval.rag_search import RAGMemorySearch
    from core.memory.retrieval.unified_search import UnifiedMemorySearch

    rag_search = RAGMemorySearch(
        tmp_path / "animas" / "fictional", tmp_path / "common_knowledge", tmp_path / "common_skills"
    )
    rag_search._get_indexer = lambda: None

    def collect_with_access_record(self, _rag, **kwargs):
        del self
        kwargs["access_batch"].record(
            [
                RetrievalResult(
                    doc_id="episodes/fake.md",
                    content="fabricated test content",
                    score=1.0,
                    metadata={"memory_type": "episodes", "anima": "fictional"},
                    source_scores={},
                )
            ],
            "fictional",
            kind="retrieved",
        )
        return []

    def fail_if_flushed(_self, _vector_store):
        pytest.fail("read-only evaluation attempted to flush access metadata")

    monkeypatch.setattr(UnifiedMemorySearch, "_collect_ranked_lists", collect_with_access_record)
    monkeypatch.setattr(AccessBatch, "flush", fail_if_flushed)

    results = rag_search.search_memory_text(
        "fabricated query",
        scope="episodes",
        episodes_dir=tmp_path / "episodes",
        knowledge_dir=tmp_path / "knowledge",
        procedures_dir=tmp_path / "procedures",
        common_knowledge_dir=tmp_path / "common_knowledge",
        pipeline_settings=variant_settings({}, "minimal"),
        read_only=True,
    )

    assert results == []
