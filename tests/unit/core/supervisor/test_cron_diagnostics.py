"""Tests for cron registration-time diagnostics."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.runtime.cron_diagnostics import (
    COMMAND_WITHOUT_SKIP,
    HIGH_FREQUENCY_LLM,
    diagnose_cron_task,
    minimum_fire_interval_minutes,
)
from core.runtime.schedule_parser import parse_schedule
from core.runtime.scheduler_manager import SchedulerManager
from core.schemas import CronTask
from server.routes.system import _parse_cron_jobs


def _make_mgr(tmp_path: Path) -> SchedulerManager:
    anima = MagicMock()
    anima.memory.read_heartbeat_config.return_value = ""
    anima.memory.read_cron_config.return_value = ""
    mgr = SchedulerManager(anima=anima, anima_name="test_anima", anima_dir=tmp_path, emit_event=MagicMock())
    mgr.scheduler = MagicMock()
    return mgr


def _setup(mgr: SchedulerManager, cron_md: str) -> None:
    mgr._anima.memory.read_cron_config.return_value = cron_md
    mgr._setup_cron_tasks()


def _notif_files(tmp_path: Path) -> list[Path]:
    directory = tmp_path / "state" / "background_notifications"
    if not directory.exists():
        return []
    return sorted(directory.glob("cron_health_*.md"))


# ── Trigger interval helper ─────────────────────────────────


class TestMinimumFireInterval:
    def test_interval_expression(self) -> None:
        trigger = parse_schedule("*/15 * * * *")
        assert trigger is not None
        assert minimum_fire_interval_minutes(trigger) == 15.0

    def test_equivalent_list_expression(self) -> None:
        trigger = parse_schedule("0,15,30,45 * * * *")
        assert trigger is not None
        assert minimum_fire_interval_minutes(trigger) == 15.0

    def test_daily_interval(self) -> None:
        trigger = parse_schedule("0 9 * * *")
        assert trigger is not None
        assert minimum_fire_interval_minutes(trigger) == 1440.0


# ── Per-task diagnostics ────────────────────────────────────


class TestDiagnoseCronTask:
    def test_high_frequency_llm(self) -> None:
        trigger = parse_schedule("*/15 * * * *")
        assert trigger is not None
        task = CronTask(name="watch", schedule="*/15 * * * *", type="llm")
        assert diagnose_cron_task(task, trigger) == [HIGH_FREQUENCY_LLM]

    def test_command_without_skip_pattern(self) -> None:
        trigger = parse_schedule("*/10 * * * *")
        assert trigger is not None
        task = CronTask(name="watch", schedule="*/10 * * * *", type="command", command="echo hi")
        assert diagnose_cron_task(task, trigger) == [COMMAND_WITHOUT_SKIP]

    def test_command_trigger_heartbeat_false_is_healthy(self) -> None:
        trigger = parse_schedule("*/10 * * * *")
        assert trigger is not None
        task = CronTask(
            name="watch",
            schedule="*/10 * * * *",
            type="command",
            command="echo hi",
            trigger_heartbeat=False,
        )
        assert diagnose_cron_task(task, trigger) == []

    def test_command_with_skip_pattern_is_healthy(self) -> None:
        trigger = parse_schedule("*/10 * * * *")
        assert trigger is not None
        task = CronTask(
            name="watch",
            schedule="*/10 * * * *",
            type="command",
            command="echo hi",
            skip_pattern=r"^\[\s*\]$",
        )
        assert diagnose_cron_task(task, trigger) == []

    def test_daily_llm_is_healthy(self) -> None:
        trigger = parse_schedule("0 9 * * *")
        assert trigger is not None
        task = CronTask(name="daily", schedule="0 9 * * *", type="llm")
        assert diagnose_cron_task(task, trigger) == []


# ── Notification integration ────────────────────────────────


class TestSetupCronDiagnostics:
    def test_high_frequency_llm_notified(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        _setup(mgr, "## Fast\nschedule: */15 * * * *\ntype: llm\nCheck for new items\n")

        files = _notif_files(tmp_path)
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "Fast" in content
        assert "skip_pattern" in content
        assert (tmp_path / "state" / "cron_health_digest.sha256").is_file()

    def test_command_without_skip_notified(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        _setup(mgr, "## Watch\nschedule: */10 * * * *\ntype: command\ncommand: echo hi\n")

        files = _notif_files(tmp_path)
        assert len(files) == 1
        content = files[0].read_text(encoding="utf-8")
        assert "Watch" in content
        assert "trigger_heartbeat: false" in content

    def test_command_without_skip_and_trigger_heartbeat_false_is_quiet(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        _setup(
            mgr,
            "## Watch\nschedule: */10 * * * *\ntype: command\ncommand: echo hi\ntrigger_heartbeat: false\n",
        )

        assert _notif_files(tmp_path) == []

    def test_daily_llm_is_quiet(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        _setup(mgr, "## Daily\nschedule: 0 9 * * *\ntype: llm\nSummarize\n")

        assert _notif_files(tmp_path) == []

    def test_high_frequency_task_is_still_registered(self, tmp_path: Path) -> None:
        mgr = _make_mgr(tmp_path)
        _setup(mgr, "## Fast\nschedule: */15 * * * *\ntype: llm\nCheck for new items\n")

        registration = json.loads((tmp_path / "state" / "cron_registration.json").read_text(encoding="utf-8"))
        assert registration["registered"] == [{"name": "Fast", "schedule": "*/15 * * * *"}]
        assert registration["rejected"] == []
        mgr.scheduler.add_job.assert_called_once()

    def test_same_diagnostics_are_not_notified_twice(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        mgr = _make_mgr(tmp_path)
        write = MagicMock()
        monkeypatch.setattr(mgr, "_write_cron_health_notification", write)
        diagnostics = {"Fast": [HIGH_FREQUENCY_LLM]}

        mgr._check_cron_parse_health("", [], 0, diagnostics)
        mgr._check_cron_parse_health("", [], 0, diagnostics)

        write.assert_called_once()

    def test_changed_diagnostics_are_notified_again(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        mgr = _make_mgr(tmp_path)
        write = MagicMock()
        monkeypatch.setattr(mgr, "_write_cron_health_notification", write)

        mgr._check_cron_parse_health("", [], 0, {"Fast": [HIGH_FREQUENCY_LLM]})
        mgr._check_cron_parse_health("", [], 0, {"Watch": [COMMAND_WITHOUT_SKIP]})

        assert write.call_count == 2

    def test_diagnostics_reappear_after_clearing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        mgr = _make_mgr(tmp_path)
        write = MagicMock()
        monkeypatch.setattr(mgr, "_write_cron_health_notification", write)

        mgr._check_cron_parse_health("", [], 0, {"Fast": [HIGH_FREQUENCY_LLM]})
        mgr._check_cron_parse_health("", [], 0, {})
        mgr._check_cron_parse_health("", [], 0, {"Fast": [HIGH_FREQUENCY_LLM]})

        assert write.call_count == 2


# ── /system/scheduler payload ───────────────────────────────


class TestSystemSchedulerDiagnostics:
    def test_parse_cron_jobs_includes_diagnostics(self, tmp_path: Path) -> None:
        animas_dir = tmp_path / "animas"
        alice_dir = animas_dir / "alice"
        alice_dir.mkdir(parents=True)
        (alice_dir / "cron.md").write_text(
            "## Fast\nschedule: */15 * * * *\ntype: llm\nCheck\n\n"
            "## Daily\nschedule: 0 9 * * *\ntype: llm\nSummarize\n\n"
            "## Watch\nschedule: */10 * * * *\ntype: command\ncommand: echo hi\n",
            encoding="utf-8",
        )

        jobs = _parse_cron_jobs(animas_dir, ["alice"])

        by_name = {job["name"]: job for job in jobs}
        assert by_name["Fast"]["diagnostics"] == [HIGH_FREQUENCY_LLM]
        assert by_name["Daily"]["diagnostics"] == []
        assert by_name["Watch"]["diagnostics"] == [COMMAND_WITHOUT_SKIP]
