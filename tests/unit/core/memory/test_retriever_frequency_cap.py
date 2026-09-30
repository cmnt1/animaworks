# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for frequency boost hard cap and per-anima access counting.

Verifies:
- frequency_boost is capped at WEIGHT_FREQUENCY * FREQUENCY_LOG_CAP (0.30)
- Shared chunks use per-anima access count (ac_{anima_name}) for scoring
- Personal chunks continue to use global access_count for scoring
- record_access writes ac_{anima_name} for shared chunks
- record_access writes access_count for personal chunks
"""

from __future__ import annotations

import math
from pathlib import Path
from unittest.mock import MagicMock

from core.memory.rag.retriever import (
    FREQUENCY_LOG_CAP,
    WEIGHT_FREQUENCY,
    MemoryRetriever,
    RetrievalResult,
)
from core.memory.rag.retriever import (
    PER_ANIMA_ACCESS_PREFIX as _PER_ANIMA_AC_PREFIX,
)

# ── Mock fixtures ────────────────────────────────────────────────────


class _MockConfigDisabled:
    class _RAG:
        enable_spreading_activation = False
        spreading_memory_types = ["knowledge", "episodes"]

    rag = _RAG()


def _make_result(
    score: float = 0.8,
    *,
    anima: str = "test_anima",
    memory_type: str = "knowledge",
    access_count: int = 0,
    per_anima_counts: dict[str, int] | None = None,
    importance: str = "",
    updated_at: str = "",
) -> RetrievalResult:
    metadata: dict[str, str | int | float | list[str]] = {
        "anima": anima,
        "memory_type": memory_type,
        "access_count": access_count,
        "updated_at": updated_at,
    }
    if importance:
        metadata["importance"] = importance
    if per_anima_counts:
        for k, v in per_anima_counts.items():
            metadata[f"{_PER_ANIMA_AC_PREFIX}{k}"] = v
    return RetrievalResult(
        doc_id=f"{anima}/{memory_type}/doc.md#0",
        content="Test content",
        score=score,
        metadata=metadata,
        source_scores={"vector": score},
    )


def _make_retriever(tmp_path: Path) -> MemoryRetriever:
    vector_store = MagicMock()
    indexer = MagicMock()
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir(exist_ok=True)
    return MemoryRetriever(vector_store, indexer, knowledge_dir)


# ── Constants ────────────────────────────────────────────────────────


class TestFrequencyConstants:
    def test_frequency_log_cap_value(self) -> None:
        assert FREQUENCY_LOG_CAP == 3.0

    def test_max_frequency_boost(self) -> None:
        assert abs(WEIGHT_FREQUENCY * FREQUENCY_LOG_CAP - 0.30) < 1e-9


# ── Hard cap on frequency_boost ──────────────────────────────────────


class TestFrequencyBoostCap:
    def test_low_access_count_unchanged(self, tmp_path: Path) -> None:
        """access_count=3 behaves identically to old formula."""
        retriever = _make_retriever(tmp_path)
        result = _make_result(access_count=3)
        retriever._apply_score_adjustments([result], "test_anima")

        expected = WEIGHT_FREQUENCY * math.log1p(3)
        assert abs(result.source_scores["frequency"] - expected) < 1e-9

    def test_boundary_access_count(self, tmp_path: Path) -> None:
        """access_count=19 is near the cap but not exceeded."""
        retriever = _make_retriever(tmp_path)
        result = _make_result(access_count=19)
        retriever._apply_score_adjustments([result], "test_anima")

        raw = WEIGHT_FREQUENCY * math.log1p(19)
        cap = WEIGHT_FREQUENCY * FREQUENCY_LOG_CAP
        expected = min(raw, cap)
        assert abs(result.source_scores["frequency"] - expected) < 1e-9

    def test_high_access_count_capped(self, tmp_path: Path) -> None:
        """access_count=265 is capped at WEIGHT_FREQUENCY * FREQUENCY_LOG_CAP."""
        retriever = _make_retriever(tmp_path)
        result = _make_result(access_count=265)
        retriever._apply_score_adjustments([result], "test_anima")

        cap = WEIGHT_FREQUENCY * FREQUENCY_LOG_CAP
        assert abs(result.source_scores["frequency"] - cap) < 1e-9

    def test_extreme_access_count_capped(self, tmp_path: Path) -> None:
        """access_count=10000 is still capped."""
        retriever = _make_retriever(tmp_path)
        result = _make_result(access_count=10000)
        retriever._apply_score_adjustments([result], "test_anima")

        cap = WEIGHT_FREQUENCY * FREQUENCY_LOG_CAP
        assert abs(result.source_scores["frequency"] - cap) < 1e-9

    def test_zero_access_count(self, tmp_path: Path) -> None:
        """access_count=0 gives zero frequency boost."""
        retriever = _make_retriever(tmp_path)
        result = _make_result(access_count=0)
        retriever._apply_score_adjustments([result], "test_anima")

        assert result.source_scores["frequency"] == 0.0


# ── Per-anima access count for shared chunks ─────────────────────────


class TestPerAnimaScoring:
    def test_shared_chunk_uses_per_anima_count(self, tmp_path: Path) -> None:
        """Shared chunk uses ac_{anima_name} for frequency boost, not global."""
        retriever = _make_retriever(tmp_path)
        result = _make_result(
            anima="shared",
            access_count=265,
            per_anima_counts={"rin": 5},
        )
        retriever._apply_score_adjustments([result], "rin")

        expected = min(WEIGHT_FREQUENCY * math.log1p(5), WEIGHT_FREQUENCY * FREQUENCY_LOG_CAP)
        assert abs(result.source_scores["frequency"] - expected) < 1e-9

    def test_shared_chunk_missing_per_anima_defaults_zero(self, tmp_path: Path) -> None:
        """Shared chunk with no ac_{anima} field defaults to 0."""
        retriever = _make_retriever(tmp_path)
        result = _make_result(anima="shared", access_count=265)
        retriever._apply_score_adjustments([result], "new_anima")

        assert result.source_scores["frequency"] == 0.0

    def test_personal_chunk_uses_global_count(self, tmp_path: Path) -> None:
        """Personal chunk uses global access_count, ignoring per-anima fields."""
        retriever = _make_retriever(tmp_path)
        result = _make_result(
            anima="rin",
            access_count=10,
            per_anima_counts={"rin": 999},
        )
        retriever._apply_score_adjustments([result], "rin")

        expected = min(WEIGHT_FREQUENCY * math.log1p(10), WEIGHT_FREQUENCY * FREQUENCY_LOG_CAP)
        assert abs(result.source_scores["frequency"] - expected) < 1e-9

    def test_shared_chunk_without_anima_name_uses_global(self, tmp_path: Path) -> None:
        """When anima_name=None, shared chunks fall back to global access_count."""
        retriever = _make_retriever(tmp_path)
        result = _make_result(anima="shared", access_count=10)
        retriever._apply_score_adjustments([result], None)

        expected = min(WEIGHT_FREQUENCY * math.log1p(10), WEIGHT_FREQUENCY * FREQUENCY_LOG_CAP)
        assert abs(result.source_scores["frequency"] - expected) < 1e-9


# ── record_access per-anima branching ────────────────────────────────


class _FakeCollection:
    """In-memory collection mock that tracks metadata updates."""

    def __init__(self, metadatas: dict[str, dict]) -> None:
        self._data = metadatas

    def get(self, ids=None, include=None):
        if ids is None:
            ids = list(self._data.keys())
        return {
            "ids": ids,
            "metadatas": [self._data.get(i, {}) for i in ids],
        }

    def update(self, ids, metadatas):
        for doc_id, meta in zip(ids, metadatas, strict=False):
            self._data.setdefault(doc_id, {}).update(meta)


class _FakeVectorStore:
    """Minimal vector store mock with per-collection storage."""

    def __init__(self) -> None:
        self.collections: dict[str, _FakeCollection] = {}

    def _ensure_collection(self, name):
        if name not in self.collections:
            self.collections[name] = _FakeCollection({})
        return self.collections[name]

    def get_by_ids(self, collection, ids):
        from core.memory.rag.store import Document

        coll = self._ensure_collection(collection)
        data = coll.get(ids=ids)
        return [Document(id=did, content="", metadata=data["metadatas"][i]) for i, did in enumerate(data["ids"])]

    def get_by_metadata(self, collection, where, limit=20):
        from core.memory.rag.store import Document, SearchResult

        coll = self._ensure_collection(collection)
        data = coll.get()
        return [
            SearchResult(
                document=Document(id=did, content="", metadata=data["metadatas"][i]),
                score=1.0,
            )
            for i, did in enumerate(data["ids"])
        ]

    def update_metadata(self, collection, ids, metadatas):
        coll = self._ensure_collection(collection)
        coll.update(ids, metadatas)


class TestRecordAccessBranching:
    def test_personal_chunk_records_global_access_count(self, tmp_path: Path) -> None:
        vs = _FakeVectorStore()
        vs.collections["rin_knowledge"] = _FakeCollection(
            {
                "doc1": {"access_count": 5, "memory_type": "knowledge", "anima": "rin"},
            }
        )
        retriever = MemoryRetriever(vs, MagicMock(), tmp_path)

        result = _make_result(anima="rin", access_count=5)
        result.doc_id = "doc1"
        retriever.record_access([result], "rin")

        meta = vs.collections["rin_knowledge"]._data["doc1"]
        assert meta["access_count"] == 6
        assert f"{_PER_ANIMA_AC_PREFIX}rin" not in meta

    def test_shared_chunk_records_per_anima_and_global(self, tmp_path: Path) -> None:
        vs = _FakeVectorStore()
        vs.collections["shared_common_knowledge"] = _FakeCollection(
            {
                "sdoc1": {
                    "access_count": 100,
                    "memory_type": "common_knowledge",
                    "anima": "shared",
                },
            }
        )
        retriever = MemoryRetriever(vs, MagicMock(), tmp_path)

        result = _make_result(anima="shared", memory_type="common_knowledge", access_count=100)
        result.doc_id = "sdoc1"
        retriever.record_access([result], "rin")

        meta = vs.collections["shared_common_knowledge"]._data["sdoc1"]
        assert meta[f"{_PER_ANIMA_AC_PREFIX}rin"] == 1
        assert meta["access_count"] == 101

    def test_shared_chunk_multiple_animas_independent(self, tmp_path: Path) -> None:
        """Two different animas increment their own ac_ fields independently."""
        vs = _FakeVectorStore()
        vs.collections["shared_common_knowledge"] = _FakeCollection(
            {
                "sdoc1": {
                    "access_count": 0,
                    "ac_rin": 0,
                    "memory_type": "common_knowledge",
                    "anima": "shared",
                },
            }
        )
        retriever = MemoryRetriever(vs, MagicMock(), tmp_path)

        result = _make_result(anima="shared", memory_type="common_knowledge")
        result.doc_id = "sdoc1"

        retriever.record_access([result], "rin")
        retriever.record_access([result], "sakura")
        retriever.record_access([result], "rin")

        meta = vs.collections["shared_common_knowledge"]._data["sdoc1"]
        assert meta[f"{_PER_ANIMA_AC_PREFIX}rin"] == 2
        assert meta[f"{_PER_ANIMA_AC_PREFIX}sakura"] == 1
        assert meta["access_count"] == 3


# ── Integration: cap + per-anima combined ────────────────────────────


class TestCapAndPerAnimaCombined:
    def test_shared_chunk_no_longer_dominates(self, tmp_path: Path) -> None:
        """Shared chunk with high global count but low per-anima count
        no longer outranks a relevant personal chunk."""
        retriever = _make_retriever(tmp_path)

        personal = _make_result(score=0.90, anima="rin", access_count=3)
        shared = _make_result(
            score=0.87,
            anima="shared",
            access_count=265,
            per_anima_counts={"rin": 2},
        )

        retriever._apply_score_adjustments([personal, shared], "rin")

        assert personal.score > shared.score, (
            f"Personal ({personal.score:.4f}) should outrank shared ({shared.score:.4f})"
        )
