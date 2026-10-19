"""Tests for suppressing repeated command-cron LLM follow-ups."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.runtime import cron_followup
from core.runtime.cron_followup import command_followup_output, should_suppress_cron_followup
from core.runtime.scheduler_manager import SchedulerManager
from core.runtime.task_runner import execute_cron_contract
from core.schemas import CronTask, CycleResult


def _make_command_task(
    name: str = "monitor",
    *,
    skip_pattern: str | None = None,
    trigger_heartbeat: bool = True,
) -> CronTask:
    return CronTask(
        name=name,
        schedule="*/10 * * * *",
        type="command",
        command="echo hi",
        skip_pattern=skip_pattern,
        trigger_heartbeat=trigger_heartbeat,
    )


def _command_result(*, exit_code: int = 0, stdout: str = "", stderr: str = "") -> dict:
    return {"task": "monitor", "exit_code": exit_code, "stdout": stdout, "stderr": stderr, "duration_ms": 100}


def _state(anima_dir: Path) -> dict:
    path = anima_dir / "state" / "cron_followup_fingerprints.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _patch_suppress_hours(monkeypatch: pytest.MonkeyPatch, hours: float) -> None:
    monkeypatch.setattr(
        cron_followup,
        "load_config",
        lambda: SimpleNamespace(heartbeat=SimpleNamespace(cron_followup_repeat_suppress_hours=hours)),
    )


# ── Fingerprint decision helper ─────────────────────────────


class TestFingerprintSuppression:
    def test_same_output_is_suppressed_within_window(self, tmp_path: Path) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        output = "disk usage normal"

        assert not should_suppress_cron_followup(tmp_path, "monitor", output, suppress_hours=6, now=now)
        assert should_suppress_cron_followup(
            tmp_path, "monitor", output, suppress_hours=6, now=now + timedelta(minutes=10)
        )

        entry = _state(tmp_path)["monitor"]
        assert entry["sha256"] == hashlib.sha256(output.encode("utf-8")).hexdigest()
        assert entry["first_seen"] == now.isoformat()
        assert entry["last_followup_at"] == now.isoformat()
        assert entry["suppressed"] == 1

    def test_suppressed_counter_accumulates(self, tmp_path: Path) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        should_suppress_cron_followup(tmp_path, "monitor", "same", suppress_hours=6, now=now)
        for minute in (5, 10, 15):
            assert should_suppress_cron_followup(
                tmp_path, "monitor", "same", suppress_hours=6, now=now + timedelta(minutes=minute)
            )
        assert _state(tmp_path)["monitor"]["suppressed"] == 3

    def test_changed_output_follows_up_immediately(self, tmp_path: Path) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        assert not should_suppress_cron_followup(tmp_path, "monitor", "first", suppress_hours=6, now=now)
        assert not should_suppress_cron_followup(
            tmp_path, "monitor", "second", suppress_hours=6, now=now + timedelta(minutes=10)
        )

        entry = _state(tmp_path)["monitor"]
        assert entry["sha256"] == hashlib.sha256(b"second").hexdigest()
        assert entry["first_seen"] == (now + timedelta(minutes=10)).isoformat()
        assert entry["suppressed"] == 0

    def test_follows_up_once_after_suppression_window(self, tmp_path: Path) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        output = "same error"
        assert not should_suppress_cron_followup(tmp_path, "monitor", output, suppress_hours=6, now=now)
        assert should_suppress_cron_followup(
            tmp_path, "monitor", output, suppress_hours=6, now=now + timedelta(hours=1)
        )

        reminder_at = now + timedelta(hours=7)
        assert not should_suppress_cron_followup(tmp_path, "monitor", output, suppress_hours=6, now=reminder_at)
        entry = _state(tmp_path)["monitor"]
        assert entry["last_followup_at"] == reminder_at.isoformat()
        assert entry["suppressed"] == 1
        assert should_suppress_cron_followup(
            tmp_path, "monitor", output, suppress_hours=6, now=reminder_at + timedelta(minutes=30)
        )

    def test_zero_hours_disables_suppression(self, tmp_path: Path) -> None:
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        assert not should_suppress_cron_followup(tmp_path, "monitor", "same", suppress_hours=0, now=now)
        assert not should_suppress_cron_followup(
            tmp_path, "monitor", "same", suppress_hours=0, now=now + timedelta(minutes=1)
        )
        assert _state(tmp_path)["monitor"]["suppressed"] == 0

    def test_default_window_reads_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_suppress_hours(monkeypatch, 6.0)
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        assert not should_suppress_cron_followup(tmp_path, "monitor", "same", now=now)
        assert should_suppress_cron_followup(tmp_path, "monitor", "same", now=now + timedelta(hours=1))

    def test_config_zero_disables_suppression(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_suppress_hours(monkeypatch, 0.0)
        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        assert not should_suppress_cron_followup(tmp_path, "monitor", "same", now=now)
        assert not should_suppress_cron_followup(tmp_path, "monitor", "same", now=now + timedelta(minutes=1))

    def test_nonzero_exit_and_stderr_are_suppressed(self, tmp_path: Path) -> None:
        task = _make_command_task()
        result = _command_result(exit_code=2, stderr="sensor failed")
        output = command_followup_output(task, result)
        assert output is not None and "sensor failed" in output

        now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        assert not should_suppress_cron_followup(tmp_path, task.name, output, suppress_hours=6, now=now)
        assert should_suppress_cron_followup(
            tmp_path, task.name, output, suppress_hours=6, now=now + timedelta(minutes=10)
        )

    def test_corrupt_state_file_starts_fresh(self, tmp_path: Path) -> None:
        state_path = tmp_path / "state" / "cron_followup_fingerprints.json"
        state_path.parent.mkdir(parents=True)
        state_path.write_text("{not json", encoding="utf-8")

        assert not should_suppress_cron_followup(tmp_path, "monitor", "same", suppress_hours=6)
        assert _state(tmp_path)["monitor"]["sha256"] == hashlib.sha256(b"same").hexdigest()


# ── Legacy scheduler path ───────────────────────────────────


def _make_scheduler_mgr(tmp_path: Path) -> SchedulerManager:
    anima = MagicMock()
    anima.memory = MagicMock()
    anima.shared_dir = tmp_path / "shared"
    anima.shared_dir.mkdir()
    anima.run_cron_command = AsyncMock(return_value=_command_result(stdout="same output"))
    anima_dir = tmp_path / "animas" / "test"
    anima_dir.mkdir(parents=True)
    mgr = SchedulerManager(anima=anima, anima_name="test", anima_dir=anima_dir, emit_event=MagicMock())
    mgr._task_runner_supervisor.run_cron_followup = AsyncMock(
        return_value={"result": {"action": "completed", "summary": "reviewed"}, "success": True}
    )
    return mgr


class TestLegacySchedulerPath:
    @pytest.mark.asyncio
    async def test_second_identical_output_skips_followup(self, tmp_path: Path) -> None:
        mgr = _make_scheduler_mgr(tmp_path)
        task = _make_command_task()

        await mgr._run_cron_task(task)
        await mgr._run_cron_task(task)

        mgr._task_runner_supervisor.run_cron_followup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_changed_output_runs_followup_again(self, tmp_path: Path) -> None:
        mgr = _make_scheduler_mgr(tmp_path)
        task = _make_command_task()

        await mgr._run_cron_task(task)
        mgr._anima.run_cron_command.return_value = _command_result(stdout="different output")
        await mgr._run_cron_task(task)

        assert mgr._task_runner_supervisor.run_cron_followup.await_count == 2


# ── Isolated task-runner path ──────────────────────────────


class TestIsolatedTaskRunnerPath:
    @pytest.mark.asyncio
    async def test_second_identical_output_skips_followup(self, tmp_path: Path) -> None:
        anima = MagicMock()
        anima.anima_dir = tmp_path
        anima.run_cron_command = AsyncMock(return_value=_command_result(stdout="same output"))
        anima.run_cron_task = AsyncMock(
            return_value=CycleResult(trigger="cron", action="completed", summary="reviewed")
        )
        task = _make_command_task()

        await execute_cron_contract(anima, task)
        await execute_cron_contract(anima, task)

        anima.run_cron_task.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_changed_output_runs_followup_again(self, tmp_path: Path) -> None:
        anima = MagicMock()
        anima.anima_dir = tmp_path
        anima.run_cron_command = AsyncMock(return_value=_command_result(stdout="first"))
        anima.run_cron_task = AsyncMock(
            return_value=CycleResult(trigger="cron", action="completed", summary="reviewed")
        )
        task = _make_command_task()

        await execute_cron_contract(anima, task)
        anima.run_cron_command.return_value = _command_result(stdout="second")
        await execute_cron_contract(anima, task)

        assert anima.run_cron_task.await_count == 2
