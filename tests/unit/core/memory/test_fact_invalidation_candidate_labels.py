from __future__ import annotations

from pathlib import Path

import pytest

from core.memory.facts import invalidation as fact_invalidation_module
from core.memory.facts.invalidation import (
    FactCandidate,
    ReconcileAction,
    ReconcileConfig,
    reconcile_new_fact,
)
from core.memory.facts.store import FactRecord, append_fact_records, fact_file_for_record, read_fact_records
from core.memory.rag.store import Document, SearchResult


def _store(anima_dir: Path, record: FactRecord) -> Path:
    append_fact_records(anima_dir, [record])
    return fact_file_for_record(anima_dir, record)


def _candidate(record: FactRecord, path: Path, score: float = 0.95) -> FactCandidate:
    return FactCandidate(record=record, score=score, path=path, doc_id=f"doc-{record.fact_id}")


@pytest.mark.unit
def test_reconcile_only_invalidates_candidates_labeled_contradict(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    contradictory = FactRecord(text="Alice's LoCoMo score is 70.", recorded_at="2026-06-03T09:00:00+09:00")
    duplicate = FactRecord(text="Alice's LoCoMo score is 85.", recorded_at="2026-06-02T09:10:00+09:00")
    unrelated = FactRecord(text="Alice uses rubric A.", recorded_at="2026-06-03T09:20:00+09:00")
    path = _store(anima_dir, contradictory)
    duplicate_path = _store(anima_dir, duplicate)
    _store(anima_dir, unrelated)
    new = FactRecord(
        text="Alice's LoCoMo score is 85.",
        recorded_at="2026-06-03T12:05:00+09:00",
    )
    labels = {
        contradictory.fact_id: "CONTRADICT",
        duplicate.fact_id: "DUPLICATE",
        unrelated.fact_id: "ADD",
    }

    result = reconcile_new_fact(
        anima_dir,
        new,
        classifier=lambda _new, candidates, _dir: labels[candidates[0].record.fact_id],
        candidate_search=lambda *_args: [
            _candidate(contradictory, path, 0.98),
            _candidate(duplicate, path, 0.97),
            _candidate(unrelated, path, 0.96),
        ],
        config=ReconcileConfig(enabled=True),
    )

    stored = {record.fact_id: record for record in read_fact_records(path, include_expired=True)}
    duplicate_records = read_fact_records(duplicate_path, include_expired=True)
    assert result.action == ReconcileAction.INVALIDATE_OLD
    assert result.appended_records == ()
    assert {record.fact_id for record in result.updated_records} == {contradictory.fact_id}
    assert stored[contradictory.fact_id].valid_until == "2026-06-03T12:05:00+09:00"
    assert stored[unrelated.fact_id].valid_until == ""
    assert [record.fact_id for record in duplicate_records] == [duplicate.fact_id]
    assert new.fact_id not in stored


@pytest.mark.unit
def test_default_reconcile_batches_three_candidate_labels_in_one_call(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    old_a = FactRecord(text="Alice's score was 70.", recorded_at="2026-06-03T09:00:00+09:00")
    old_b = FactRecord(text="Alice uses rubric B.", recorded_at="2026-06-03T09:05:00+09:00")
    old_c = FactRecord(text="Alice tracks rubric C.", recorded_at="2026-06-03T09:10:00+09:00")
    path = _store(anima_dir, old_a)
    _store(anima_dir, old_b)
    _store(anima_dir, old_c)
    new = FactRecord(text="Alice's score is 85.", recorded_at="2026-06-03T12:05:00+09:00")
    calls: list[list[str]] = []

    def batch_classify(_new, candidates, _dir):
        calls.append([candidate.record.fact_id for candidate in candidates])
        return {
            old_a.fact_id: "CONTRADICT",
            old_b.fact_id: "ADD",
            old_c.fact_id: "ADD",
        }

    result = reconcile_new_fact(
        anima_dir,
        new,
        candidate_search=lambda *_args: [
            _candidate(old_a, path, 0.98),
            _candidate(old_b, path, 0.97),
            _candidate(old_c, path, 0.96),
        ],
        config=ReconcileConfig(enabled=True),
        batch_classifier=batch_classify,
    )

    stored = {record.fact_id: record for record in read_fact_records(path, include_expired=True)}
    assert calls == [[old_a.fact_id, old_b.fact_id, old_c.fact_id]]
    assert result.action == ReconcileAction.INVALIDATE_OLD
    assert {record.fact_id for record in result.updated_records} == {old_a.fact_id}
    assert stored[old_a.fact_id].valid_until == "2026-06-03T12:05:00+09:00"
    assert stored[old_b.fact_id].valid_until == ""
    assert result.reconcile_llm_calls == 1


@pytest.mark.unit
def test_batched_reconcile_missing_label_falls_back_to_add(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    old_a = FactRecord(text="Alice tracks LoCoMo scores.", recorded_at="2026-06-03T09:00:00+09:00")
    old_b = FactRecord(text="Alice uses rubric A.", recorded_at="2026-06-03T09:05:00+09:00")
    path = _store(anima_dir, old_a)
    _store(anima_dir, old_b)
    new = FactRecord(text="Alice tracks new score deltas.", recorded_at="2026-06-03T10:00:00+09:00")

    result = reconcile_new_fact(
        anima_dir,
        new,
        candidate_search=lambda *_args: [_candidate(old_a, path), _candidate(old_b, path, 0.94)],
        config=ReconcileConfig(enabled=True),
        batch_classifier=lambda *_args: {old_a.fact_id: "ADD"},
    )

    assert result.action == ReconcileAction.ADD
    assert result.should_append is True
    assert result.reason == "invalid_label"
    assert result.reconcile_llm_calls == 1


@pytest.mark.unit
def test_batched_reconcile_does_not_send_dedup_key_matches_to_classifier(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    duplicate = FactRecord(
        text="Alice owns Project X.",
        source_entity="Alice",
        target_entity="Project X",
        fact_id="old-duplicate",
        recorded_at="2026-06-03T09:00:00+09:00",
    )
    new = FactRecord(
        text="Alice owns Project X.",
        source_entity="Alice",
        target_entity="Project X",
        fact_id="new-fact",
        recorded_at="2026-06-03T10:00:00+09:00",
    )
    other_a = FactRecord(text="Alice uses rubric A.", recorded_at="2026-06-03T09:05:00+09:00")
    other_b = FactRecord(text="Alice tracks metric B.", recorded_at="2026-06-03T09:10:00+09:00")
    path = _store(anima_dir, duplicate)
    _store(anima_dir, other_a)
    _store(anima_dir, other_b)
    calls: list[list[str]] = []

    def batch_classify(_new, candidates, _dir):
        calls.append([candidate.record.fact_id for candidate in candidates])
        return {candidate.record.fact_id: "ADD" for candidate in candidates}

    result = reconcile_new_fact(
        anima_dir,
        new,
        candidate_search=lambda *_args: [
            _candidate(duplicate, path, 0.99),
            _candidate(other_a, path, 0.98),
            _candidate(other_b, path, 0.97),
        ],
        config=ReconcileConfig(enabled=True),
        batch_classifier=batch_classify,
    )

    assert calls == [[other_a.fact_id, other_b.fact_id]]
    assert result.action == ReconcileAction.SKIP
    assert result.reconcile_llm_calls == 1


@pytest.mark.unit
def test_reconcile_duplicate_does_not_mark_path_for_reindex(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    old = FactRecord(text="Alice tracks LoCoMo memory scores.", recorded_at="2026-06-03T09:00:00+09:00")
    path = _store(anima_dir, old)
    new = FactRecord(text="Alice tracks LoCoMo memory scores.", recorded_at="2026-06-03T10:00:00+09:00")

    result = reconcile_new_fact(
        anima_dir,
        new,
        classifier=lambda *_args: "DUPLICATE",
        candidate_search=lambda *_args: [_candidate(old, path)],
        config=ReconcileConfig(enabled=True),
    )

    assert result.action == ReconcileAction.SKIP
    assert result.affected_fact_ids == (old.fact_id,)
    assert result.affected_paths == ()


@pytest.mark.unit
def test_vector_candidate_search_keeps_same_id_duplicate_and_uses_source_file_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "alice"
    old = FactRecord(text="Alice tracks LoCoMo scores.", recorded_at="2026-06-03T09:00:00+09:00")
    path = _store(anima_dir, old)
    new = FactRecord(text="Alice tracks LoCoMo scores.", recorded_at="2026-06-03T10:00:00+09:00")

    class FakeVectorStore:
        def query(self, *, collection, embedding, top_k):
            assert collection == "alice_facts"
            return [
                SearchResult(
                    Document(
                        id="old",
                        content="",
                        metadata={
                            "fact_id": old.fact_id,
                            "source_file": str(path.relative_to(anima_dir)),
                        },
                    ),
                    0.97,
                )
            ]

    monkeypatch.setattr("core.memory.rag.vector_registry.get_vector_store", lambda anima_name: FakeVectorStore())
    monkeypatch.setattr("core.memory.rag.embedding.generate_embeddings", lambda texts, **_kwargs: [[0.1, 0.2]])
    monkeypatch.setattr(
        fact_invalidation_module,
        "find_fact_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fallback scan should not run")),
    )

    candidates = fact_invalidation_module._search_fact_candidates(anima_dir, new, 5)

    assert len(candidates) == 1
    assert candidates[0].record.fact_id == old.fact_id
    assert candidates[0].record.fact_id == new.fact_id
    assert candidates[0].path == path


@pytest.mark.unit
def test_same_id_vector_duplicate_skips_append_without_llm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "alice"
    duplicate = FactRecord(text="Alice's LoCoMo score is 85.", recorded_at="2026-06-02T09:10:00+09:00")
    contradiction = FactRecord(text="Alice's LoCoMo score is 70.", recorded_at="2026-06-03T09:00:00+09:00")
    duplicate_path = _store(anima_dir, duplicate)
    contradiction_path = _store(anima_dir, contradiction)
    new = FactRecord(text="Alice's LoCoMo score is 85.", recorded_at="2026-06-03T12:05:00+09:00")

    class FakeVectorStore:
        def query(self, *, collection, embedding, top_k):
            return [
                SearchResult(
                    Document(
                        id="duplicate",
                        content="",
                        metadata={
                            "fact_id": duplicate.fact_id,
                            "source_file": str(duplicate_path.relative_to(anima_dir)),
                        },
                    ),
                    0.99,
                ),
                SearchResult(
                    Document(
                        id="contradiction",
                        content="",
                        metadata={
                            "fact_id": contradiction.fact_id,
                            "source_file": str(contradiction_path.relative_to(anima_dir)),
                        },
                    ),
                    0.98,
                ),
            ]

    def classify(_new: FactRecord, candidates: list[FactCandidate], _dir: Path) -> str:
        assert candidates[0].record.fact_id == contradiction.fact_id
        return "CONTRADICT"

    monkeypatch.setattr("core.memory.rag.vector_registry.get_vector_store", lambda anima_name: FakeVectorStore())
    monkeypatch.setattr("core.memory.rag.embedding.generate_embeddings", lambda texts, **_kwargs: [[0.1, 0.2]])

    result = reconcile_new_fact(
        anima_dir,
        new,
        classifier=classify,
        config=ReconcileConfig(enabled=True),
    )

    duplicate_records = read_fact_records(duplicate_path, include_expired=True)
    contradiction_records = read_fact_records(contradiction_path, include_expired=True)
    assert result.action == ReconcileAction.INVALIDATE_OLD
    assert result.appended_records == ()
    assert duplicate_records == [duplicate]
    assert contradiction_records[0].valid_until == "2026-06-03T12:05:00+09:00"
    assert len(contradiction_records) == 1
