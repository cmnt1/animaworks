from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.config.models import ConsolidationConfig
from core.memory.maintenance.activity_compaction import (
    ActivityCompactionSettings,
    compact_activity_entries,
)
from core.memory.maintenance.consolidation import ConsolidationEngine


@dataclass
class FakeEntry:
    ts: str
    type: str
    tool: str = ""
    content: str = ""
    summary: str = ""
    ctx: str = ""
    meta: dict = field(default_factory=dict)
    from_person: str = ""
    to_person: str = ""
    channel: str = ""


def _entry(
    minute: int,
    event_type: str,
    *,
    task: str = "",
    second: int = 0,
    tool: str = "",
    content: str = "",
    summary: str = "",
    meta: dict | None = None,
) -> FakeEntry:
    context = f"cron:{task}" if task else ""
    return FakeEntry(
        ts=f"2026-10-02T08:{minute:02d}:{second:02d}+00:00",
        type=event_type,
        tool=tool,
        content=content,
        summary=summary,
        ctx=context,
        meta=meta or {},
    )


def _compact(
    entries: list[FakeEntry],
    *,
    min_runs: int = 6,
    max_notable_runs: int = 5,
    tool_use_max_bytes: int = 300,
    error_tail_bytes: int = 300,
):
    settings = ActivityCompactionSettings(
        profile="compact",
        cron_digest_min_runs=min_runs,
        cron_digest_max_notable_runs=max_notable_runs,
        tool_use_max_bytes=tool_use_max_bytes,
        error_tail_bytes=error_tail_bytes,
    )
    return compact_activity_entries(
        entries,
        settings=settings,
        format_full=lambda entry: ConsolidationEngine._format_entry_full(entry),
        format_tool_use=lambda entry: ConsolidationEngine._format_entry_full(
            entry,
            max_content_bytes=settings.tool_use_max_bytes,
        ),
    )


def _cron_entries(run_count: int, *, notable_runs: set[int] | None = None) -> list[FakeEntry]:
    notable_runs = notable_runs or set()
    entries: list[FakeEntry] = []
    for run in range(run_count):
        minute = run * 2
        entries.append(
            _entry(
                minute,
                "tool_use",
                task="poller",
                tool="Bash",
                content=f"command-{run}",
                meta={"tool_use_id": f"tool-{run}"},
            )
        )
        entries.append(
            _entry(
                minute,
                "tool_result",
                task="poller",
                second=5,
                tool="Bash",
                content=f"result-{run}",
                meta={
                    "tool_use_id": f"tool-{run}",
                    "is_error": run in notable_runs,
                    "result_bytes": len(f"result-{run}"),
                },
            )
        )
        entries.append(
            _entry(
                minute,
                "cron_executed",
                task="poller",
                second=10,
                summary=f"execution-{run}",
                meta={"task_name": "poller", "status": "completed"},
            )
        )
    return entries


def test_compact_cron_digest_keeps_first_last_and_earliest_notable_runs() -> None:
    entries = _cron_entries(6, notable_runs={2, 3, 4})

    lines, stats = _compact(entries, max_notable_runs=1)
    text = "\n".join(line for _, line in lines)

    assert stats.cron_digests == 1
    assert stats.cron_runs_folded == 3
    assert "[cron digest] poller: 6回実行（completed=6, failed=0）" in text
    assert "command-0" in text
    assert "command-2" in text
    assert "command-3" not in text
    assert "command-4" not in text
    assert "command-5" in text
    assert "result-2" in text
    assert "result-3" not in text
    assert "result-4" not in text
    assert text.index("[cron digest]") < text.index("command-0")


def test_compact_cron_digest_counts_failure_notifications_and_top_memory_paths() -> None:
    entries = _cron_entries(6)
    entries[2].meta["status"] = "failed"
    entries.extend(
        [
            _entry(
                3,
                "message_sent",
                task="poller",
                content="sent marker",
            ),
            _entry(
                5,
                "memory_write",
                task="poller",
                summary="knowledge/thermostat.md (overwrite)",
                meta={"path": "knowledge/thermostat.md"},
            ),
            _entry(
                7,
                "memory_write",
                task="poller",
                summary="knowledge/thermostat.md (overwrite)",
                meta={"path": "knowledge/thermostat.md"},
            ),
            _entry(
                9,
                "memory_write",
                task="poller",
                summary="state/cron_status.md (overwrite)",
                meta={"path": "state/cron_status.md"},
            ),
        ]
    )
    entries.sort(key=lambda entry: entry.ts)

    lines, _stats = _compact(entries, max_notable_runs=0)
    text = "\n".join(line for _, line in lines)

    assert "completed=5, failed=1" in text
    assert "送信/通知 1回" in text
    assert "memory_write 3回" in text
    assert "knowledge/thermostat.md×2" in text
    # The memory_write from an otherwise folded run remains in full.
    assert "MEM_WRITE" in text
    assert "knowledge/thermostat.md (overwrite)" in text
    assert "state/cron_status.md (overwrite)" in text


