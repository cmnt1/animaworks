from __future__ import annotations

from pathlib import Path

import pytest

from core.memory.facts.store import FactRecord, append_fact_records
from core.memory.retrieval.rag_search import RAGMemorySearch


@pytest.mark.e2e
def test_legacy_atomic_facts_search_flow(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    for subdir in ("knowledge", "episodes", "procedures", "facts"):
        (anima_dir / subdir).mkdir(parents=True)
    common_knowledge_dir = tmp_path / "common_knowledge"
    common_skills_dir = tmp_path / "common_skills"
    common_knowledge_dir.mkdir()
    common_skills_dir.mkdir()

    append_fact_records(
        anima_dir,
        [
            FactRecord(
                text="Alice prefers LoCoMo benchmark reports when evaluating memory changes.",
                source_entity="Alice",
                target_entity="LoCoMo benchmark reports",
                edge_type="PREFERS",
                valid_at="2026-06-03T10:00:00+09:00",
                recorded_at="2026-06-03T10:05:00+09:00",
                source_episode="episodes/2026-06-03.md",
                source_session_id="session-locomo",
            ),
            FactRecord(
                text="Alice used an expired LoCoMo rubric.",
                source_entity="Alice",
                target_entity="LoCoMo rubric",
                edge_type="USED",
                recorded_at="2026-06-03T10:06:00+09:00",
                valid_until="2000-01-01T00:00:00+00:00",
            ),
        ],
    )

    rag = RAGMemorySearch(anima_dir, common_knowledge_dir, common_skills_dir)
    search_kwargs = {
        "knowledge_dir": anima_dir / "knowledge",
        "episodes_dir": anima_dir / "episodes",
        "procedures_dir": anima_dir / "procedures",
        "common_knowledge_dir": common_knowledge_dir,
        "result_limit": 5,
    }
    scoped = rag.search_memory_text("LoCoMo reports", scope="facts", **search_kwargs)
    recent = rag.search_memory_text("LoCoMo reports", scope="facts", **search_kwargs)
    all_scope = rag.search_memory_text("LoCoMo reports", scope="all", **search_kwargs)

    assert [r["content"] for r in scoped] == ["Alice prefers LoCoMo benchmark reports when evaluating memory changes."]
    assert recent[0]["fact_id"] == scoped[0]["fact_id"]
    assert any(r["memory_type"] == "facts" for r in all_scope)
    assert all("expired" not in r["content"].lower() for r in scoped + recent + all_scope)
