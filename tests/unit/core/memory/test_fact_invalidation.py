from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from core.memory.facts import invalidation as fact_invalidation_module
from core.memory.facts import invalidation_llm as fact_invalidation_llm
from core.memory.facts.config import DEFAULT_FACT_EXTRACTION_TIMEOUT_SECONDS
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
def test_reconcile_below_similarity_threshold_adds_without_llm(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    old = FactRecord(text="Alice uses LoCoMo rubric A.", recorded_at="2026-06-03T09:00:00+09:00")
    path = _store(anima_dir, old)
    new = FactRecord(text="Alice uses LoCoMo rubric B.", recorded_at="2026-06-03T10:00:00+09:00")

    def fail_classifier(*args, **kwargs):
        raise AssertionError("LLM classifier should not be called below threshold")

    result = reconcile_new_fact(
        anima_dir,
        new,
        classifier=fail_classifier,
        candidate_search=lambda *_args: [_candidate(old, path, score=0.3)],
        config=ReconcileConfig(enabled=True, threshold=0.82, top_k=5),
    )

    assert result.action == ReconcileAction.ADD
    assert result.should_append is True
    assert result.reason == "below_similarity_threshold"
    assert read_fact_records(path, include_expired=True)[0].valid_until == ""


@pytest.mark.unit
def test_reconcile_search_or_llm_failure_falls_back_to_add(tmp_path: Path) -> None:
    new = FactRecord(text="Alice prefers LoCoMo score deltas.", recorded_at="2026-06-03T10:00:00+09:00")

    search_failed = reconcile_new_fact(
        tmp_path / "alice",
        new,
        candidate_search=lambda *_args: (_ for _ in ()).throw(RuntimeError("chroma down")),
        config=ReconcileConfig(enabled=True),
    )
    assert search_failed.action == ReconcileAction.ADD
    assert search_failed.should_append is True
    assert search_failed.error == "chroma down"

    old = FactRecord(text="Alice prefers LoCoMo score summaries.", recorded_at="2026-06-03T09:00:00+09:00")
    anima_dir = tmp_path / "bob"
    path = _store(anima_dir, old)
    llm_failed = reconcile_new_fact(
        anima_dir,
        new,
        classifier=lambda *_args: (_ for _ in ()).throw(RuntimeError("llm down")),
        candidate_search=lambda *_args: [_candidate(old, path)],
        config=ReconcileConfig(enabled=True),
    )
    assert llm_failed.action == ReconcileAction.ADD
    assert llm_failed.should_append is True
    assert llm_failed.error == "llm down"


@pytest.mark.unit
def test_reconcile_invalid_label_adds(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    old = FactRecord(text="Alice prefers concise reports.", recorded_at="2026-06-03T09:00:00+09:00")
    path = _store(anima_dir, old)
    new = FactRecord(text="Alice prefers detailed reports.", recorded_at="2026-06-03T10:00:00+09:00")

    result = reconcile_new_fact(
        anima_dir,
        new,
        classifier=lambda *_args: "UNKNOWN",
        candidate_search=lambda *_args: [_candidate(old, path)],
        config=ReconcileConfig(enabled=True),
    )

    assert result.action == ReconcileAction.ADD
    assert result.should_append is True
    assert result.reason == "invalid_label"


@pytest.mark.unit
def test_reconcile_empty_disabled_no_candidates_and_classified_add(tmp_path: Path) -> None:
    empty = reconcile_new_fact(
        tmp_path / "alice",
        FactRecord(text=""),
        config=ReconcileConfig(enabled=True),
    )
    assert empty.action == ReconcileAction.SKIP
    assert empty.reason == "empty_fact"

    fact = FactRecord(text="Alice tracks LoCoMo.", recorded_at="2026-06-03T10:00:00+09:00")
    disabled = reconcile_new_fact(tmp_path / "alice", fact, config=ReconcileConfig(enabled=False))
    assert disabled.action == ReconcileAction.ADD
    assert disabled.reason == "disabled"

    no_candidates = reconcile_new_fact(
        tmp_path / "alice",
        fact,
        candidate_search=lambda *_args: [],
        config=ReconcileConfig(enabled=True),
    )
    assert no_candidates.action == ReconcileAction.ADD
    assert no_candidates.reason == "no_candidates"

    old = FactRecord(text="Alice tracks LoCoMo scores.", recorded_at="2026-06-03T09:00:00+09:00")
    path = _store(tmp_path / "alice", old)
    classified_add = reconcile_new_fact(
        tmp_path / "alice",
        fact,
        classifier=lambda *_args: "ADD",
        candidate_search=lambda *_args: [_candidate(old, path)],
        config=ReconcileConfig(enabled=True),
    )
    assert classified_add.action == ReconcileAction.ADD
    assert classified_add.reason == "classified_add"


@pytest.mark.unit
def test_reconcile_duplicate_skips_new_fact(tmp_path: Path) -> None:
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
    assert result.should_append is False
    assert result.affected_fact_ids == (old.fact_id,)


@pytest.mark.unit
def test_reconcile_contradiction_invalidates_all_candidates_and_appends_new(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    old_a = FactRecord(text="Alice's LoCoMo score is 70.", recorded_at="2026-06-03T09:00:00+09:00")
    old_b = FactRecord(
        text="Alice still uses the old LoCoMo score.",
        recorded_at="2026-06-03T09:05:00+09:00",
        valid_until="2026-12-31T00:00:00+09:00",
    )
    path_a = _store(anima_dir, old_a)
    path_b = _store(anima_dir, old_b)
    new = FactRecord(
        text="Alice's LoCoMo score is 85.",
        valid_at="2026-06-03T12:00:00+09:00",
        recorded_at="2026-06-03T12:05:00+09:00",
    )

    result = reconcile_new_fact(
        anima_dir,
        new,
        classifier=lambda *_args: "CONTRADICT",
        candidate_search=lambda *_args: [_candidate(old_a, path_a), _candidate(old_b, path_b, score=0.91)],
        config=ReconcileConfig(enabled=True, threshold=0.82, top_k=5),
    )

    records = read_fact_records(path_a, include_expired=True)
    assert result.action == ReconcileAction.INVALIDATE_OLD
    assert result.should_append is False
    assert result.appended_records == (new,)
    assert {record.fact_id for record in result.updated_records} == {old_a.fact_id, old_b.fact_id}
    assert {record.valid_until for record in result.updated_records} == {"2026-06-03T12:00:00+09:00"}
    assert [record.text for record in records] == [old_a.text, old_b.text, new.text]


@pytest.mark.unit
def test_reconcile_contradiction_uses_recorded_at_without_valid_at(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    old = FactRecord(text="Alice uses rubric A.", recorded_at="2026-06-03T09:00:00+09:00")
    path = _store(anima_dir, old)
    new = FactRecord(text="Alice uses rubric B.", recorded_at="2026-06-03T10:00:00+09:00")

    result = reconcile_new_fact(
        anima_dir,
        new,
        classifier=lambda *_args: "CONTRADICT",
        candidate_search=lambda *_args: [_candidate(old, path)],
        config=ReconcileConfig(enabled=True),
    )

    assert result.action == ReconcileAction.INVALIDATE_OLD
    assert result.updated_records[0].valid_until == "2026-06-03T10:00:00+09:00"


@pytest.mark.unit
def test_reconcile_complement_updates_best_candidate_without_append(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    old_best = FactRecord(
        text="Alice prefers LoCoMo reports.",
        entities=["Alice", "LoCoMo"],
        confidence=0.5,
        recorded_at="2026-06-03T09:00:00+09:00",
    )
    old_other = FactRecord(text="Alice mentions LoCoMo.", recorded_at="2026-06-03T09:05:00+09:00")
    path_best = _store(anima_dir, old_best)
    path_other = _store(anima_dir, old_other)
    new = FactRecord(
        text="Alice prefers LoCoMo reports with score deltas.",
        entities=["Score Deltas"],
        confidence=0.9,
        recorded_at="2026-06-03T10:00:00+09:00",
    )

    result = reconcile_new_fact(
        anima_dir,
        new,
        classifier=lambda *_args: "COMPLEMENT",
        candidate_search=lambda *_args: [_candidate(old_best, path_best, 0.95), _candidate(old_other, path_other, 0.9)],
        config=ReconcileConfig(enabled=True),
    )

    stored_records = read_fact_records(path_best, include_expired=True)
    assert result.action == ReconcileAction.ADD
    assert result.should_append is True
    assert result.label == "COMPLEMENT"
    assert result.reason == "complement_kept_separate"
    assert result.affected_fact_ids == (old_best.fact_id,)
    assert stored_records[0].text == old_best.text
    assert stored_records[0].entities == old_best.entities


@pytest.mark.unit
def test_reconcile_ignores_candidate_expired_at_new_fact_time(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    old = FactRecord(
        text="Alice used an obsolete LoCoMo rubric.",
        recorded_at="2026-06-03T08:00:00+09:00",
        valid_until="2026-06-03T09:00:00+09:00",
    )
    path = _store(anima_dir, old)
    new = FactRecord(
        text="Alice uses the current LoCoMo rubric.",
        valid_at="2026-06-03T10:00:00+09:00",
        recorded_at="2026-06-03T10:01:00+09:00",
    )

    result = reconcile_new_fact(
        anima_dir,
        new,
        classifier=lambda *_args: (_ for _ in ()).throw(AssertionError("expired candidate should be ignored")),
        candidate_search=lambda *_args: [_candidate(old, path)],
        config=ReconcileConfig(enabled=True),
    )

    assert result.action == ReconcileAction.ADD
    assert result.reason == "no_active_candidates"


@pytest.mark.unit
def test_reconcile_invalidation_write_failure_skips_new_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "alice"
    old = FactRecord(text="Alice uses rubric A.", recorded_at="2026-06-03T09:00:00+09:00")
    path = _store(anima_dir, old)
    new = FactRecord(text="Alice uses rubric B.", recorded_at="2026-06-03T10:00:00+09:00")

    monkeypatch.setattr(
        "core.memory.facts.invalidation.update_fact_records_and_append",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("rewrite failed")),
    )

    result = reconcile_new_fact(
        anima_dir,
        new,
        classifier=lambda *_args: "CONTRADICT",
        candidate_search=lambda *_args: [_candidate(old, path)],
        config=ReconcileConfig(enabled=True),
    )

    assert result.action == ReconcileAction.SKIP
    assert result.should_append is False
    assert result.reason == "invalidate_failed"
    assert result.error == "rewrite failed"


@pytest.mark.unit
def test_reconcile_invalidation_append_failure_rolls_back_old_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "alice"
    old = FactRecord(text="Alice uses rubric A.", recorded_at="2026-06-03T09:00:00+09:00")
    path = _store(anima_dir, old)
    new = FactRecord(text="Alice uses rubric B.", recorded_at="2026-06-04T10:00:00+09:00")
    original_write = fact_invalidation_module.update_fact_records_and_append.__globals__["_write_fact_records_unlocked"]
    calls = {"count": 0}

    def fail_second_write(path_arg: Path, records: list[FactRecord]) -> None:
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("append write failed")
        original_write(path_arg, records)

    monkeypatch.setitem(
        fact_invalidation_module.update_fact_records_and_append.__globals__,
        "_write_fact_records_unlocked",
        fail_second_write,
    )

    result = reconcile_new_fact(
        anima_dir,
        new,
        classifier=lambda *_args: "CONTRADICT",
        candidate_search=lambda *_args: [_candidate(old, path)],
        config=ReconcileConfig(enabled=True),
    )

    assert result.action == ReconcileAction.SKIP
    assert result.should_append is False
    assert result.reason == "invalidate_failed"
    assert read_fact_records(path, include_expired=True)[0].valid_until == ""
    assert not fact_file_for_record(anima_dir, new).exists()


@pytest.mark.unit
def test_reconcile_invalidation_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "alice"
    old = FactRecord(text="Alice uses rubric A.", recorded_at="2026-06-03T09:00:00+09:00")
    path = _store(anima_dir, old)
    new = FactRecord(text="Alice uses rubric B.", recorded_at="2026-06-03T10:00:00+09:00")

    monkeypatch.setattr(
        "core.memory.facts.invalidation.update_fact_records_and_append", lambda *_args, **_kwargs: ([], [])
    )
    incomplete = reconcile_new_fact(
        anima_dir,
        new,
        classifier=lambda *_args: "CONTRADICT",
        candidate_search=lambda *_args: [_candidate(old, path)],
        config=ReconcileConfig(enabled=True),
    )
    assert incomplete.action == ReconcileAction.SKIP
    assert incomplete.reason == "invalidate_incomplete"


@pytest.mark.unit
def test_label_parser_is_strict() -> None:
    assert fact_invalidation_module._parse_label("CONTRADICT") == "CONTRADICT"
    assert fact_invalidation_module._parse_label("'ADD'") == "ADD"
    assert fact_invalidation_module._parse_label("not CONTRADICT, use ADD") == ""
    assert fact_invalidation_module._parse_label("Label: DUPLICATE") == ""


@pytest.mark.unit
def test_reconcile_config_and_vector_candidate_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rag = SimpleNamespace(
        facts_reconcile_enabled=True,
        facts_reconcile_similarity_threshold=2.0,
        facts_reconcile_top_k=0,
    )
    monkeypatch.setattr("core.config.load_config", lambda: SimpleNamespace(rag=rag))
    loaded = fact_invalidation_module._load_reconcile_config()
    assert loaded.enabled is True
    assert loaded.threshold == 1.0
    assert loaded.top_k == 1

    monkeypatch.setattr("core.config.load_config", lambda: (_ for _ in ()).throw(RuntimeError("config failed")))
    assert fact_invalidation_module._load_reconcile_config() == ReconcileConfig()

    anima_dir = tmp_path / "alice"
    old = FactRecord(text="Alice tracks LoCoMo scores.", recorded_at="2026-06-03T09:00:00+09:00")
    _store(anima_dir, old)
    new = FactRecord(text="Alice tracks LoCoMo deltas.", recorded_at="2026-06-03T10:00:00+09:00")

    class FakeVectorStore:
        def query(self, *, collection, embedding, top_k):
            assert collection == "alice_facts"
            assert embedding == [0.1, 0.2]
            assert top_k == 5
            return [
                SearchResult(Document(id="missing", content="", metadata={}), 0.99),
                SearchResult(Document(id="self", content="", metadata={"fact_id": new.fact_id}), 0.98),
                SearchResult(Document(id="old", content="", metadata={"fact_id": old.fact_id}), 0.97),
                SearchResult(Document(id="old-duplicate", content="", metadata={"fact_id": old.fact_id}), 0.96),
                SearchResult(Document(id="unknown", content="", metadata={"fact_id": "fact_unknown"}), 0.95),
            ]

    monkeypatch.setattr("core.memory.rag.vector_registry.get_vector_store", lambda anima_name: FakeVectorStore())
    monkeypatch.setattr("core.memory.rag.embedding.generate_embeddings", lambda texts, **_kwargs: [[0.1, 0.2]])

    candidates = fact_invalidation_module._search_fact_candidates(anima_dir, new, 5)

    assert len(candidates) == 1
    assert candidates[0].record.fact_id == old.fact_id
    assert candidates[0].doc_id == "old"


@pytest.mark.unit
def test_reconcile_uses_consolidation_model_and_credential_not_status_background_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    # A status.json background_model with no credential must not become the
    # independent first choice for fact reconciliation (T3).
    (anima_dir / "status.json").write_text(
        '{"background_model": "claude-opus-5-5"}',
        encoding="utf-8",
    )
    old = FactRecord(text="Alice's LoCoMo score is 70.", recorded_at="2026-06-03T09:00:00+09:00")
    new = FactRecord(text="Alice's LoCoMo score is 85.", recorded_at="2026-06-03T10:00:00+09:00")
    captured: dict[str, object] = {}

    def fake_completion(prompt: str, **kwargs):
        captured.update(kwargs)
        captured["prompt"] = prompt
        return "CONTRADICT"

    consolidation = SimpleNamespace(
        llm_model="openai/deepseek-v4-flash",
        llm_credential="gpu40-direct",
        fact_reconcile_model=None,
        fact_reconcile_credential=None,
    )
    rag = SimpleNamespace(fact_extraction_timeout_seconds=11, fact_extraction_max_tokens=8192)
    defs = SimpleNamespace(
        consolidation=consolidation,
        rag=rag,
        anima_defaults=SimpleNamespace(background_model="", model="", background_credential="", credential=""),
        locale="ja",
    )
    monkeypatch.setattr("core.config.load_config", lambda: defs)
    monkeypatch.setattr("core.llm.oneshot.one_shot_completion_sync", fake_completion)

    label = fact_invalidation_llm.classify_fact_relation(
        new,
        [FactCandidate(record=old, score=0.96, path=anima_dir / "facts" / "2026-06-03.jsonl")],
        anima_dir,
    )

    assert label == "CONTRADICT"
    assert captured["model"] == "openai/deepseek-v4-flash"
    assert captured["credential"] == "gpu40-direct"
    assert captured["timeout"] == 11
    assert captured["max_tokens"] == 16
    assert captured["temperature"] == 0.0
    assert captured["allow_agent_sdk_fallback"] is False
    assert "Return exactly one label" in captured["system_prompt"]
    assert "DUPLICATE" in captured["prompt"]
    assert old.fact_id in captured["prompt"]


@pytest.mark.unit
def test_default_batch_classifier_parses_labels_and_sizes_tokens(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "alice"
    old_a = FactRecord(text="Alice tracks score A.", recorded_at="2026-06-03T09:00:00+09:00")
    old_b = FactRecord(text="Alice tracks score B.", recorded_at="2026-06-03T09:05:00+09:00")
    new = FactRecord(text="Alice tracks score C.", recorded_at="2026-06-03T10:00:00+09:00")
    path = _store(anima_dir, old_a)
    _store(anima_dir, old_b)
    candidates = [
        FactCandidate(record=old_a, score=0.98, path=path),
        FactCandidate(record=old_b, score=0.97, path=path),
    ]
    captured: dict[str, object] = {}
    consolidation = SimpleNamespace(
        fact_reconcile_model="test-reconcile-model",
        fact_reconcile_credential="test-credential",
    )
    rag = SimpleNamespace(fact_extraction_timeout_seconds=11)
    monkeypatch.setattr(
        "core.config.load_config",
        lambda: SimpleNamespace(consolidation=consolidation, rag=rag),
    )

    def fake_completion(prompt: str, **kwargs):
        captured.update(kwargs)
        captured["prompt"] = prompt
        return f'```json\n{{"labels":{{"{old_a.fact_id}":"ADD","{old_b.fact_id}":"COMPLEMENT"}}}}\n```'

    monkeypatch.setattr("core.llm.oneshot.one_shot_completion_sync", fake_completion)
    result = reconcile_new_fact(
        anima_dir,
        new,
        candidate_search=lambda *_args: candidates,
        config=ReconcileConfig(enabled=True),
    )

    assert result.action == ReconcileAction.ADD
    assert result.reconcile_llm_calls == 1
    assert captured["max_tokens"] == 32 + 40 * 2
    assert captured["model"] == "test-reconcile-model"
    assert "- DUPLICATE: same meaning, no new durable information." in captured["prompt"]
    assert old_a.fact_id in captured["prompt"]
    assert captured["allow_agent_sdk_fallback"] is False


@pytest.mark.unit
def test_llm_helper_config_fallbacks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    consolidation = SimpleNamespace(
        llm_model="",
        llm_credential="",
        fact_reconcile_model=None,
        fact_reconcile_credential=None,
    )
    rag = SimpleNamespace(fact_extraction_timeout_seconds=5, fact_extraction_max_tokens=8192)
    defs = SimpleNamespace(
        consolidation=consolidation,
        rag=rag,
        anima_defaults=SimpleNamespace(
            background_model="", model="config-model", background_credential="", credential=""
        ),
        locale="ja",
    )
    monkeypatch.setattr("core.config.load_config", lambda: defs)
    resolved = fact_invalidation_llm._resolve_reconcile_llm_config(tmp_path / "alice")
    assert resolved[0] == "claude-sonnet-5-5"
    assert resolved[-1] == "anthropic"

    monkeypatch.setattr("core.config.load_config", lambda: (_ for _ in ()).throw(RuntimeError("config failed")))
    assert fact_invalidation_llm._resolve_reconcile_llm_config(tmp_path / "alice") == (
        "claude-sonnet-5-5",
        {},
        DEFAULT_FACT_EXTRACTION_TIMEOUT_SECONDS,
        "anthropic",
    )
