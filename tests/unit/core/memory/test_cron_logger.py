"""Unit tests for core/memory/maintenance/cron_logger.py — CronLogger."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from core.memory.maintenance.cron_logger import CronLogger

JST = ZoneInfo("Asia/Tokyo")


def _jst_today() -> date:
    return datetime.now(tz=JST).date()


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "anima"
    d.mkdir()
    return d


@pytest.fixture
def cl(anima_dir: Path) -> CronLogger:
    return CronLogger(anima_dir)


# ── append_cron_log ──────────────────────────────────────


class TestAppendCronLog:
    def test_creates_jsonl_file(self, cl: CronLogger, anima_dir: Path) -> None:
        cl.append_cron_log("daily-report", summary="Generated report", duration_ms=123)
        log_dir = anima_dir / "state" / "cron_logs"
        path = log_dir / f"{_jst_today().isoformat()}.jsonl"
        assert path.exists()

    def test_writes_correct_json_fields(self, cl: CronLogger, anima_dir: Path) -> None:
        cl.append_cron_log("daily-report", summary="Generated report", duration_ms=456)
        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["task"] == "daily-report"
        assert entry["summary"] == "Generated report"
        assert entry["duration_ms"] == 456
        assert "timestamp" in entry

    def test_appends_multiple_entries(self, cl: CronLogger, anima_dir: Path) -> None:
        cl.append_cron_log("task-a", summary="First", duration_ms=100)
        cl.append_cron_log("task-b", summary="Second", duration_ms=200)
        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["task"] == "task-a"
        assert json.loads(lines[1])["task"] == "task-b"

    def test_truncates_summary_at_500_chars(self, cl: CronLogger, anima_dir: Path) -> None:
        long_summary = "x" * 1000
        cl.append_cron_log("task", summary=long_summary, duration_ms=0)
        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        entry = json.loads(path.read_text(encoding="utf-8").strip())
        assert len(entry["summary"]) == 500

    def test_more_than_50_entries_are_preserved(self, cl: CronLogger, anima_dir: Path) -> None:
        for i in range(55):
            cl.append_cron_log(f"task-{i}", summary=f"entry {i}", duration_ms=i)
        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 55
        assert json.loads(lines[0])["task"] == "task-0"

    def test_creates_parent_directories(self, cl: CronLogger, anima_dir: Path) -> None:
        log_dir = anima_dir / "state" / "cron_logs"
        assert not log_dir.exists()
        cl.append_cron_log("task", summary="ok", duration_ms=0)
        assert log_dir.is_dir()

    def test_writes_scheduler_audit_event(self, cl: CronLogger, anima_dir: Path) -> None:
        cl.append_cron_event("daily", "skipped", reason="already running", schedule="0 9 * * *")
        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        entry = json.loads(path.read_text(encoding="utf-8"))
        assert entry["task"] == "daily"
        assert entry["event"] == "skipped"
        assert entry["reason"] == "already running"
        assert entry["schedule"] == "0 9 * * *"

    def test_append_rotates_logs_older_than_14_days(self, cl: CronLogger, anima_dir: Path) -> None:
        log_dir = anima_dir / "state" / "cron_logs"
        log_dir.mkdir(parents=True)
        old_path = log_dir / f"{(_jst_today() - timedelta(days=20)).isoformat()}.jsonl"
        old_path.write_text("{}\n", encoding="utf-8")

        cl.append_cron_event("daily", "fired")

        assert not old_path.exists()

    def test_concurrent_appends_no_data_loss(self, anima_dir: Path) -> None:
        """Concurrent appends from multiple threads preserve all entries."""
        n_threads = 8
        entries_per_thread = 10

        def append_batch(thread_id: int) -> None:
            logger = CronLogger(anima_dir)
            for i in range(entries_per_thread):
                logger.append_cron_log(
                    f"thread-{thread_id}-task-{i}",
                    summary=f"entry {i} from thread {thread_id}",
                    duration_ms=thread_id * 100 + i,
                )

        with ThreadPoolExecutor(max_workers=n_threads) as executor:
            futures = [executor.submit(append_batch, tid) for tid in range(n_threads)]
            for f in futures:
                f.result()

        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        total_expected = n_threads * entries_per_thread
        assert len(lines) == total_expected
        for line in lines:
            entry = json.loads(line)
            assert "task" in entry
            assert "summary" in entry


# ── append_cron_command_log ──────────────────────────────


class TestAppendCronCommandLog:
    def test_writes_correct_json_fields(self, cl: CronLogger, anima_dir: Path) -> None:
        cl.append_cron_command_log(
            "git-pull",
            exit_code=0,
            stdout="Already up to date.\n",
            stderr="",
            duration_ms=350,
        )
        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        entry = json.loads(path.read_text(encoding="utf-8").strip())
        assert entry["task"] == "git-pull"
        assert entry["exit_code"] == 0
        assert entry["stdout_lines"] == 1
        assert entry["stderr_lines"] == 0
        assert entry["stdout_preview"] == "Already up to date."
        assert entry["stderr_preview"] == ""
        assert entry["duration_ms"] == 350
        assert "timestamp" in entry

    def test_preview_short_output(self, cl: CronLogger, anima_dir: Path) -> None:
        """Output with <=10 lines is included in full."""
        stdout = "\n".join(f"line {i}" for i in range(8))
        cl.append_cron_command_log(
            "task",
            exit_code=0,
            stdout=stdout,
            stderr="",
            duration_ms=0,
        )
        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        entry = json.loads(path.read_text(encoding="utf-8").strip())
        assert entry["stdout_lines"] == 8
        assert "..." not in entry["stdout_preview"]

    def test_preview_long_output(self, cl: CronLogger, anima_dir: Path) -> None:
        """Output with >10 lines shows first 5 + '...' + last 5."""
        stdout = "\n".join(f"line {i}" for i in range(20))
        cl.append_cron_command_log(
            "task",
            exit_code=0,
            stdout=stdout,
            stderr="",
            duration_ms=0,
        )
        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        entry = json.loads(path.read_text(encoding="utf-8").strip())
        assert entry["stdout_lines"] == 20
        preview_lines = entry["stdout_preview"].splitlines()
        assert preview_lines[5] == "..."
        assert preview_lines[0] == "line 0"
        assert preview_lines[-1] == "line 19"
        assert len(preview_lines) == 11  # 5 + 1 ("...") + 5

    def test_preview_truncated_at_1000_chars(self, cl: CronLogger, anima_dir: Path) -> None:
        """Preview is capped at 1000 characters."""
        # Create long lines so preview exceeds 1000 chars
        stdout = "\n".join("A" * 200 for _ in range(20))
        cl.append_cron_command_log(
            "task",
            exit_code=0,
            stdout=stdout,
            stderr="",
            duration_ms=0,
        )
        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        entry = json.loads(path.read_text(encoding="utf-8").strip())
        assert len(entry["stdout_preview"]) <= 1000

    def test_empty_stdout_stderr(self, cl: CronLogger, anima_dir: Path) -> None:
        cl.append_cron_command_log(
            "task",
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=0,
        )
        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        entry = json.loads(path.read_text(encoding="utf-8").strip())
        assert entry["stdout_lines"] == 0
        assert entry["stderr_lines"] == 0
        assert entry["stdout_preview"] == ""
        assert entry["stderr_preview"] == ""

    def test_nonzero_exit_code(self, cl: CronLogger, anima_dir: Path) -> None:
        cl.append_cron_command_log(
            "failing-task",
            exit_code=1,
            stdout="",
            stderr="Error: something went wrong",
            duration_ms=50,
        )
        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        entry = json.loads(path.read_text(encoding="utf-8").strip())
        assert entry["exit_code"] == 1
        assert entry["stderr_lines"] == 1
        assert "Error" in entry["stderr_preview"]

    def test_more_than_50_command_entries_are_preserved(self, cl: CronLogger, anima_dir: Path) -> None:
        for i in range(55):
            cl.append_cron_command_log(
                f"task-{i}",
                exit_code=0,
                stdout=f"out-{i}",
                stderr="",
                duration_ms=i,
            )
        path = anima_dir / "state" / "cron_logs" / f"{_jst_today().isoformat()}.jsonl"
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 55


def test_now_local_used_for_date(cl: CronLogger, anima_dir: Path) -> None:
    """Verify that now_local() determines the log file date, not date.today()."""
    fake_jst = datetime(2026, 3, 6, 1, 30, 0, tzinfo=JST)
    with patch("core.memory.maintenance.cron_logger.now_local", return_value=fake_jst):
        cl.append_cron_log("jst-task", summary="jst check", duration_ms=1)

    path = anima_dir / "state" / "cron_logs" / "2026-03-06.jsonl"
    assert path.exists()
    entry = json.loads(path.read_text(encoding="utf-8").strip())
    assert entry["task"] == "jst-task"
