from __future__ import annotations

from pathlib import Path

import pytest

from core.memory import fact_extraction
from core.memory.fact_extraction import extract_and_store_facts
from core.memory.fact_invalidation import ReconcileAction, ReconcileResult
from core.memory.facts import FactRecord


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_and_store_facts_duplicate_reconcile_skips_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = FactRecord(
        text="Alice tracks LoCoMo memory scores.",
        source_entity="Alice",
        target_entity="LoCoMo",
        edge_type="TRACKS",
        recorded_at="2026-06-03T10:00:00+09:00",
    )

    async def fake_extract(*args, **kwargs):
        return [record]

    def fail_append(*args, **kwargs):
        raise AssertionError("duplicate reconcile should skip append")

    monkeypatch.setattr(fact_extraction, "extract_fact_records", fake_extract)
    monkeypatch.setattr(fact_extraction, "append_fact_records", fail_append)
    monkeypatch.setattr(
        fact_extraction,
        "reconcile_new_fact",
        lambda *_args, **_kwargs: ReconcileResult(
            action=ReconcileAction.SKIP,
            fact=record,
            should_append=False,
            reason="duplicate",
        ),
    )

    stored = await extract_and_store_facts(
        tmp_path / "alice",
        "Alice tracks LoCoMo memory scores.",
        source_episode="episodes/2026-06-03.md",
        enabled=True,
    )

    assert stored == []


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_and_store_facts_update_reconcile_reindexes_affected_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "alice"
    record = FactRecord(
        text="Alice prefers LoCoMo reports.",
        source_entity="Alice",
        target_entity="LoCoMo",
        edge_type="PREFERS",
        recorded_at="2026-06-03T10:00:00+09:00",
    )
    updated = FactRecord.from_dict({**record.to_dict(), "text": "Alice prefers LoCoMo reports with score deltas."})
    affected_path = anima_dir / "facts" / "2026-06-03.jsonl"
    calls: dict[str, object] = {}

    async def fake_extract(*args, **kwargs):
        return [record]

    def fake_append(path: Path, records: list[FactRecord]):
        calls["append"] = (path, records)
        return []

    def fake_upsert(path: Path, records: list[FactRecord]) -> None:
        calls["upsert"] = (path, records)

    def fake_index(
        path: Path,
        records: list[FactRecord],
        *,
        origin: str,
        sync_entities: bool = True,
        entity_registry: dict[str, object] | None = None,
        entity_keys: set[str] | None = None,
        extra_paths: set[Path] | None = None,
    ) -> None:
        calls["index"] = (path, records, origin, sync_entities, entity_registry, entity_keys, extra_paths)

    monkeypatch.setattr(fact_extraction, "extract_fact_records", fake_extract)
    monkeypatch.setattr(fact_extraction, "append_fact_records", fake_append)
    monkeypatch.setattr(fact_extraction, "_upsert_fact_entities", fake_upsert)
    monkeypatch.setattr(fact_extraction, "_index_fact_records", fake_index)
    monkeypatch.setattr(
        fact_extraction,
        "reconcile_new_fact",
        lambda *_args, **_kwargs: ReconcileResult(
            action=ReconcileAction.UPDATE,
            fact=record,
            should_append=False,
            reason="complement",
            affected_fact_ids=(record.fact_id,),
            affected_paths=(affected_path,),
            updated_records=(updated,),
        ),
    )

    stored = await extract_and_store_facts(
        anima_dir,
        "Alice prefers LoCoMo reports.",
        source_episode="episodes/2026-06-03.md",
        origin="episode",
        enabled=True,
    )

    assert stored == []
    assert calls["append"] == (anima_dir, [])
    assert calls["upsert"] == (anima_dir, [updated])
    assert calls["index"] == (anima_dir, [], "episode", True, None, None, {affected_path})
