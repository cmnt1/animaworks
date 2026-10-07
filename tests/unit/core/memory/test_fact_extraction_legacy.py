from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.memory.facts import extraction as fact_extraction
from core.memory.facts.config import DEFAULT_FACT_EXTRACTION_TIMEOUT_SECONDS
from core.memory.facts.extraction import (
    DEFAULT_FACT_CONFIDENCE,
    _resolve_extraction_config,
    extract_and_store_facts_with_outcome,
    extract_fact_records_with_outcome,
    format_turns_for_fact_extraction,
    records_from_extraction,
)
from core.memory.facts.observability import reset_warning_rate_limits
from core.memory.facts.ontology import ExtractedEntity, ExtractedFact
from core.memory.facts.store import FactRecord


@pytest.mark.unit
def test_single_call_extraction_config_defaults_enabled() -> None:
    from core.config.schemas import RAGConfig

    assert RAGConfig().facts_extraction_single_call is True
    assert RAGConfig(facts_extraction_single_call=False).facts_extraction_single_call is False


class FakeExtractor:
    def __init__(self) -> None:
        self.entity_calls = 0
        self.fact_calls = 0

    async def extract_entities(self, content: str):
        self.entity_calls += 1
        assert "LoCoMo" in content
        return [
            ExtractedEntity(name="Alice", entity_type="Person", summary="Test user"),
            ExtractedEntity(name="LoCoMo", entity_type="Concept", summary="Memory benchmark"),
        ]

    async def extract_facts(self, content: str, entities, *, reference_time: str | None = None):
        self.fact_calls += 1
        assert reference_time == "2026-06-03T10:00:00+09:00"
        return [
            ExtractedFact(
                source_entity="Alice",
                target_entity="LoCoMo",
                fact="Alice is evaluating LoCoMo memory scores.",
                valid_at=reference_time,
                edge_type="EVALUATES",
            )
        ]


@pytest.mark.unit
def test_records_from_extraction_maps_entities_and_source() -> None:
    records = records_from_extraction(
        [ExtractedEntity(name="Alice"), ExtractedEntity(name="LoCoMo")],
        [
            ExtractedFact(
                source_entity="Alice",
                target_entity="LoCoMo",
                fact="Alice is evaluating LoCoMo.",
                valid_at="2026-06-03T10:00:00+09:00",
                edge_type="EVALUATES",
            )
        ],
        source_episode="episodes/2026-06-03.md",
        source_session_id="session-1",
        recorded_at="2026-06-03T10:01:00+09:00",
    )

    assert len(records) == 1
    assert records[0].source_episode == "episodes/2026-06-03.md"
    assert records[0].source_session_id == "session-1"
    assert records[0].entities == ["Alice", "LoCoMo"]
    assert records[0].edge_type == "EVALUATES"
    assert records[0].confidence == DEFAULT_FACT_CONFIDENCE


@pytest.mark.unit
def test_format_turns_for_fact_extraction_includes_timestamp_and_role() -> None:
    turns = [
        SimpleNamespace(role="user", content="Alice mentioned LoCoMo.", timestamp="2026-06-03T10:00:00+09:00"),
        SimpleNamespace(role="assistant", content="", timestamp="2026-06-03T10:01:00+09:00"),
        SimpleNamespace(role="assistant", content="Noted.", timestamp=""),
    ]

    assert format_turns_for_fact_extraction(turns) == (
        "[2026-06-03T10:00:00+09:00] user: Alice mentioned LoCoMo.\nassistant: Noted."
    )


