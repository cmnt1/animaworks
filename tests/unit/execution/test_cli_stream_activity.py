from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for common activity recording in CLI streaming executors."""

import json
from pathlib import Path
from typing import Any

import pytest

from core.execution.cli_stream import CLIStreamExecutor
from core.prompt.context import ContextTracker
from core.schemas import ModelConfig


class _FakeCLIStreamExecutor(CLIStreamExecutor):
    engine_mode = "X"

    async def _stream_events(self, *args: Any, **kwargs: Any):
        yield {
            "type": "tool_start",
            "tool_id": "tool-1",
            "tool_name": "Bash",
            "input": {"command": "echo hello"},
        }
        yield {
            "type": "tool_end",
            "tool_id": "tool-1",
            "tool_name": "Bash",
            "result": "hello",
            "is_error": False,
        }


@pytest.mark.asyncio
async def test_cli_tool_end_records_activity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "data"
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(data_dir))
    anima_dir = data_dir / "animas" / "test-anima"
    anima_dir.mkdir(parents=True)
    executor = _FakeCLIStreamExecutor(ModelConfig(model="test"), anima_dir)

    events = [
        event
        async for event in executor.execute_streaming(
            system_prompt="",
            prompt="",
            tracker=ContextTracker(model="test"),
        )
    ]

    assert [event["type"] for event in events] == ["tool_start", "tool_end"]
    activity_files = list((anima_dir / "activity_log").glob("*.jsonl"))
    entries = [json.loads(line) for path in activity_files for line in path.read_text(encoding="utf-8").splitlines()]
    assert [entry["type"] for entry in entries] == ["tool_use", "tool_result"]
    assert entries[0]["tool"] == "Bash"
    assert entries[0]["meta"]["args"] == {"command": "echo hello"}
    assert entries[1]["content"] == "hello"
