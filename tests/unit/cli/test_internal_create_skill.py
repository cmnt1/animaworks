from __future__ import annotations

import json
from argparse import Namespace
from io import StringIO
from unittest.mock import Mock

import pytest

from cli.commands import internal_cmd


def _run_internal(monkeypatch, capsys, subcommand: str, args: dict, tool_name: str, tool_args: dict) -> None:
    result = '{"status":"ok"}'
    run_tool = Mock(return_value=result)
    monkeypatch.setattr("cli._anima_tool.run_anima_tool", run_tool)

    internal_cmd.cmd_internal(Namespace(internal_command=subcommand, **args))

    run_tool.assert_called_once_with(tool_name, tool_args)
    assert capsys.readouterr().out == f"{result}\n"


def test_archive_memory_maps_path_and_default_reason(monkeypatch, capsys) -> None:
    _run_internal(
        monkeypatch,
        capsys,
        "archive-memory",
        {"path": "knowledge/old.md"},
        "archive_memory_file",
        {"path": "knowledge/old.md", "reason": "archived via CLI"},
    )


def test_archive_memory_maps_explicit_reason(monkeypatch, capsys) -> None:
    _run_internal(
        monkeypatch,
        capsys,
        "archive-memory",
        {"path": "procedures/old.md", "reason": "replaced"},
        "archive_memory_file",
        {"path": "procedures/old.md", "reason": "replaced"},
    )


def test_check_permissions_maps_optional_action(monkeypatch, capsys) -> None:
    _run_internal(
        monkeypatch,
        capsys,
        "check-permissions",
        {"tool_name": "gmail", "action": "send"},
        "check_permissions",
        {"tool_name": "gmail", "action": "send"},
    )


def test_check_permissions_omits_empty_action(monkeypatch, capsys) -> None:
    _run_internal(
        monkeypatch,
        capsys,
        "check-permissions",
        {"tool_name": "gmail", "action": ""},
        "check_permissions",
        {"tool_name": "gmail"},
    )


def test_create_skill_maps_frontmatter_and_location(monkeypatch, capsys) -> None:
    content = "---\nname: legacy\ndescription: Deploy applications\n---\n\n# Deployment\nRun the deploy flow.\n"
    _run_internal(
        monkeypatch,
        capsys,
        "create-skill",
        {"name": "legacy.md", "content": content, "location": "common"},
        "create_skill",
        {
            "skill_name": "legacy",
            "description": "Deploy applications",
            "body": "# Deployment\nRun the deploy flow.\n",
            "location": "common",
        },
    )


def test_create_skill_uses_first_heading_as_fallback_description(monkeypatch, capsys) -> None:
    content = "# Deploy\n\nRun the deploy flow.\n"
    _run_internal(
        monkeypatch,
        capsys,
        "create-skill",
        {"name": "deploy", "content": content, "location": "personal"},
        "create_skill",
        {
            "skill_name": "deploy",
            "description": "Deploy",
            "body": content,
            "location": "personal",
        },
    )


def test_create_skill_reads_stdin_when_content_is_omitted(monkeypatch, capsys) -> None:
    content = "A skill for reports\n\nDetails.\n"
    monkeypatch.setattr(internal_cmd.sys, "stdin", StringIO(content))
    _run_internal(
        monkeypatch,
        capsys,
        "create-skill",
        {"name": "reports"},
        "create_skill",
        {
            "skill_name": "reports",
            "description": "A skill for reports",
            "body": content,
            "location": "personal",
        },
    )


def test_manage_channel_maps_members_and_description(monkeypatch, capsys) -> None:
    _run_internal(
        monkeypatch,
        capsys,
        "manage-channel",
        {
            "action": "create",
            "channel": "team",
            "members": ["alice", "bob"],
            "description": "Team channel",
        },
        "manage_channel",
        {
            "action": "create",
            "channel": "team",
            "members": ["alice", "bob"],
            "description": "Team channel",
        },
    )


@pytest.mark.parametrize("action", ["archive", "add_member", "remove_member", "info"])
def test_manage_channel_maps_supported_actions(monkeypatch, capsys, action: str) -> None:
    members = ["bob"] if action == "add_member" else None
    args = {"action": action, "channel": "team"}
    tool_args = {"action": action, "channel": "team"}
    if members:
        args["members"] = members
        tool_args["members"] = members
    _run_internal(monkeypatch, capsys, "manage-channel", args, "manage_channel", tool_args)


def test_list_background_tasks_maps_status(monkeypatch, capsys) -> None:
    _run_internal(
        monkeypatch,
        capsys,
        "list-background-tasks",
        {"status": "running"},
        "list_background_tasks",
        {"status": "running"},
    )


def test_list_background_tasks_omits_status_when_not_given(monkeypatch, capsys) -> None:
    _run_internal(
        monkeypatch,
        capsys,
        "list-background-tasks",
        {},
        "list_background_tasks",
        {},
    )


def test_check_background_task_maps_task_id(monkeypatch, capsys) -> None:
    _run_internal(
        monkeypatch,
        capsys,
        "check-background-task",
        {"task_id": "task-1"},
        "check_background_task",
        {"task_id": "task-1"},
    )


@pytest.mark.parametrize(
    "error",
    [
        json.dumps({"status": "error", "message": "missing"}),
        "Error: missing",
        "エラー: 拒否",
        "오류: 거부",
        "错误：拒绝",
    ],
)
def test_handler_error_is_printed_and_exits_nonzero(monkeypatch, capsys, error: str) -> None:
    monkeypatch.setattr("cli._anima_tool.run_anima_tool", lambda *_args: error)

    with pytest.raises(SystemExit) as stopped:
        internal_cmd.cmd_internal(Namespace(internal_command="check-background-task", task_id="missing"))

    assert stopped.value.code == 1
    assert capsys.readouterr().out == f"{error}\n"
