"""Task queue CLI adapters delegate updates and listings to ToolHandler."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from cli.commands.task_cmd import _cmd_add, _cmd_list, _cmd_resume, _cmd_update, register_task_command


def test_cli_update_calls_update_task_with_mapped_args(capsys, monkeypatch) -> None:
    result = '{"task_id":"task-1","status":"done"}'
    run_tool = Mock(return_value=result)
    monkeypatch.setattr("cli._anima_tool.run_anima_tool", run_tool)

    _cmd_update(SimpleNamespace(task_id="task-1", status="done", summary="Verified once"))

    run_tool.assert_called_once_with(
        "update_task",
        {"task_id": "task-1", "status": "done", "summary": "Verified once"},
    )
    assert capsys.readouterr().out == f"{result}\n"


def test_cli_update_omits_missing_summary(monkeypatch, capsys) -> None:
    run_tool = Mock(return_value="{}")
    monkeypatch.setattr("cli._anima_tool.run_anima_tool", run_tool)

    _cmd_update(SimpleNamespace(task_id="task-1", status="cancelled", summary=None))

    run_tool.assert_called_once_with("update_task", {"task_id": "task-1", "status": "cancelled"})
    capsys.readouterr()


def test_cli_update_prints_tool_error_and_exits_nonzero(monkeypatch, capsys) -> None:
    error = json.dumps({"status": "error", "error_type": "InvalidArguments", "message": "retired"})
    monkeypatch.setattr("cli._anima_tool.run_anima_tool", lambda *_args: error)

    with pytest.raises(SystemExit) as stopped:
        _cmd_update(SimpleNamespace(task_id="task-1", status="failed", summary=None))

    assert stopped.value.code == 1
    assert capsys.readouterr().out == f"{error}\n"


def test_cli_list_requests_full_tool_details(monkeypatch, capsys) -> None:
    result = "[]"
    run_tool = Mock(return_value=result)
    monkeypatch.setattr("cli._anima_tool.run_anima_tool", run_tool)

    _cmd_list(SimpleNamespace(status="pending"))

    run_tool.assert_called_once_with("list_tasks", {"detail": True, "status": "pending"})
    assert capsys.readouterr().out == f"{result}\n"


def test_cli_list_without_filter_requests_full_tool_details(monkeypatch, capsys) -> None:
    run_tool = Mock(return_value="[]")
    monkeypatch.setattr("cli._anima_tool.run_anima_tool", run_tool)

    _cmd_list(SimpleNamespace(status=None))

    run_tool.assert_called_once_with("list_tasks", {"detail": True})
    capsys.readouterr()


def test_cli_resume_calls_update_task_with_resume_flag(monkeypatch, capsys) -> None:
    run_tool = Mock(return_value='{"status":"pending"}')
    monkeypatch.setattr("cli._anima_tool.run_anima_tool", run_tool)

    _cmd_resume(SimpleNamespace(task_id="task-1"))

    run_tool.assert_called_once_with(
        "update_task",
        {"task_id": "task-1", "status": "pending", "resume": True},
    )
    capsys.readouterr()


def test_task_add_still_publishes_an_executable_descriptor(tmp_path: Path, capsys) -> None:
    anima_dir = tmp_path / "animas" / "worker"
    anima_dir.mkdir(parents=True)
    entry = Mock()
    entry.model_dump.return_value = {"task_id": "task-1", "summary": "Do the work"}

    with patch("core.tasks.dispatch.publish_tasks", return_value=[entry]) as publish:
        _cmd_add(
            SimpleNamespace(
                source="human",
                instruction="Do the work",
                assignee="worker",
                summary=None,
                relay_chain="alice,bob",
                workspace=None,
            ),
            SimpleNamespace(anima_dir=anima_dir),
        )

    payload = publish.call_args.args[1][0]
    assert publish.call_args.kwargs["source"] == "human"
    assert payload["task_type"] == "llm"
    assert payload["description"] == "Do the work"
    assert payload["title"] == "Do the work"
    assert payload["task_id"]
    assert json.loads(capsys.readouterr().out)["executable"] is True


def test_task_add_help_explains_difference_from_backlog_task(capsys) -> None:
    parser = argparse.ArgumentParser()
    register_task_command(parser.add_subparsers())

    with pytest.raises(SystemExit) as stopped:
        parser.parse_args(["task", "add", "--help"])

    assert stopped.value.code == 0
    help_text = capsys.readouterr().out
    assert "executable TaskExec task" in help_text
    assert "backlog_task" in help_text