@pytest.mark.unit
def test_resolve_extraction_config_ignores_status_endpoint_fields(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    (anima_dir / "status.json").write_text(
        json.dumps(
            {
                "extraction_model": "local-safe-model",
                "extraction_timeout": 7,
                "extraction_api_base": "https://attacker.example",
                "extraction_api_key": "secret",
                "extraction_extra_body": {"stream": True},
            }
        ),
        encoding="utf-8",
    )

    model, llm_extra, _locale, timeout, credential = _resolve_extraction_config(anima_dir)

    assert model == "local-safe-model"
    assert timeout == 7
    assert llm_extra == {}
    assert credential == ""


@pytest.mark.unit
def test_resolve_extraction_config_ignores_background_model_and_handles_invalid_status(tmp_path: Path) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    (anima_dir / "status.json").write_text(
        json.dumps(
            {
                "background_model": "background-safe-model",
                "background_credential": "background-cred",
                "extraction_timeout": 11,
            }
        ),
        encoding="utf-8",
    )

    model, llm_extra, locale, timeout, credential = _resolve_extraction_config(anima_dir)

    assert model == "claude-sonnet-5-5"
    assert llm_extra == {}
    assert locale
    assert timeout == 11
    assert credential == "anthropic"

    (anima_dir / "status.json").write_text("{invalid json", encoding="utf-8")
    fallback_model, fallback_extra, fallback_locale, fallback_timeout, fallback_credential = _resolve_extraction_config(
        anima_dir
    )

    assert fallback_model
    assert fallback_extra == {}
    assert fallback_locale
    assert fallback_timeout == DEFAULT_FACT_EXTRACTION_TIMEOUT_SECONDS
    assert isinstance(fallback_credential, str)


@pytest.mark.unit
def test_resolve_extraction_config_defaults_to_consolidation_llm(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = SimpleNamespace(
        locale="ja",
        rag=SimpleNamespace(fact_extraction_timeout_seconds=75),
        consolidation=SimpleNamespace(llm_model="openai/deepseek-v4-flash", llm_credential="vllm-lb"),
        anima_defaults=SimpleNamespace(
            background_model=None,
            model="claude-sonnet-4-6",
            background_credential=None,
            credential="anthropic",
        ),
    )
    monkeypatch.setattr("core.config.load_config", lambda: cfg)

    model, llm_extra, locale, timeout, credential = _resolve_extraction_config(tmp_path / "alice")

    assert model == "openai/deepseek-v4-flash"
    assert llm_extra == {}
    assert locale == "ja"
    assert timeout == 75
    assert credential == "vllm-lb"


@pytest.mark.unit
def test_resolve_extraction_config_ignores_background_model_and_uses_legacy_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    (anima_dir / "status.json").write_text(
        json.dumps({"background_model": "codex/gpt-5.5"}),
        encoding="utf-8",
    )
    cfg = SimpleNamespace(
        locale="ja",
        consolidation=SimpleNamespace(llm_model="openai/deepseek-v4-flash", llm_credential="vllm-lb"),
        anima_defaults=SimpleNamespace(
            background_model=None,
            model="claude-sonnet-4-6",
            background_credential=None,
            credential="anthropic",
        ),
    )
    monkeypatch.setattr("core.config.load_config", lambda: cfg)

    model, _llm_extra, _locale, _timeout, credential = _resolve_extraction_config(anima_dir)

    assert model == "openai/deepseek-v4-flash"
    assert credential == "vllm-lb"


@pytest.mark.unit
def test_resolve_extraction_config_bare_status_model_uses_consolidation_credential(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "alice"
    anima_dir.mkdir()
    (anima_dir / "status.json").write_text(
        json.dumps({"extraction_model": "deepseek-v4-flash"}),
        encoding="utf-8",
    )
    cfg = SimpleNamespace(
        locale="ja",
        consolidation=SimpleNamespace(llm_model="openai/deepseek-v4-flash", llm_credential="vllm-lb"),
        anima_defaults=SimpleNamespace(
            background_model=None,
            model="claude-sonnet-4-6",
            background_credential=None,
            credential="anthropic",
        ),
    )
    monkeypatch.setattr("core.config.load_config", lambda: cfg)

    model, _llm_extra, _locale, _timeout, credential = _resolve_extraction_config(anima_dir)

    assert model == "deepseek-v4-flash"
    assert credential == "vllm-lb"


@pytest.mark.unit
def test_facts_extraction_enabled_returns_boolean() -> None:
    assert isinstance(fact_extraction._facts_extraction_enabled(), bool)


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_and_store_facts_with_outcome_appends_and_indexes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = FactRecord(
        text="Alice tracks LoCoMo memory scores.",
        source_entity="Alice",
        target_entity="LoCoMo",
        edge_type="TRACKS",
        recorded_at="2026-06-03T10:00:00+09:00",
    )
    calls: dict[str, object] = {}

    async def fake_extract(*args, **kwargs):
        calls["extract_args"] = args
        calls["extract_kwargs"] = kwargs
        return fact_extraction.FactExtractionOutcome([record])

    def fake_append(anima_dir: Path, records: list[FactRecord]):
        calls["append"] = (anima_dir, records)
        return records

    def fake_upsert(anima_dir: Path, records: list[FactRecord]) -> None:
        calls["upsert"] = (anima_dir, records)

    def fake_index(
        anima_dir: Path,
        records: list[FactRecord],
        *,
        origin: str,
        sync_entities: bool = True,
        entity_registry: dict[str, object] | None = None,
        entity_keys: set[str] | None = None,
        extra_paths: set[Path] | None = None,
    ) -> None:
        calls["index"] = (anima_dir, records, origin, sync_entities, entity_registry, entity_keys, extra_paths)

    monkeypatch.setattr(fact_extraction, "extract_fact_records_with_outcome", fake_extract)
    monkeypatch.setattr(fact_extraction, "append_fact_records", fake_append)
    monkeypatch.setattr(fact_extraction, "_upsert_fact_entities", fake_upsert)
    monkeypatch.setattr(fact_extraction, "_index_fact_records", fake_index)
    monkeypatch.setattr(fact_extraction, "_facts_reconcile_enabled", lambda: False)

    outcome = await extract_and_store_facts_with_outcome(
        tmp_path / "alice",
        "Alice tracks LoCoMo memory scores.",
        source_episode="episodes/2026-06-03.md",
        source_session_id="session-1",
        reference_time="2026-06-03T10:00:00+09:00",
        origin="episode",
        enabled=True,
    )

    assert outcome.records == [record]
    assert calls["append"] == (tmp_path / "alice", [record])
    assert calls["upsert"] == (tmp_path / "alice", [record])
    assert calls["index"] == (tmp_path / "alice", [record], "episode", True, None, None, set())
    assert calls["extract_kwargs"]["source_session_id"] == "session-1"


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_and_store_facts_with_outcome_skips_registry_when_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = FactRecord(
        text="Alice tracks LoCoMo memory scores.",
        source_entity="Alice",
        target_entity="LoCoMo",
        edge_type="TRACKS",
        recorded_at="2026-06-03T10:00:00+09:00",
    )
    calls: dict[str, object] = {}

    async def fake_extract(*args, **kwargs):
        return fact_extraction.FactExtractionOutcome([record])

    def fake_append(anima_dir: Path, records: list[FactRecord]):
        return records

    def fail_upsert(anima_dir: Path, records: list[FactRecord]) -> None:
        raise AssertionError("registry upsert should be disabled")

    def fake_index(
        anima_dir: Path,
        records: list[FactRecord],
        *,
        origin: str,
        sync_entities: bool = True,
        entity_registry: dict[str, object] | None = None,
        entity_keys: set[str] | None = None,
        extra_paths: set[Path] | None = None,
    ) -> None:
        calls["index"] = (anima_dir, records, origin, sync_entities, entity_registry, entity_keys, extra_paths)

    monkeypatch.setattr(fact_extraction, "extract_fact_records_with_outcome", fake_extract)
    monkeypatch.setattr(fact_extraction, "append_fact_records", fake_append)
    monkeypatch.setattr(fact_extraction, "_entity_registry_enabled", lambda: False)
    monkeypatch.setattr(fact_extraction, "_upsert_fact_entities", fail_upsert)
    monkeypatch.setattr(fact_extraction, "_index_fact_records", fake_index)
    monkeypatch.setattr(fact_extraction, "_facts_reconcile_enabled", lambda: False)

    outcome = await extract_and_store_facts_with_outcome(
        tmp_path / "alice",
        "Alice tracks LoCoMo memory scores.",
        source_episode="episodes/2026-06-03.md",
        origin="episode",
        enabled=True,
    )

    assert outcome.records == [record]
    assert calls["index"] == (tmp_path / "alice", [record], "episode", False, None, None, set())


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_and_store_facts_with_outcome_append_failure_is_non_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    record = FactRecord(
        text="Alice tracks LoCoMo memory scores.",
        source_entity="Alice",
        target_entity="LoCoMo",
        edge_type="TRACKS",
        recorded_at="2026-06-03T10:00:00+09:00",
    )

    async def fake_extract(*args, **kwargs):
        return fact_extraction.FactExtractionOutcome([record])

    def fake_append(anima_dir: Path, records: list[FactRecord]):
        raise OSError("write failed")

    monkeypatch.setattr(fact_extraction, "extract_fact_records_with_outcome", fake_extract)
    monkeypatch.setattr(fact_extraction, "append_fact_records", fake_append)
    monkeypatch.setattr(fact_extraction, "_facts_reconcile_enabled", lambda: False)

    outcome = await extract_and_store_facts_with_outcome(
        tmp_path / "alice",
        "Alice tracks LoCoMo memory scores.",
        source_episode="episodes/2026-06-03.md",
        enabled=True,
    )
    assert outcome.records == []
    assert outcome.failed is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_fact_records_uses_single_call_extractor_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.memory.facts.extractor import FactExtractor

    monkeypatch.setattr(
        "core.config.load_config",
        lambda: SimpleNamespace(rag=SimpleNamespace(facts_extraction_single_call=True)),
    )
    completion = AsyncMock(
        return_value=json.dumps(
            {
                "entities": [
                    {"name": "Alice", "entity_type": "Person"},
                    {"name": "LoCoMo", "entity_type": "Concept"},
                ],
                "facts": [
                    {
                        "source_entity": "Alice",
                        "target_entity": "LoCoMo",
                        "fact": "Alice evaluates LoCoMo.",
                        "valid_at": "2026-06-03T10:00:00+09:00",
                    }
                ],
            }
        )
    )
    monkeypatch.setattr("core.llm.oneshot.one_shot_completion", completion)
    extractor = FactExtractor(model="test-model", max_retries=1)

    outcome = await extract_fact_records_with_outcome(
        tmp_path / "alice",
        "Alice evaluates LoCoMo.",
        source_episode="episodes/2026-06-03.md",
        reference_time="2026-06-03T10:00:00+09:00",
        extractor=extractor,
        enabled=True,
    )

    assert len(outcome.records) == 1
    assert completion.await_count == 1
    assert outcome.extract_llm_calls == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_fact_records_config_can_restore_two_stage_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.memory.facts.extractor import FactExtractor

    monkeypatch.setattr(
        "core.config.load_config",
        lambda: SimpleNamespace(rag=SimpleNamespace(facts_extraction_single_call=False)),
    )
    completion = AsyncMock(
        side_effect=[
            json.dumps(
                {
                    "entities": [
                        {"name": "Alice", "entity_type": "Person"},
                        {"name": "LoCoMo", "entity_type": "Concept"},
                    ]
                }
            ),
            json.dumps(
                {
                    "facts": [
                        {
                            "source_entity": "Alice",
                            "target_entity": "LoCoMo",
                            "fact": "Alice evaluates LoCoMo.",
                        }
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr("core.llm.oneshot.one_shot_completion", completion)
    extractor = FactExtractor(model="test-model", max_retries=1)

    outcome = await extract_fact_records_with_outcome(
        tmp_path / "alice",
        "Alice evaluates LoCoMo.",
        source_episode="episodes/2026-06-03.md",
        reference_time="2026-06-03T10:00:00+09:00",
        extractor=extractor,
        enabled=True,
    )

    assert len(outcome.records) == 1
    assert completion.await_count == 2
    assert outcome.extract_llm_calls == 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_fact_records_failure_warns_once_per_window(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    reset_warning_rate_limits()

    class RaisingExtractor:
        async def extract_entities(self, content: str):
            raise RuntimeError("extractor failed")

    with caplog.at_level("WARNING", logger="animaworks.memory.fact_extraction"):
        first = await extract_fact_records_with_outcome(
            tmp_path / "alice",
            "Alice discusses LoCoMo score improvements.",
            source_episode="episodes/2026-06-03.md",
            extractor=RaisingExtractor(),
            enabled=True,
        )
        second = await extract_fact_records_with_outcome(
            tmp_path / "alice",
            "Alice discusses LoCoMo score improvements.",
            source_episode="episodes/2026-06-03.md",
            extractor=RaisingExtractor(),
            enabled=True,
        )

    assert first.failed is True
    assert first.facts_failed == 1
    assert second.failed is True
    records = [record for record in caplog.records if record.message == "Atomic fact extraction failed"]
    assert len(records) == 1
    assert records[0].exc_info


@pytest.mark.asyncio
@pytest.mark.unit
async def test_extract_and_store_facts_with_outcome_reports_index_failure(
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
        return fact_extraction.FactExtractionOutcome([record])

    def fake_append(anima_dir: Path, records: list[FactRecord]):
        return records

    monkeypatch.setattr(fact_extraction, "extract_fact_records_with_outcome", fake_extract)
    monkeypatch.setattr(fact_extraction, "append_fact_records", fake_append)
    monkeypatch.setattr(fact_extraction, "_facts_reconcile_enabled", lambda: False)
    monkeypatch.setattr(fact_extraction, "_entity_registry_enabled", lambda: False)
    monkeypatch.setattr(fact_extraction, "_index_fact_records", lambda *args, **kwargs: False)

    outcome = await extract_and_store_facts_with_outcome(
        tmp_path / "alice",
        "Alice tracks LoCoMo memory scores.",
        source_episode="episodes/2026-06-03.md",
        enabled=True,
    )

    assert outcome.records == [record]
    assert outcome.facts_extracted == 1
    assert outcome.facts_failed == 1
    assert outcome.failure_stage == "index"


@pytest.mark.unit
def test_index_fact_records_indexes_each_fact_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    record = FactRecord(
        text="Alice tracks LoCoMo memory scores.",
        source_entity="Alice",
        target_entity="LoCoMo",
        edge_type="TRACKS",
        recorded_at="2026-06-03T10:00:00+09:00",
    )
    calls: list[tuple[Path, str, bool, str]] = []

    class FakeRag:
        def index_file(self, path: Path, memory_type: str, *, force: bool = False, origin: str) -> None:
            calls.append((path, memory_type, force, origin))

    class FakeMemoryManager:
        def __init__(self, anima_dir: Path) -> None:
            self.anima_dir = anima_dir
            self._rag = FakeRag()

    monkeypatch.setattr("core.memory.manager.MemoryManager", FakeMemoryManager)

    fact_extraction._index_fact_records(tmp_path / "alice", [], origin="conversation")
    fact_extraction._index_fact_records(tmp_path / "alice", [record], origin="episode")

    assert calls == [(tmp_path / "alice" / "facts" / "2026-06-03.jsonl", "facts", True, "episode")]
