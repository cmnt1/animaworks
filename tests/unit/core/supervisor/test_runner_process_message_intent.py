"""Unit tests for AnimaRunner process_message handler delegation."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.supervisor.runner import AnimaRunner


def _runner(tmp_path: Path, *, run_chat_result: object) -> AnimaRunner:
    runner = AnimaRunner(
        anima_name="sakura",
        socket_path=tmp_path / "sakura.sock",
        animas_dir=tmp_path / "animas",
        shared_dir=tmp_path / "shared",
    )
    runner.anima = MagicMock()
    runner.anima.process_message = AsyncMock()
    supervisor = MagicMock()
    supervisor.run_chat = AsyncMock(return_value=run_chat_result)
    runner._scheduler_mgr = SimpleNamespace(_task_runner_supervisor=supervisor)
    return runner


@pytest.mark.asyncio
async def test_handle_process_message_forwards_payload_to_child(tmp_path: Path):
    result = {"response": "ok", "images": [{"path": "assets/a.png"}], "cycle_result": {"summary": "ok"}}
    runner = _runner(tmp_path, run_chat_result=result)

    got = await runner._handle_process_message(
        {"message": "hello", "from_person": "human", "intent": None},
    )

    assert got == result
    supervisor = runner._scheduler_mgr._task_runner_supervisor
    supervisor.run_chat.assert_awaited_once_with(
        kind="message",
        payload={"message": "hello", "from_person": "human", "intent": None},
    )
    runner.anima.process_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_process_message_returns_child_result_as_is(tmp_path: Path):
    runner = _runner(tmp_path, run_chat_result={"response": "legacy-text", "images": [], "cycle_result": {}})

    got = await runner._handle_process_message({"message": "hello"})

    assert got == {"response": "legacy-text", "images": [], "cycle_result": {}}
    runner._scheduler_mgr._task_runner_supervisor.run_chat.assert_awaited_once_with(
        kind="message",
        payload={"message": "hello"},
    )
