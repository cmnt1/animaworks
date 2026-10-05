from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.activity.logger import ActivityLogger
from core.memory.facts.extraction import FactExtractionOutcome
from core.memory.facts.live import (
    LiveFactRunResult,
    _LiveFactCoordinator,
    _LiveFactOptions,
    build_live_fact_input,
    resolve_live_fact_model_and_credential,
    run_live_fact_extraction,
    schedule_live_fact_extraction,
)
from core.time_utils import now_local


def _live_options(
    *,
    enabled: bool = True,
    min_input_chars: int = 0,
    max_input_chars: int = 24_000,
    debounce_seconds: int = 0,
    model: str = "openai/live-model",
    credential: str = "live-key",
) -> _LiveFactOptions:
    return _LiveFactOptions(
        enabled=enabled,
        model=model,
        credential=credential,
        min_input_chars=min_input_chars,
        max_input_chars=max_input_chars,
        debounce_seconds=debounce_seconds,
    )


def _range() -> tuple[object, object]:
    return now_local() - timedelta(minutes=1), now_local() + timedelta(seconds=1)


@pytest.mark.unit
def test_live_fact_configuration_defaults() -> None:
    from core.config.schemas import ConsolidationConfig

    config = ConsolidationConfig()

    assert config.live_fact_extraction_enabled is True
    assert config.live_fact_model is None
    assert config.live_fact_credential is None
    assert config.live_fact_min_input_chars == 200
    assert config.live_fact_max_input_chars == 24_000
    assert config.live_fact_debounce_seconds == 120


