from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI subcommands for internal tools invoked by Animas via animaworks-tool internal."""

import argparse
import json
import os
import sys
from pathlib import Path


def cmd_internal(args: argparse.Namespace) -> None:
    """Dispatch internal subcommand."""
    anima_dir_str = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
    if not anima_dir_str:
        print("Error: ANIMAWORKS_ANIMA_DIR not set", file=sys.stderr)
        sys.exit(1)

    anima_dir = Path(anima_dir_str)
    if not anima_dir.is_dir():
        print(f"Error: anima_dir not found: {anima_dir}", file=sys.stderr)
        sys.exit(1)

    sub = getattr(args, "internal_command", None)
    if sub == "archive-memory":
        _cmd_archive_memory(args, anima_dir)
    elif sub == "check-permissions":
        _cmd_check_permissions(args, anima_dir)
    elif sub == "create-skill":
        _cmd_create_skill(args, anima_dir)
    elif sub == "manage-channel":
        _cmd_manage_channel(args, anima_dir)
    elif sub == "list-background-tasks":
        _cmd_list_background_tasks(args, anima_dir)
    elif sub == "check-background-task":
        _cmd_check_background_task(args, anima_dir)
    else:
        print(
            "Usage: animaworks-tool internal {archive-memory|check-permissions|create-skill|manage-channel|list-background-tasks|check-background-task}",
            file=sys.stderr,
        )
        sys.exit(1)


def _validate_memory_path(anima_dir: Path, path_str: str) -> Path | None:
    """Validate path is under knowledge/, episodes/, or procedures/ and within anima_dir."""
    if ".." in path_str or path_str.startswith("/"):
        return None
    allowed_prefixes = ("knowledge/", "episodes/", "procedures/")
    if not any(path_str.startswith(p) for p in allowed_prefixes):
        return None
    target = (anima_dir / path_str).resolve()
    base = anima_dir.resolve()
    if not str(target).startswith(str(base)):
        return None
    return target


def _cmd_archive_memory(args: argparse.Namespace, anima_dir: Path) -> None:
    path_str = getattr(args, "path", "")
    if not path_str:
        print("Error: PATH is required", file=sys.stderr)
        sys.exit(1)

    target = _validate_memory_path(anima_dir, path_str)
    if target is None:
        print("Error: invalid path (must be under knowledge/, episodes/, or procedures/)", file=sys.stderr)
        sys.exit(1)

    if not target.exists():
        print(json.dumps({"archived": False, "error": "file not found"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    if not target.is_file():
        print(json.dumps({"archived": False, "error": "not a file"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    archive_dir = anima_dir / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    dest = archive_dir / target.name
    if dest.exists():
        stem, suffix = target.stem, target.suffix
        counter = 1
        while dest.exists():
            dest = archive_dir / f"{stem}_{counter}{suffix}"
            counter += 1

    target.rename(dest)
    from_rel = path_str
    to_rel = dest.relative_to(anima_dir)
    print(
        json.dumps(
            {"archived": True, "from": from_rel, "to": str(to_rel)},
            ensure_ascii=False,
            indent=2,
        )
    )


def _cmd_check_permissions(args: argparse.Namespace, anima_dir: Path) -> None:
    tool_name = getattr(args, "tool_name", "")
    action = getattr(args, "action", None) or ""

    if not tool_name:
        print("Error: TOOL_NAME is required", file=sys.stderr)
        sys.exit(1)

    perm_path = anima_dir / "permissions.md"
    if not perm_path.is_file():
        from core.tools import TOOL_MODULES

        permitted = set(TOOL_MODULES.keys())
    else:
        from core.tooling.permissions import parse_permitted_tools

        text = perm_path.read_text(encoding="utf-8")
        permitted = parse_permitted_tools(text)

    action_key = f"{tool_name}_{action}" if action else tool_name
    tool_permitted = tool_name in permitted
    if action:
        from core.tooling.permissions import is_action_gated

        gated = is_action_gated(tool_name, action, permitted)
        action_permitted = action_key in permitted or (not gated and tool_permitted)
        result_permitted = tool_permitted and action_permitted
    else:
        result_permitted = tool_permitted

    print(
        json.dumps(
            {"tool": tool_name, "action": action or None, "permitted": result_permitted},
            ensure_ascii=False,
            indent=2,
        )
    )


def _cmd_create_skill(args: argparse.Namespace, anima_dir: Path) -> None:
    name = getattr(args, "name", "")
    content = getattr(args, "content", None)

    if not name:
        print("Error: NAME is required", file=sys.stderr)
        sys.exit(1)

    if content is None:
        content = sys.stdin.read()

    skills_dir = anima_dir / "skills"

    if ".." in name or "/" in name or "\\" in name:
        print("Error: invalid name (directory traversal not allowed)", file=sys.stderr)
        sys.exit(1)

    skill_name = name[:-3] if name.endswith(".md") else name
    if not skill_name:
        print("Error: invalid name", file=sys.stderr)
        sys.exit(1)

    skill_path = skills_dir / skill_name / "SKILL.md"

    if not str(skill_path.resolve()).startswith(str(skills_dir.resolve())):
        print("Error: invalid name (path traversal not allowed)", file=sys.stderr)
        sys.exit(1)

    skill_path.parent.mkdir(parents=True, exist_ok=True)
    skill_path.write_text(content, encoding="utf-8")
    rel_path = skill_path.relative_to(anima_dir)
    print(
        json.dumps(
            {"created": True, "path": str(rel_path)},
            ensure_ascii=False,
            indent=2,
        )
    )


def _cmd_manage_channel(args: argparse.Namespace, anima_dir: Path) -> None:
    from core.paths import get_data_dir

    action = getattr(args, "action", "")
    channel = getattr(args, "channel", "")

    if not action or not channel:
        print("Error: ACTION and CHANNEL are required", file=sys.stderr)
        sys.exit(1)

    if ".." in channel or "/" in channel:
        print("Error: invalid channel name", file=sys.stderr)
        sys.exit(1)

    data_dir = get_data_dir()
    channels_dir = data_dir / "shared" / "channels"
    channel_file = channels_dir / f"{channel}.jsonl"

    if action == "create":
        channels_dir.mkdir(parents=True, exist_ok=True)
        if channel_file.exists():
            print(
                json.dumps(
                    {"action": "create", "channel": channel, "created": False, "message": "already exists"},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            channel_file.touch()
            print(
                json.dumps(
                    {"action": "create", "channel": channel, "created": True, "path": str(channel_file)},
                    ensure_ascii=False,
                    indent=2,
                )
            )
    elif action == "archive":
        archive_dir = channels_dir / "archive"
        if not channel_file.exists():
            print(
                json.dumps(
                    {"action": "archive", "channel": channel, "archived": False, "error": "channel not found"},
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            archive_dir.mkdir(parents=True, exist_ok=True)
            dest = archive_dir / channel_file.name
            channel_file.rename(dest)
            print(
                json.dumps(
                    {"action": "archive", "channel": channel, "archived": True, "to": str(dest)},
                    ensure_ascii=False,
                    indent=2,
                )
            )
    else:
        print("Error: ACTION must be create or archive", file=sys.stderr)
        sys.exit(1)


def _cmd_list_background_tasks(args: argparse.Namespace, anima_dir: Path) -> None:
    bg_dir = anima_dir / "state" / "background_tasks"
    tasks: list[dict] = []

    for subdir in ("pending", "done"):
        sub_path = bg_dir / subdir
        if not sub_path.is_dir():
            continue
        for path in sorted(sub_path.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                data["_source"] = subdir
                tasks.append(data)
            except (json.JSONDecodeError, OSError):
                continue

    for path in sorted(bg_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if "_source" not in data:
                data["_source"] = "root"
            tasks.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    print(json.dumps(tasks, ensure_ascii=False, indent=2))


def _cmd_check_background_task(args: argparse.Namespace, anima_dir: Path) -> None:
    task_id = getattr(args, "task_id", "")
    if not task_id:
        print("Error: TASK_ID is required", file=sys.stderr)
        sys.exit(1)

    if ".." in task_id or "/" in task_id:
        print(json.dumps({"error": "invalid task_id"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    bg_dir = anima_dir / "state" / "background_tasks"
    for subdir in ("pending", "done", ""):
        base = bg_dir / subdir if subdir else bg_dir
        task_file = base / f"{task_id}.json"
        if task_file.exists():
            try:
                data = json.loads(task_file.read_text(encoding="utf-8"))
                print(json.dumps(data, ensure_ascii=False, indent=2))
                return
            except (json.JSONDecodeError, OSError) as e:
                print(json.dumps({"error": str(e)}, ensure_ascii=False, indent=2))
                sys.exit(1)

    print(json.dumps({"error": "task not found", "task_id": task_id}, ensure_ascii=False, indent=2))
    sys.exit(1)


def register_internal_command(subparsers) -> None:
    """Register the internal subcommand under animaworks-tool."""
    p_internal = subparsers.add_parser("internal", help="Internal tools for Anima use")
    internal_sub = p_internal.add_subparsers(dest="internal_command")

    p_archive = internal_sub.add_parser("archive-memory", help="Archive a memory file")
    p_archive.add_argument("path", help="Relative path (e.g. knowledge/old-notes.md)")
    p_archive.set_defaults(func=cmd_internal)

    p_check_perm = internal_sub.add_parser("check-permissions", help="Check tool permission")
    p_check_perm.add_argument("tool_name", help="Tool name")
    p_check_perm.add_argument("action", nargs="?", default="", help="Optional action")
    p_check_perm.set_defaults(func=cmd_internal)

    p_skill = internal_sub.add_parser("create-skill", help="Create a skill file")
    p_skill.add_argument("name", help="Skill name (or name.md)")
    p_skill.add_argument("--content", default=None, help="Content (default: stdin)")
    p_skill.set_defaults(func=cmd_internal)

    p_channel = internal_sub.add_parser("manage-channel", help="Create or archive a channel")
    p_channel.add_argument("action", choices=["create", "archive"], help="Action")
    p_channel.add_argument("channel", help="Channel name")
    p_channel.set_defaults(func=cmd_internal)

    p_list_bg = internal_sub.add_parser("list-background-tasks", help="List background tasks")
    p_list_bg.set_defaults(func=cmd_internal)

    p_check_bg = internal_sub.add_parser("check-background-task", help="Check a specific task")
    p_check_bg.add_argument("task_id", help="Task ID")
    p_check_bg.set_defaults(func=cmd_internal)

    p_internal.set_defaults(func=cmd_internal)
