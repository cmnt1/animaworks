"""Submitted command tools retry without -j when the subcommand rejects it."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from core.supervisor.task_runner import execute_background_contract


def _completed(
    argv: list[str], returncode: int, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, returncode, stdout=stdout, stderr=stderr)


@pytest.mark.asyncio
async def test_command_retries_without_json_flag_when_unsupported(tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        if argv[-1] == "-j":
            return _completed(argv, 2, stderr="animaworks-chatwork: error: unrecognized arguments: -j")
        return _completed(argv, 0, stdout="rooms listed")

    with patch("subprocess.run", side_effect=fake_run):
        result = await execute_background_contract(
            SimpleNamespace(anima_dir=tmp_path),
            kind="command",
            payload={"tool_name": "chatwork", "subcommand": "rooms", "raw_args": []},
        )

    assert calls == [
        ["animaworks-tool", "chatwork", "rooms", "-j"],
        ["animaworks-tool", "chatwork", "rooms"],
    ]
    assert result == {"task_type": "command", "result": "rooms listed", "success": True}


@pytest.mark.asyncio
async def test_command_keeps_json_output_when_supported(tmp_path) -> None:
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        return _completed(argv, 0, stdout='{"ok": true}')

    with patch("subprocess.run", side_effect=fake_run):
        result = await execute_background_contract(
            SimpleNamespace(anima_dir=tmp_path),
            kind="command",
            payload={"tool_name": "notion", "subcommand": "search", "raw_args": []},
        )

    assert calls == [["animaworks-tool", "notion", "search", "-j"]]
    assert result["result"] == '{"ok": true}'