@pytest.mark.unit
def test_live_fact_input_keeps_only_conversation_and_summary_entries(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    activity = ActivityLogger(anima_dir)
    activity.log(
        "message_received",
        content="Human request: prepare the report.",
        from_person="owner",
        channel="chat",
        meta={"from_type": "human"},
    )
    activity.log("response_sent", content="I will prepare it by Friday.", to_person="owner", channel="chat")
    activity.log("human_notify", content="The report is ready.", via="configured_channels")
    activity.log(
        "task_exec_end",
        content="Completed the report and saved it.",
        summary="Report task completed",
        meta={"task_id": "task-1", "title": "Prepare report", "status": "completed"},
    )
    activity.log("memory_write", content="must not leak file contents", summary="knowledge/report.md (overwrite)")
    activity.log("tool_use", content="EXCLUDED TOOL INPUT", summary="EXCLUDED TOOL SUMMARY")
    activity.log("tool_result", content="EXCLUDED TOOL RESULT")
    activity.log("cron_executed", content="EXCLUDED CRON OUTPUT", summary="EXCLUDED CRON")
    activity.log("heartbeat_end", content="EXCLUDED HEARTBEAT", summary="EXCLUDED HEARTBEAT")

    since, until = _range()
    result = build_live_fact_input(anima_dir, since, until)

    assert result.qualifies is True
    assert "Human request: prepare the report." in result.text
    assert "I will prepare it by Friday." in result.text
    assert "The report is ready." in result.text
    assert "Completed the report and saved it." in result.text
    assert "knowledge/report.md (overwrite)" in result.text
    assert "must not leak file contents" not in result.text
    for excluded in ("EXCLUDED TOOL", "EXCLUDED CRON", "EXCLUDED HEARTBEAT"):
        assert excluded not in result.text


@pytest.mark.unit
def test_live_fact_input_truncates_each_entry_and_preserves_newest_within_total_limit(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    activity = ActivityLogger(anima_dir)
    activity.log(
        "message_received",
        content="old-entry " + "o" * 500,
        from_person="owner",
        channel="chat",
        meta={"from_type": "human"},
    )
    activity.log("response_sent", content="new-entry " + "n" * 5_000, to_person="owner", channel="chat")
    since, until = _range()

    per_entry = build_live_fact_input(anima_dir, since, until, max_input_chars=5_000)
    response_line = next(line for line in per_entry.text.splitlines() if "response_sent" in line)
    assert len(response_line.split(": ", 1)[1]) == 2_000

    aggregate = build_live_fact_input(anima_dir, since, until, max_input_chars=500)
    assert len(aggregate.text) <= 500
    assert "new-entry" in aggregate.text
    assert "old-entry" not in aggregate.text


@pytest.mark.unit
def test_live_fact_input_requires_human_or_anima_interaction_to_qualify(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    activity = ActivityLogger(anima_dir)
    activity.log(
        "message_received",
        content="automated system message",
        from_person="scheduler",
        channel="inbox",
        meta={"from_type": "cron"},
    )
    activity.log("memory_write", summary="knowledge/only-write.md (overwrite)")
    since, until = _range()

    result = build_live_fact_input(anima_dir, since, until)

    assert result.text
    assert result.qualifies is False

    activity.log(
        "message_received",
        content="Another anima sent a durable decision.",
        from_person="bob",
        channel="inbox",
        meta={"from_type": "anima"},
        origin="anima",
    )
    result = build_live_fact_input(anima_dir, since, now_local() + timedelta(seconds=1))
    assert result.qualifies is True


@pytest.mark.asyncio
@pytest.mark.unit
async def test_live_extraction_skips_llm_for_unqualified_or_short_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anima_dir = tmp_path / "animas" / "alice"
    activity = ActivityLogger(anima_dir)
    since, _until = _range()
    engine = MagicMock()
    engine.extract_facts_from_text_outcome = AsyncMock(return_value=FactExtractionOutcome([]))
    monkeypatch.setattr("core.memory.facts.live._load_options", lambda: _live_options(min_input_chars=200))
    monkeypatch.setattr("core.memory.facts.live._make_fact_extractor", MagicMock())
    monkeypatch.setattr("core.memory.maintenance.consolidation.ConsolidationEngine", MagicMock(return_value=engine))

    activity.log("memory_write", summary="knowledge/no-chat.md (overwrite)")
    no_qualifying = await run_live_fact_extraction(
        anima_dir,
        trigger="chat",
        session_started_at=since,
        until=now_local() + timedelta(seconds=1),
    )
    assert no_qualifying.skipped_reason == "no_qualifying_entry"

    second_dir = tmp_path / "animas" / "bob"
    ActivityLogger(second_dir).log(
        "message_received",
        content="short",
        from_person="owner",
        channel="chat",
        meta={"from_type": "human"},
    )
    too_short = await run_live_fact_extraction(
        second_dir,
        trigger="chat",
        session_started_at=since,
        until=now_local() + timedelta(seconds=1),
    )
    assert too_short.skipped_reason == "input_too_short"
    engine.extract_facts_from_text_outcome.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_checkpoint_advances_atomically_and_next_run_reads_only_new_activity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.memory.facts.store import FactRecord

    anima_dir = tmp_path / "animas" / "alice"
    activity = ActivityLogger(anima_dir)
    first_timestamp = now_local().replace(microsecond=0)
    second_timestamp = first_timestamp + timedelta(seconds=5)
    with patch(
        "core.activity.logger.now_iso",
        return_value=first_timestamp.isoformat(),
    ):
        first_entry = activity.log(
            "message_received",
            content="first durable request with enough text to preserve.",
            from_person="owner",
            channel="chat",
            meta={"from_type": "human"},
        )
    session_start = first_timestamp - timedelta(minutes=1)
    engine = MagicMock()
    engine.extract_facts_from_text_outcome = AsyncMock(
        side_effect=[FactExtractionOutcome([FactRecord(text="first fact")]), FactExtractionOutcome([])]
    )
    monkeypatch.setattr("core.memory.facts.live._load_options", lambda: _live_options())
    monkeypatch.setattr("core.memory.facts.live._make_fact_extractor", lambda *_args: object())
    monkeypatch.setattr("core.memory.maintenance.consolidation.ConsolidationEngine", MagicMock(return_value=engine))

    from core.memory.facts.live import atomic_write_json as real_atomic_write_json

    with patch("core.memory.facts.live.atomic_write_json", wraps=real_atomic_write_json) as atomic_write:
        first_until = first_timestamp
        first = await run_live_fact_extraction(
            anima_dir,
            trigger="chat",
            session_started_at=session_start,
            until=first_until,
        )
        checkpoint = json.loads((anima_dir / "state" / "live_fact_checkpoint.json").read_text(encoding="utf-8"))
        assert checkpoint == {"last_until": first_until.isoformat()}

        with patch("core.activity.logger.now_iso", return_value=second_timestamp.isoformat()):
            activity.log(
                "message_received",
                content="second independent decision arrives later.",
                from_person="owner",
                channel="chat",
                meta={"from_type": "human"},
            )
        second_until = second_timestamp
        second = await run_live_fact_extraction(
            anima_dir,
            trigger="chat",
            session_started_at=session_start,
            until=second_until,
        )

    assert first.facts_extracted == 1
    assert second.since == first_until
    first_call, second_call = engine.extract_facts_from_text_outcome.call_args_list
    assert first_call.kwargs["source_episode"] == f"activity_log/{first_until.date().isoformat()}.jsonl"
    assert first_call.kwargs["source_session_id"] == f"live:chat:{first_until.isoformat()}"
    assert first_call.kwargs["origin"] == "live"
    assert "first durable request" not in second_call.args[0]
    assert "second independent decision" in second_call.args[0]
    assert atomic_write.call_count == 2
    assert not list((anima_dir / "state").glob(".live_fact_checkpoint.json.*.tmp"))
    assert first_entry.ts <= first_until.isoformat()


@pytest.mark.asyncio
@pytest.mark.unit
async def test_live_model_resolution_order_and_agent_sdk_fallback_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.memory.facts.extractor import FactExtractor

    configured = SimpleNamespace(
        live_fact_model="provider/live",
        live_fact_credential="live-credential",
        fact_reconcile_model="provider/reconcile",
        fact_reconcile_credential="reconcile-credential",
        llm_model="provider/daily",
        llm_credential="daily-credential",
    )
    assert resolve_live_fact_model_and_credential(configured) == ("provider/live", "live-credential")
    configured.live_fact_model = None
    configured.live_fact_credential = None
    assert resolve_live_fact_model_and_credential(configured) == ("provider/reconcile", "reconcile-credential")
    configured.fact_reconcile_model = None
    configured.fact_reconcile_credential = None
    assert resolve_live_fact_model_and_credential(configured) == ("provider/daily", "daily-credential")

    completion = AsyncMock(return_value="ok")
    monkeypatch.setattr("core.llm.oneshot.one_shot_completion", completion)
    extractor = FactExtractor(model="provider/live", credential="live-credential")
    assert await extractor._call_llm("system", "prompt") == "ok"
    assert completion.call_args.kwargs["model"] == "provider/live"
    assert completion.call_args.kwargs["credential"] == "live-credential"
    assert completion.call_args.kwargs["allow_agent_sdk_fallback"] is False


@pytest.mark.asyncio
@pytest.mark.unit
async def test_live_fact_coordinator_coalesces_triggers_until_debounce_quiets() -> None:
    first_trigger_at = now_local()
    sleeper_entered = asyncio.Event()
    release_sleeper = asyncio.Event()
    sleep_calls = 0
    calls: list[tuple[str, object]] = []

    async def sleeper(_seconds: float) -> None:
        nonlocal sleep_calls
        sleep_calls += 1
        sleeper_entered.set()
        await release_sleeper.wait()

    async def runner(_anima_dir: Path, *, trigger: str, session_started_at):
        calls.append((trigger, session_started_at))
        return LiveFactRunResult(trigger=trigger, since=session_started_at, until=now_local())

    coordinator = _LiveFactCoordinator(Path("alice"), runner=runner, sleeper=sleeper)
    coordinator.schedule("chat", first_trigger_at, 120)
    await sleeper_entered.wait()
    coordinator.schedule("inbox", first_trigger_at + timedelta(seconds=10), 120)
    release_sleeper.set()
    assert coordinator._task is not None
    await coordinator._task

    assert calls == [("inbox", first_trigger_at)]
    assert sleep_calls == 2


@pytest.mark.asyncio
@pytest.mark.unit
async def test_live_fact_coordinator_serializes_runs_for_one_anima() -> None:
    now = now_local()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    calls: list[str] = []
    active = 0
    max_active = 0

    async def runner(_anima_dir: Path, *, trigger: str, session_started_at):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        calls.append(trigger)
        if len(calls) == 1:
            first_started.set()
            await release_first.wait()
        active -= 1
        return LiveFactRunResult(trigger=trigger, since=session_started_at, until=now)

    async def gated_sleep(_seconds: float) -> None:
        await asyncio.sleep(0)

    coordinator = _LiveFactCoordinator(Path("alice"), runner=runner, sleeper=gated_sleep)
    coordinator.schedule("chat", now, 0)
    await first_started.wait()

    # A trigger during an active extraction is queued for a second run, never
    # started concurrently with the first one.
    coordinator.schedule("task", now + timedelta(seconds=1), 0)
    await asyncio.sleep(0)
    assert calls == ["chat"]

    release_first.set()
    assert coordinator._task is not None
    await coordinator._task

    assert calls == ["chat", "task"]
    assert max_active == 1


@pytest.mark.asyncio
@pytest.mark.unit
async def test_live_fact_scheduler_rejects_disabled_consolidation_heartbeat_and_cron(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    options = _live_options(enabled=False)
    monkeypatch.setattr("core.memory.facts.live._load_options", lambda: options)
    anima_dir = tmp_path / "animas" / "alice"

    assert not schedule_live_fact_extraction(anima_dir, trigger="chat")

    options = _live_options(enabled=True)
    monkeypatch.setattr("core.memory.facts.live._load_options", lambda: options)
    (anima_dir / "state").mkdir(parents=True)
    (anima_dir / "state" / ".consolidation_mode").write_text("1", encoding="utf-8")
    assert not schedule_live_fact_extraction(anima_dir, trigger="inbox")
    (anima_dir / "state" / ".consolidation_mode").unlink()

    assert not schedule_live_fact_extraction(anima_dir, trigger="heartbeat")
    assert not schedule_live_fact_extraction(anima_dir, trigger="cron:daily")
