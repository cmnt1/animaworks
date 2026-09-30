"""Submitted command tools retry only when their parser rejects -j."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.exceptions import ToolExecutionError
from core.supervisor.task_runner import execute_background_contract


@pytest.mark.asyncio
async def test_command_retries_without_json_flag_when_unsupported(tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(list(argv))
        assert kwargs["env"]["ANIMAWORKS_ANIMA_DIR"] == str(tmp_path)
        if argv[-1] == "-j":
            return subprocess.CompletedProcess(argv, 2, "", "chatwork: error: unrecognized arguments: -j")
        return subprocess.CompletedProcess(argv, 0, "rooms listed", "")

    with patch("subprocess.run", side_effect=fake_run):
        result = await execute_background_contract(
            SimpleNamespace(anima_dir=tmp_path),
            kind="command",
            payload={"tool_name": "chatwork", "subcommand": "rooms", "raw_args": ["rooms"]},
        )

    assert calls == [
        ["animaworks-tool", "chatwork", "rooms", "-j"],
        ["animaworks-tool", "chatwork", "rooms"],
    ]
    assert result == {"task_type": "command", "result": "rooms listed", "success": True}


@pytest.mark.asyncio
async def test_command_keeps_json_output_when_supported(tmp_path) -> None:
    completed = subprocess.CompletedProcess([], 0, '{"ok": true}', "")
    with patch("subprocess.run", return_value=completed) as run:
        result = await execute_background_contract(
            SimpleNamespace(anima_dir=tmp_path),
            kind="command",
            payload={"tool_name": "notion", "subcommand": "search", "raw_args": []},
        )

    run.assert_called_once()
    assert run.call_args.args[0] == ["animaworks-tool", "notion", "search", "-j"]
    assert result["result"] == '{"ok": true}'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("returncode", "stderr"),
    [(1, "service unavailable"), (2, "unrecognized arguments: --other"), (1, "unrecognized arguments: -j")],
)
async def test_command_does_not_retry_execution_or_other_argument_errors(tmp_path, returncode, stderr) -> None:
    completed = subprocess.CompletedProcess([], returncode, "", stderr)
    with patch("subprocess.run", return_value=completed) as run, pytest.raises(ToolExecutionError):
        await execute_background_contract(
            SimpleNamespace(anima_dir=tmp_path),
            kind="command",
            payload={"tool_name": "chatwork", "subcommand": "send", "raw_args": []},
        )
    run.assert_called_once()
