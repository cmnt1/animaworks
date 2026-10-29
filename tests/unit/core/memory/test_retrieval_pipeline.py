from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.memory.retrieval import entity as entity_module
from core.memory.retrieval.entity import expand_alias_terms, extract_entities
from core.memory.retrieval.pipeline import RetrievalPipeline


def test_pipeline_rerank_disabled_keeps_rrf_order() -> None:
    ranked = [
        [
            {"content": "first", "score": 0.5, "source_file": "a.md", "chunk_index": 0},
            {"content": "second", "score": 0.4, "source_file": "b.md", "chunk_index": 0},
        ],
    ]
    pipeline = RetrievalPipeline(reranker=MagicMock())
    result = pipeline.run("q", ranked, limit=2, rerank_enabled=False)
    assert [c["content"] for c in result.items] == ["first", "second"]
    pipeline._reranker.rerank_sync.assert_not_called()


def test_pipeline_empty_lists_abstains() -> None:
    pipeline = RetrievalPipeline(reranker=MagicMock())
    result = pipeline.run("q", [[]], confidence_threshold=0.35)
    assert result.abstain is True
    assert result.items == []


def test_pipeline_single_rrf_list_can_pass_default_confidence_gate() -> None:
    ranked = [[{"content": "hit", "score": 0.8, "source_file": "a.md", "chunk_index": 0}]]
    pipeline = RetrievalPipeline(reranker=MagicMock())

    result = pipeline.run(
        "q",
        ranked,
        limit=1,
        rerank_enabled=False,
        rrf_confidence_threshold=0.02,
    )

    assert result.abstain is False
    assert result.items[0]["content"] == "hit"


def test_pipeline_uses_reranker_when_enabled() -> None:
    reranker = MagicMock()
    reranker.rerank_sync.return_value = [
        {"content": "b", "score": 0.9, "search_method": "cross_encoder"},
    ]
    ranked = [
        [
            {"content": "a", "score": 0.5, "source_file": "a.md", "chunk_index": 0},
            {"content": "b", "score": 0.4, "source_file": "b.md", "chunk_index": 0},
        ],
    ]
    pipeline = RetrievalPipeline(reranker=reranker)
    result = pipeline.run(
        "q",
        ranked,
        limit=1,
        rerank_enabled=True,
    )
    assert result.items[0]["content"] == "b"
    reranker.rerank_sync.assert_called_once()


def test_extract_entities_deduplicates_phrases_and_ignores_speakers() -> None:
    entities = extract_entities(
        'What book did Melanie read from Caroline\'s suggestion, "Becoming Nicole"?',
        ignored_entities=("Melanie", "Caroline"),
    )

    assert "melanie" not in entities
    assert "caroline" not in entities
    assert "becoming nicole" in entities
    assert "book" in entities
    assert "suggestion" in entities


def test_extract_entities_caches_without_sharing_mutable_results(monkeypatch: pytest.MonkeyPatch) -> None:
    entity_module._extract_entities_cached.cache_clear()
    calls = 0
    original = entity_module._content_tokens

    def counted(text: str, ignored: set[str]) -> list[str]:
        nonlocal calls
        calls += 1
        return original(text, ignored)

    monkeypatch.setattr(entity_module, "_content_tokens", counted)
    text = "ZephyrNova launch review by Caroline"
    first = extract_entities(text)
    first.add("mutated")
    second = extract_entities(text)

    assert calls == 1
    assert "mutated" not in second
    assert first - {"mutated"} == second


def test_expand_alias_terms_returns_triggered_aliases_deterministically() -> None:
    aliases = expand_alias_terms(
        "What is Caroline's identity?",
        {"identity": ("transgender", "woman", "transgender woman"), "pets": ("dog",)},
    )

    assert aliases == ("transgender", "woman", "transgender woman")


def test_pipeline_preserves_rrf_order_without_removed_score_adjustments() -> None:
    ranked = [
        [
            {
                "content": "generic memory",
                "score": 0.5,
                "source_file": "a.md",
                "chunk_index": 0,
                "access_count": 0,
            },
            {
                "content": "Melanie read Becoming Nicole after Caroline suggested the book in 2023.",
                "score": 0.4,
                "source_file": "b.md",
                "chunk_index": 0,
                "entities": ["Becoming Nicole"],
                "event_time_iso": "2023-07-20T20:56:00+09:00",
                "access_count": 100,
            },
        ],
    ]
    pipeline = RetrievalPipeline(reranker=MagicMock())

    result = pipeline.run(
        "What book did Melanie read from Caroline's suggestion in 2023?",
        ranked,
        limit=2,
        rerank_enabled=False,
    )

    assert [item["content"] for item in result.items] == [
        "generic memory",
        "Melanie read Becoming Nicole after Caroline suggested the book in 2023.",
    ]
    assert all("entity_boost" not in item for item in result.items)
    assert all("temporal_boost" not in item for item in result.items)
    assert all("access_boost" not in item for item in result.items)