def test_cron_run_count_does_not_cross_calendar_days() -> None:
    entries = [
        FakeEntry(
            ts=f"{day}T08:{run * 2:02d}:00+00:00",
            type="cron_executed",
            meta={"task_name": "poller", "status": "completed"},
        )
        for day in ("2026-10-02", "2026-10-03")
        for run in range(3)
    ]

    lines, stats = _compact(entries)

    assert stats.cron_digests == 0
    assert sum("CRON:" in line for _, line in lines) == 6


def test_repeated_command_count_does_not_cross_calendar_days() -> None:
    entries = []
    for index, day in enumerate(("2026-10-02", "2026-10-02", "2026-10-03")):
        minute = index * 2
        ts = f"{day}T12:{minute:02d}:00+00:00"
        entries.extend(
            [
                FakeEntry(ts=ts, type="tool_use", tool="Bash", content="echo hello"),
                FakeEntry(
                    ts=f"{day}T12:{minute:02d}:10+00:00",
                    type="tool_result",
                    tool="Bash",
                    content=f"result-{index}",
                ),
            ]
        )

    lines, stats = _compact(entries)
    text = "\n".join(line for _, line in lines)

    assert stats.duplicate_commands_folded == 0
    assert "同一コマンド" not in text
    assert text.count("[tool_result Bash") == 3


def test_cron_below_digest_threshold_is_not_folded() -> None:
    entries = _cron_entries(5)

    lines, stats = _compact(entries)
    text = "\n".join(line for _, line in lines)

    assert stats.cron_digests == 0
    assert "[cron digest]" not in text
    assert text.count("CRON:") == 5
    assert all(f"command-{run}" in text for run in range(5))


def test_tool_results_become_one_line_and_failures_keep_the_tail() -> None:
    entries = [
        FakeEntry(
            ts="2026-10-02T12:00:00+00:00",
            type="tool_result",
            tool="Bash",
            content="prefix-error-tail",
            meta={"is_error": True, "result_bytes": 1000},
        ),
        FakeEntry(
            ts="2026-10-02T12:01:00+00:00",
            type="tool_result",
            tool="Read",
            content="large success output",
            meta={"is_error": False, "result_bytes": 19},
        ),
    ]

    lines, stats = _compact(entries, error_tail_bytes=4)
    text = "\n".join(line for _, line in lines)

    assert stats.tool_results_one_lined == 2
    assert "[tool_result Bash exit=fail bytes=1000] error_tail: tail" in text
    assert "[tool_result Read exit=ok bytes=19]" in text
    assert "large success output" not in text
    assert "prefix-error-tail" not in text
    assert len(text.splitlines()) == 2


def test_tool_use_body_is_truncated_to_configured_utf8_byte_limit() -> None:
    entries = [
        FakeEntry(
            ts="2026-10-02T12:00:00+00:00",
            type="tool_use",
            tool="Bash",
            content="日本語" * 30,
        )
    ]

    lines, _stats = _compact(entries, tool_use_max_bytes=24)
    text = lines[0][1]
    body = "\n".join(line[2:] for line in text.split(":\n", maxsplit=1)[1].splitlines())

    assert len(body.encode("utf-8")) <= 24
    assert "truncated" in body
    assert "日本語" * 30 not in text


def test_repeated_command_folding_removes_middle_tool_results() -> None:
    entries: list[FakeEntry] = []
    for index, command in enumerate(("echo   hello", "echo hello", "echo\nhello")):
        minute = index * 2
        tool_id = f"call-{index}"
        entries.extend(
            [
                FakeEntry(
                    ts=f"2026-10-02T12:{minute:02d}:00+00:00",
                    type="tool_use",
                    tool="Bash",
                    content=command,
                    meta={"tool_use_id": tool_id},
                ),
                FakeEntry(
                    ts=f"2026-10-02T12:{minute:02d}:10+00:00",
                    type="tool_result",
                    tool="Bash",
                    content=f"result-{index}",
                    meta={"tool_use_id": tool_id, "result_bytes": 8},
                ),
            ]
        )

    lines, stats = _compact(entries)
    text = "\n".join(line for _, line in lines)

    assert stats.duplicate_commands_folded == 1
    assert "（同一コマンド ×1 回、結果は省略）" in text
    assert "result-0" not in text
    assert "result-1" not in text
    assert "result-2" not in text
    assert text.count("[tool_result Bash") == 2
    assert text.count("TOOL_USE:Bash") == 2


