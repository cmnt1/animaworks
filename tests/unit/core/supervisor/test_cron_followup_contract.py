from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.schemas import CronTask, CycleResult
from core.supervisor.task_runner import execute_cron_contract


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stdout,stderr,exit_code,pattern,enabled,expected",
    [
        ("OK", "", 0, r"\AOK\Z", True, False),
        ("  OK\n", "", 0, r"\AOK\Z", True, False),
        ("OK\nALERT", "", 0, r"\AOK\Z", True, True),
        ("new-format", "", 0, r"\AOK\Z", True, True),
        ("OK", "sensor failed", 1, r"\AOK\Z", True, True),
        ("", "TimeoutError", 1, r"\AOK\Z", True, True),
        ("", "", 1, r"\AOK\Z", True, True),
        ("OK", "warning", 0, r"\AOK\Z", True, True),
        ("OK", "", 0, "[invalid", True, True),
        ("", "", 0, None, True, False),
        ("ALERT", "", 0, None, False, False),
        ("", "failure", 1, None, False, False),
    ],
)
async def test_execute_cron_contract_followup(
    stdout: str,
    stderr: str,
    exit_code: int,
    pattern: str | None,
    enabled: bool,
    expected: bool,
) -> None:
    anima = MagicMock()
    result = {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}
    anima.run_cron_command = AsyncMock(return_value=result)
    anima.run_cron_task = AsyncMock(return_value=CycleResult(trigger="cron", action="responded", summary="reviewed"))
    task = CronTask(
        name="sensor",
        schedule="*/10 * * * *",
        type="command",
        command="sensor",
        skip_pattern=pattern,
        trigger_heartbeat=enabled,
    )

    outcome = await execute_cron_contract(anima, task)

    assert outcome["success"] == (exit_code == 0)
    assert outcome["result"] == result
    assert anima.run_cron_command.await_count == 1
    assert anima.run_cron_task.await_count == int(expected)
    if expected and stderr:
        assert stderr in anima.run_cron_task.call_args.kwargs["command_output"]
