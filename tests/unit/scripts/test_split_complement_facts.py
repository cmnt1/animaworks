from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from pathlib import Path

from core.memory.facts.store import FactRecord, append_fact_records, read_fact_records
from scripts.migrations.split_complement_facts import split_anima_facts, split_text


def test_split_text_restores_joined_facts_and_keeps_unmerged_text() -> None:
    assert split_text("AはBを使う。 CはDに依存する。 Eは完了した。") == [
        "AはBを使う。",
        "CはDに依存する。",
        "Eは完了した。",
    ]
    assert split_text("PR #1は承認された。Issue #2は保留。") == ["PR #1は承認された。Issue #2は保留。"]


def _blob_store(tmp_path: Path) -> tuple[Path, FactRecord]:
    anima_dir = tmp_path / "rin"
    existing = FactRecord(text="PR #3はmergeされた。", recorded_at="2026-10-04T10:00:00+09:00")
    blob = FactRecord(
        text="PR #1はrinが承認した。 PR #2はsoraが検証した。 PR #3はmergeされた。",
        source_entity="PR #1",
        target_entity="rin",
        edge_type="APPROVED_BY",
        entities=["sora"],
        recorded_at="2026-10-04T09:00:00+09:00",
        source_episode="episodes/2026-10-04.md",
        confidence=0.9,
    )
    expired = FactRecord(
        text="古い事実。 別の古い事実。",
        recorded_at="2026-10-04T08:00:00+09:00",
        valid_until="2026-10-04T08:30:00+09:00",
    )
    append_fact_records(anima_dir, [existing, blob, expired])
    return anima_dir, blob


def test_split_anima_facts_dry_run_writes_nothing(tmp_path: Path) -> None:
    anima_dir, _blob = _blob_store(tmp_path)
    path = next((anima_dir / "facts").glob("*.jsonl"))
    before = path.read_text(encoding="utf-8")

    stats = split_anima_facts(anima_dir, apply=False)

    assert stats.records_split == 1
    assert stats.pieces_added == 1
    assert stats.pieces_dropped_duplicate == 1
    assert path.read_text(encoding="utf-8") == before


def test_split_anima_facts_apply_keeps_id_and_splits_pieces(tmp_path: Path) -> None:
    anima_dir, blob = _blob_store(tmp_path)
    path = next((anima_dir / "facts").glob("*.jsonl"))

    split_anima_facts(anima_dir, apply=True)

    records = {record.text: record for record in read_fact_records(path, include_expired=True)}
    head = records["PR #1はrinが承認した。"]
    assert head.fact_id == blob.fact_id
    assert head.edge_type == "APPROVED_BY"
    assert head.entities == ["PR #1", "rin"]
    piece = records["PR #2はsoraが検証した。"]
    assert piece.fact_id != blob.fact_id
    assert piece.source_entity == ""
    assert piece.entities == ["sora"]
    assert piece.source_episode == "episodes/2026-10-04.md"
    assert piece.confidence == 0.9
    assert sum(1 for text in records if text == "PR #3はmergeされた。") == 1
    assert "古い事実。 別の古い事実。" in records
    assert split_anima_facts(anima_dir, apply=True).records_split == 0
