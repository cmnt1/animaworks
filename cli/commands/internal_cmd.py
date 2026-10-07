from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Thin CLI adapters for internal tools invoked by Animas."""

import argparse
import json
import sys

from cli._anima_tool import run_anima_tool

_TOOL_ERROR_PREFIXES = ("error", "unknown tool:", "エラー", "오류", "错误")


def _print_tool_result(result: str) -> None:
    """Print a tool result and use a failing exit status for handler errors."""
    print(result)
    rendered = result.lstrip()
    try:
        parsed, _ = json.JSONDecoder().raw_decode(rendered)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict) and parsed.get("status") == "error":
        sys.exit(1)
    if rendered.casefold().startswith(_TOOL_ERROR_PREFIXES):
        sys.exit(1)


def _run_tool(tool_name: str, tool_args: dict) -> None:
    _print_tool_result(run_anima_tool(tool_name, tool_args))


def cmd_internal(args: argparse.Namespace) -> None:
    """Dispatch internal subcommand."""
    sub = getattr(args, "internal_command", None)
    if sub == "archive-memory":
        _cmd_archive_memory(args)
    elif sub == "check-permissions":
        _cmd_check_permissions(args)
    elif sub == "create-skill":
        _cmd_create_skill(args)
    elif sub == "manage-channel":
        _cmd_manage_channel(args)
    elif sub == "list-background-tasks":
        _cmd_list_background_tasks(args)
    elif sub == "check-background-task":
        _cmd_check_background_task(args)
    else:
        print(
            "Usage: animaworks-tool internal {archive-memory|check-permissions|create-skill|manage-channel|list-background-tasks|check-background-task}",
            file=sys.stderr,
        )
        sys.exit(1)


def _cmd_archive_memory(args: argparse.Namespace) -> None:
    _run_tool(
        "archive_memory_file",
        {
            "path": getattr(args, "path", ""),
            "reason": getattr(args, "reason", "archived via CLI"),
        },
    )


def _cmd_check_permissions(args: argparse.Namespace) -> None:
    tool_args = {"tool_name": getattr(args, "tool_name", "")}
    action = getattr(args, "action", None)
    if action:
        tool_args["action"] = action
    _run_tool("check_permissions", tool_args)


def _skill_description(body: str) -> str:
    """Derive a description from the first non-empty Markdown line."""
    first_line = next((line.strip() for line in body.splitlines() if line.strip()), "")
    return first_line.lstrip("#").strip()


def _cmd_create_skill(args: argparse.Namespace) -> None:
    from core.memory.frontmatter import parse_frontmatter

    name = getattr(args, "name", "")
    content = getattr(args, "content", None)
    if content is None:
        content = sys.stdin.read()

    metadata, body = parse_frontmatter(content)
    description = metadata.get("description")
    if not isinstance(description, str) or not description.strip():
        description = _skill_description(body)

    skill_name = name[:-3] if name.endswith(".md") else name
    tool_args = {
        "skill_name": skill_name,
        "description": description,
        "body": body,
        "location": getattr(args, "location", "personal"),
    }
    _run_tool("create_skill", tool_args)


def _cmd_manage_channel(args: argparse.Namespace) -> None:
    tool_args = {
        "action": getattr(args, "action", ""),
        "channel": getattr(args, "channel", ""),
    }
    members = getattr(args, "members", None) or []
    if members:
        tool_args["members"] = members
    description = getattr(args, "description", None)
    if description is not None:
        tool_args["description"] = description
    _run_tool("manage_channel", tool_args)


def _cmd_list_background_tasks(args: argparse.Namespace) -> None:
    tool_args = {}
    status = getattr(args, "status", None)
    if status:
        tool_args["status"] = status
    _run_tool("list_background_tasks", tool_args)


def _cmd_check_background_task(args: argparse.Namespace) -> None:
    _run_tool("check_background_task", {"task_id": getattr(args, "task_id", "")})


def register_internal_command(subparsers) -> None:
    """Register the internal subcommand under animaworks-tool."""
    p_internal = subparsers.add_parser("internal", help="Internal tools for Anima use")
    internal_sub = p_internal.add_subparsers(dest="internal_command")

    p_archive = internal_sub.add_parser("archive-memory", help="Archive a memory file")
    p_archive.add_argument("path", help="Relative path allowed by archive_memory_file")
    p_archive.add_argument("--reason", default="archived via CLI", help="Reason for archiving")
    p_archive.set_defaults(func=cmd_internal)

    p_check_perm = internal_sub.add_parser("check-permissions", help="Check tool permission")
    p_check_perm.add_argument("tool_name", help="Tool name")
    p_check_perm.add_argument("action", nargs="?", default="", help="Optional action")
    p_check_perm.set_defaults(func=cmd_internal)

    p_skill = internal_sub.add_parser("create-skill", help="Create a skill file")
    p_skill.add_argument("name", help="Skill name (or name.md)")
    p_skill.add_argument("--content", default=None, help="SKILL.md content (default: stdin)")
    p_skill.add_argument("--location", choices=["personal", "common"], default="personal")
    p_skill.set_defaults(func=cmd_internal)

    p_channel = internal_sub.add_parser("manage-channel", help="Manage a channel and its members")
    p_channel.add_argument(
        "action",
        choices=["create", "archive", "add_member", "remove_member", "info"],
        help="Action",
    )
    p_channel.add_argument("channel", help="Channel name")
    p_channel.add_argument("--member", dest="members", action="append", default=[], help="Member name (repeatable)")
    p_channel.add_argument("--description", default=None, help="Description for a new channel")
    p_channel.set_defaults(func=cmd_internal)

    p_list_bg = internal_sub.add_parser("list-background-tasks", help="List background tasks")
    p_list_bg.add_argument(
        "--status",
        choices=["running", "completed", "failed", "pending"],
        default=None,
        help="Filter by status",
    )
    p_list_bg.set_defaults(func=cmd_internal)

    p_check_bg = internal_sub.add_parser("check-background-task", help="Check a specific task")
    p_check_bg.add_argument("task_id", help="Task ID")
    p_check_bg.set_defaults(func=cmd_internal)

    p_internal.set_defaults(func=cmd_internal)
