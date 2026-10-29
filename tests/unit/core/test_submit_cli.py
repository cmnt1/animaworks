# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for animaworks-tool submit CLI command.

The command stores a ``task_type=command`` input in TaskStore and preserves the
existing JSON acknowledgement for CLI callers.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest


def _submit(anima_dir: Path, args: list[str], monkeypatch: pytest.MonkeyPatch) -> dict:
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))
    from cli.tool_dispatch import _handle_submit

    captured = io.StringIO()
    with patch("builtins.print", side_effect=lambda value, **_kwargs: captured.write(str(value) + "\n")):
        _handle_submit(args)
    return json.loads(captured.getvalue())


def _get_submitted_payload(anima_dir: Path, task_id: str) -> dict:
    from core.tasks.queue import TaskQueueManager

    return TaskQueueManager(anima_dir).store.get_input(anima_dir.name, task_id)


class TestHandleSubmit:
    def test_submits_command_to_task_store(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        anima_dir = tmp_path / "animas" / "test-anima"
        anima_dir.mkdir(parents=True)

        output = _submit(anima_dir, ["image_gen", "3d", "assets/avatar.png"], monkeypatch)
        payload = _get_submitted_payload(anima_dir, output["task_id"])

        assert payload["task_type"] == "command"
        assert payload["tool_name"] == "image_gen"
        assert payload["subcommand"] == "3d"
        assert payload["raw_args"] == ["3d", "assets/avatar.png"]
        assert payload["anima_name"] == "test-anima"
        assert payload["anima_dir"] == str(anima_dir)
        assert payload["status"] == "pending"
        assert payload["submitted_by"] == "test-anima"
        assert payload["submitted_at"]
        assert not (anima_dir / "state" / "background_tasks" / "pending").exists()

        from core.tasks.queue import TaskQueueManager

        task = TaskQueueManager(anima_dir).get_task_by_id(output["task_id"])
        assert task is not None
        assert task.status == "pending"
        assert task.meta["executor"] == "command"
        assert task.original_instruction.startswith("animaworks-tool image_gen 3d")

    def test_output_json_remains_compatible(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        anima_dir = tmp_path / "animas" / "test-anima"
        anima_dir.mkdir(parents=True)

        output = _submit(anima_dir, ["local_llm", "generate", "hello"], monkeypatch)

        assert output["status"] == "submitted"
        assert output["tool"] == "local_llm"
        assert output["subcommand"] == "generate"
        assert len(output["task_id"]) == 12
        assert "task_id" in output["message"]

    @pytest.mark.parametrize(
        ("args", "tool_name", "subcommand", "raw_args"),
        [
            (["transcribe", "--language", "ja", "/audio.wav"], "transcribe", "ja", ["--language", "ja", "/audio.wav"]),
            (["transcribe"], "transcribe", "", []),
            (["some_tool", "--verbose", "--dry-run"], "some_tool", "", ["--verbose", "--dry-run"]),
        ],
    )
    def test_preserves_args_and_detects_subcommand(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        args: list[str],
        tool_name: str,
        subcommand: str,
        raw_args: list[str],
    ) -> None:
        anima_dir = tmp_path / "animas" / "sakura"
        anima_dir.mkdir(parents=True)

        output = _submit(anima_dir, args, monkeypatch)
        payload = _get_submitted_payload(anima_dir, output["task_id"])

        assert payload["tool_name"] == tool_name
        assert payload["subcommand"] == subcommand
        assert payload["raw_args"] == raw_args

    def test_unique_task_ids(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        anima_dir = tmp_path / "animas" / "test-anima"
        anima_dir.mkdir(parents=True)

        task_ids = [_submit(anima_dir, ["local_llm", "generate", str(i)], monkeypatch)["task_id"] for i in range(5)]

        assert len(set(task_ids)) == 5
        from core.tasks.queue import TaskQueueManager

        assert len(TaskQueueManager(anima_dir).store.pending("test-anima")) == 5

    def test_no_args_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", "/tmp/fake")
        from cli.tool_dispatch import _handle_submit

        with pytest.raises(SystemExit) as exc_info:
            _handle_submit([])
        assert exc_info.value.code == 1

    def test_no_anima_dir_exits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANIMAWORKS_ANIMA_DIR", raising=False)
        from cli.tool_dispatch import _handle_submit

        with pytest.raises(SystemExit) as exc_info:
            _handle_submit(["image_gen", "3d"])
        assert exc_info.value.code == 1
