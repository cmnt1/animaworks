from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.skills.dense (embedding similarity for the skill router)."""

from pathlib import Path

import pytest

import core.skills.dense as skill_dense
from core.paths import get_shared_dir
from core.skills.models import SkillMetadata
from core.skills.router import SkillRouter


def _skill(name: str, description: str, *, path: Path | None = None) -> SkillMetadata:
    if path is None:
        path = Path("/skills") / name / "SKILL.md"
    return SkillMetadata(
        name=name,
        description=description,
        path=path,
    )


def _fake_embed(texts: list[str], *, purpose: str = "document", priority: str = "interactive") -> list[list[float]]:
    """Vector scheme: ``pdf``-containing text -> [1,0,0], otherwise -> [0,1,0]."""
    out: list[list[float]] = []
    for text in texts:
        if "pdf" in text.casefold():
            out.append([1.0, 0.0, 0.0])
        else:
            out.append([0.0, 1.0, 0.0])
    return out


def test_returns_cosine_similarity(monkeypatch) -> None:
    monkeypatch.setattr(skill_dense, "generate_embeddings", _fake_embed)
    pdf = _skill("md-to-pdf", "PDF変換する", path=Path("/skills/md-to-pdf/SKILL.md"))
    other = _skill("note-tool", "メモを書く", path=Path("/skills/note-tool/SKILL.md"))

    scores = skill_dense.skill_dense_scores("PDFを作って", [pdf, other])

    # rank-based: only similar skills (cos >= DENSE_MIN_SIM) get a bonus; top-1 = 1.0
    assert scores == {"/skills/md-to-pdf/SKILL.md": pytest.approx(1.0)}


def test_scores_below_min_sim_are_zeroed(monkeypatch) -> None:
    monkeypatch.setattr(skill_dense, "generate_embeddings", _fake_embed)
    skill = _skill("foo", "PDF関係", path=Path("/skills/foo/SKILL.md"))
    # Query not pdf-related => cosine 0 with the pdf-vector -> zeroed / not the
    # below-threshold branch; craft a near-miss via a dedicated below-threshold
    # vector below using a custom embedder.
    monkeypatch.setattr(
        skill_dense,
        "generate_embeddings",
        lambda texts, purpose="document", priority="interactive": [[1.0, 0.0, 0.0]] * len(texts) if purpose == "document" else [[0.3, 0.95, 0.0]],
    )
    scores = skill_dense.skill_dense_scores("anything", [skill])
    assert "/skills/foo/SKILL.md" not in scores


def test_disk_cache_written_and_document_only_computed_once(monkeypatch, tmp_path: Path) -> None:
    calls: dict[str, int] = {"query": 0, "document": 0}

    def _embed(texts, *, purpose="document", priority="interactive"):
        calls[purpose] += 1
        return _fake_embed(texts, purpose=purpose)

    monkeypatch.setattr(skill_dense, "generate_embeddings", _embed)
    pdf = _skill("md-to-pdf", "PDF変換する", path=Path("/skills/md-to-pdf/SKILL.md"))

    skill_dense.skill_dense_scores("PDFを作って", [pdf])
    assert calls["document"] == 1
    cache_path = get_shared_dir() / skill_dense._CACHE_FILENAME
    assert cache_path.is_file()

    # Second call must not recompute document embeddings (or query, LRU).
    skill_dense.skill_dense_scores("PDFを作って", [pdf])
    assert calls["document"] == 1
    assert calls["query"] == 1


def test_returns_empty_on_exception(monkeypatch) -> None:
    def _boom(texts, *, purpose="document", priority="interactive"):
        raise RuntimeError("model not loaded")

    monkeypatch.setattr(skill_dense, "generate_embeddings", _boom)
    skill = _skill("foo", "anything", path=Path("/skills/foo/SKILL.md"))

    assert skill_dense.skill_dense_scores("query", [skill]) == {}


def test_dense_weight_scales_router_score() -> None:
    meta = _skill("unique-skill", "totally unrelated text", path=Path("/skills/unique-skill/SKILL.md"))
    dense_scores = {"/skills/unique-skill/SKILL.md": 0.8}

    with_weight = SkillRouter(include_body=False, dense_weight=6.0).route(
        "unrelated query",
        [meta],
        top_k=1,
        dense_scores=dense_scores,
    )
    assert with_weight
    assert with_weight[0].score >= 6.0 * 0.8 - 1e-3
    assert any(r.startswith("dense:") for r in with_weight[0].reasons)

    zero_weight = SkillRouter(include_body=False, dense_weight=0.0).route(
        "unrelated query",
        [meta],
        top_k=1,
        dense_scores=dense_scores,
    )
    assert zero_weight == []


def test_rank_based_bonus_top_k(monkeypatch) -> None:
    """Top DENSE_TOP_K by cosine get 1.0, 0.8, ... and the rest nothing."""
    vecs = {f"s{i}": [1.0, 0.1 * i, 0.0] for i in range(8)}

    def fake(texts, purpose="document", priority="interactive"):
        if purpose == "query":
            return [[1.0, 0.0, 0.0]]
        return [vecs[t.split("\n", 1)[0]] for t in texts]

    monkeypatch.setattr(skill_dense, "generate_embeddings", fake)
    skills = [_skill(f"s{i}", "d", path=Path(f"/skills/s{i}/SKILL.md")) for i in range(8)]
    scores = skill_dense.skill_dense_scores("q", skills)
    assert len(scores) == skill_dense.DENSE_TOP_K
    assert scores["/skills/s0/SKILL.md"] == pytest.approx(1.0)
    assert scores["/skills/s4/SKILL.md"] == pytest.approx(0.2)
    assert "/skills/s7/SKILL.md" not in scores