def test_protected_activity_types_remain_full() -> None:
    protected = [
        ("message_sent", "sent-full"),
        ("message_received", "received-full"),
        ("response_sent", "response-full"),
        ("human_notify", "notify-full"),
        ("heartbeat_reflection", "reflection-full"),
        ("memory_write", "memory-full"),
        ("error", "error-full"),
        ("task_exec_end", "task-end-full"),
        ("task_updated", "task-completed-full"),
    ]
    entries = [
        FakeEntry(
            ts=f"2026-10-02T13:{index:02d}:00+00:00",
            type=event_type,
            content=body,
            meta={"status": "completed"} if event_type == "task_updated" else {},
        )
        for index, (event_type, body) in enumerate(protected)
    ]

    lines, _stats = _compact(entries, tool_use_max_bytes=1, error_tail_bytes=1)
    text = "\n".join(line for _, line in lines)

    for _event_type, body in protected:
        assert body in text


def test_full_profile_matches_legacy_formatter_and_chunking(tmp_path: Path) -> None:
    entries = [
        FakeEntry(
            ts="2026-03-29T14:30:00+00:00",
            type="tool_result",
            tool="github",
            content='{"ok": true, "details": "preserve this"}',
            meta={"result_status": "ok"},
        ),
        FakeEntry(
            ts="2026-03-29T14:31:00+00:00",
            type="response_sent",
            content="keep this message",
        ),
    ]
    engine = ConsolidationEngine(tmp_path / "anima", "test")
    budget = 50_000
    entry_content_bytes = min(64 * 1024, max(256, 200 * 1024 // 2))
    expected_entries = [
        (
            entry.ts[:13],
            ConsolidationEngine._format_entry_full(entry, max_content_bytes=entry_content_bytes),
        )
        for entry in entries
    ]
    expected = ConsolidationEngine._split_into_chunks(expected_entries, budget)
    activity = MagicMock()
    activity.recent.return_value = entries
    fixed_now = datetime(2026, 3, 29, 15, 0, 0, tzinfo=UTC)

    with (
        patch("core.memory.maintenance.consolidation.ConsolidationEngine.compute_activity_budget", return_value=budget),
        patch("core.activity.logger.ActivityLogger", return_value=activity),
        patch("core.memory.maintenance.consolidation.now_local", return_value=fixed_now),
    ):
        actual = engine.collect_activity_chunks(
            hours=24,
            model="test-model",
            compaction_settings=ActivityCompactionSettings(profile="full"),
        )

    assert actual == expected


def test_consolidation_config_defaults_to_compact_profile_and_reduced_output() -> None:
    config = ConsolidationConfig()

    assert config.episode_summary_input_profile == "compact"
    assert config.episode_summary_cron_digest_min_runs == 6
    assert config.episode_summary_cron_digest_max_notable_runs == 5
    assert config.episode_summary_tool_use_max_bytes == 300
    assert config.episode_summary_error_tail_bytes == 300
    assert config.episode_summary_max_output_tokens == 4096


def test_compact_v2_cuts_only_bash_tool_use_bodies() -> None:
    bash = FakeEntry(ts="2026-10-02T12:00:00+00:00", type="tool_use", tool="Bash")
    other = FakeEntry(ts="2026-10-02T12:00:00+00:00", type="tool_use", tool="mcp__aw__send_message")
    v2 = ActivityCompactionSettings(profile="compact_v2", tool_use_max_bytes=300, bash_tool_use_max_bytes=120)
    v1 = ActivityCompactionSettings(profile="compact", tool_use_max_bytes=300, bash_tool_use_max_bytes=120)

    assert v2.tool_use_bytes_for(bash) == 120
    assert v2.tool_use_bytes_for(other) == 300
    assert v1.tool_use_bytes_for(bash) == 300
    assert ActivityCompactionSettings.from_config(ConsolidationConfig()).bash_tool_use_max_bytes == 120
