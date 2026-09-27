"""Unit tests for skip_pattern filtering in command-type cron tasks."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.schemas import CronTask
from core.supervisor.cron_followup import command_followup_output
from core.supervisor.scheduler_manager import SchedulerManager

# ── Helpers ──────────────────────────────────────────────────


def _make_scheduler_mgr() -> SchedulerManager:
    """Create a SchedulerManager with minimal config for unit testing."""
    mock_anima = MagicMock()
    mock_anima.memory = MagicMock()

    anima_dir = Path("/tmp/animas/test")
    anima_dir.mkdir(parents=True, exist_ok=True)
    mgr = SchedulerManager(
        anima=mock_anima,
        anima_name="test",
        anima_dir=anima_dir,
        emit_event=MagicMock(),
    )
    # Always-isolated: _run_cron_task delegates to the task runner supervisor.
    mgr._task_runner_supervisor.run_cron = AsyncMock(
        return_value={"result": {"action": "completed", "summary": "ok"}, "success": True}
    )
    return mgr


def _make_command_task(
    name: str = "test_task",
    skip_pattern: str | None = None,
    trigger_heartbeat: bool = True,
) -> CronTask:
    return CronTask(
        name=name,
        schedule="*/5 * * * *",
        type="command",
        tool="test_tool",
        skip_pattern=skip_pattern,
        trigger_heartbeat=trigger_heartbeat,
    )


def _command_result(
    *,
    exit_code: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> dict:
    return {
        "task": "test_task",
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "duration_ms": 100,
    }


# ── TestDispatchDelegation ─────────────────────────────────


class TestDispatchDelegation:
    """_run_cron_task always delegates to the task runner supervisor."""

    @pytest.mark.asyncio
    async def test_llm_task_delegates_to_supervisor(self):
        mgr = _make_scheduler_mgr()
        task = CronTask(
            name="review",
            schedule="0 9 * * *",
            type="llm",
            description="Review PRs",
            skills=["github-pr-review"],
        )

        await mgr._run_cron_task(task)

        mgr._task_runner_supervisor.run_cron.assert_awaited_once_with(task)
        mgr._anima.run_cron_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_command_task_delegates_to_supervisor(self):
        mgr = _make_scheduler_mgr()
        task = _make_command_task()

        await mgr._run_cron_task(task)

        mgr._task_runner_supervisor.run_cron.assert_awaited_once_with(task)
        mgr._anima.run_cron_command.assert_not_called()


# ── TestSkipPatternFiltering ─────────────────────────────────


class TestSkipPatternFiltering:
    """Skip-pattern semantics (used by the task runner child via cron_followup)."""

    def test_empty_stdout_is_suppressed(self):
        assert (
            command_followup_output(_make_command_task(skip_pattern=r"^\[\s*\]$"), _command_result(stdout="")) is None
        )

    def test_empty_array_matches_skip_pattern(self):
        out = command_followup_output(_make_command_task(skip_pattern=r"^\[\s*\]$"), _command_result(stdout="[]"))
        assert out is None

    def test_non_empty_array_does_not_match_skip_pattern(self):
        out = command_followup_output(
            _make_command_task(skip_pattern=r"^\[\s*\]$"),
            _command_result(stdout='[{"message_id": "123"}]'),
        )
        assert out == '[{"message_id": "123"}]'

    def test_no_skip_pattern_passes_stdout_through(self):
        out = command_followup_output(_make_command_task(skip_pattern=None), _command_result(stdout="[]"))
        assert out == "[]"

    def test_invalid_regex_continues_to_followup(self, caplog):
        with caplog.at_level(logging.WARNING):
            out = command_followup_output(
                _make_command_task(skip_pattern="[unterminated"),
                _command_result(stdout="some output"),
            )
        assert out == "some output"
        assert "Invalid skip_pattern" in caplog.text

    def test_empty_stdout_no_heartbeat(self):
        out = command_followup_output(
            _make_command_task(skip_pattern=r"^\[\s*\]$"),
            _command_result(stdout="   \n  "),
        )
        assert out is None

    def test_trigger_heartbeat_false_suppresses_heartbeat(self):
        out = command_followup_output(
            _make_command_task(trigger_heartbeat=False),
            _command_result(stdout='[{"message_id": "123"}]'),
        )
        assert out is None

    def test_trigger_heartbeat_true_allows_heartbeat(self):
        out = command_followup_output(
            _make_command_task(trigger_heartbeat=True),
            _command_result(stdout="some output"),
        )
        assert out == "some output"

    def test_trigger_heartbeat_false_takes_precedence_over_skip_pattern(self):
        out = command_followup_output(
            _make_command_task(skip_pattern=r"^\[\s*\]$", trigger_heartbeat=False),
            _command_result(stdout='[{"data": "real"}]'),
        )
        assert out is None

    def test_nonzero_exit_code_triggers_failure_review(self):
        out = command_followup_output(
            _make_command_task(skip_pattern=None),
            _command_result(stdout="error occurred", stderr="some error", exit_code=1),
        )
        assert "some error" in out
