from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI subcommands for supervisor tools invoked via animaworks-tool supervisor.

Usage via animaworks-tool:
    animaworks-tool supervisor org-dashboard
    animaworks-tool supervisor ping [--name NAME]
    animaworks-tool supervisor read-state NAME
    animaworks-tool supervisor task-tracker [--status STATUS]
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from core.paths import get_data_dir

logger = logging.getLogger("animaworks")


def _get_anima_dir() -> Path:
    anima_dir_str = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
    if not anima_dir_str:
        print("Error: ANIMAWORKS_ANIMA_DIR not set", file=sys.stderr)
        sys.exit(1)
    anima_dir = Path(anima_dir_str)
    if not anima_dir.is_dir():
        print(f"Error: anima_dir not found: {anima_dir}", file=sys.stderr)
        sys.exit(1)
    return anima_dir


def _load_supervisor_map(animas_dir: Path) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    if not animas_dir.is_dir():
        return result
    from core.config.models import read_anima_supervisor

    for child in animas_dir.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            result[child.name] = read_anima_supervisor(child)
    return result


def _get_descendants(supervisor_map: dict[str, str | None], root: str) -> list[str]:
    visited: set[str] = {root}
    queue = [n for n, sup in supervisor_map.items() if sup == root]
    result: list[str] = []
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        result.append(current)
        queue.extend(n for n, sup in supervisor_map.items() if sup == current)
    return result


def _is_ancestor(supervisor_map: dict[str, str | None], ancestor: str, name: str) -> bool:
    if ancestor == name:
        return True
    current: str | None = name
    visited: set[str] = set()
    while current and current not in visited:
        visited.add(current)
        if current == ancestor:
            return True
        current = supervisor_map.get(current)
    return False


def cmd_supervisor(args: argparse.Namespace) -> None:
    """Dispatch supervisor subcommand."""
    sub = getattr(args, "supervisor_command", None)
    if sub == "org-dashboard":
        _cmd_org_dashboard(args)
    elif sub == "ping":
        _cmd_ping(args)
    elif sub == "read-state":
        _cmd_read_state(args)
    elif sub == "task-tracker":
        _cmd_task_tracker(args)
    else:
        print(
            "Usage: animaworks-tool supervisor {org-dashboard|ping|read-state|task-tracker}",
            file=sys.stderr,
        )
        sys.exit(1)


def _cmd_org_dashboard(args: argparse.Namespace) -> None:
    anima_dir = _get_anima_dir()
    caller_name = anima_dir.name
    data_dir = get_data_dir()
    animas_dir = data_dir / "animas"
    sockets_dir = data_dir / "run" / "sockets"

    supervisor_map = _load_supervisor_map(animas_dir)
    descendants = _get_descendants(supervisor_map, caller_name)

    def _node(name: str) -> dict:
        desc_dir = animas_dir / name
        current_task = ""
        current_task_path = desc_dir / "state" / "current_task.md"
        if current_task_path.exists():
            try:
                current_task = current_task_path.read_text(encoding="utf-8").strip()
            except OSError:
                pass

        sock_path = sockets_dir / f"{name}.sock"
        alive = sock_path.exists()

        last_activity_time: str | None = None
        activity_dir = desc_dir / "activity_log"
        if activity_dir.exists():
            from core.memory.activity import ActivityLogger

            al = ActivityLogger(desc_dir)
            entries = al.recent(days=1, limit=1)
            if entries:
                last_activity_time = entries[-1].ts

        return {
            "name": name,
            "status": "alive" if alive else "stopped",
            "current_task": current_task or None,
            "last_activity_time": last_activity_time,
        }

    tree: list[dict] = []
    for name in descendants:
        tree.append(_node(name))

    result = {"caller": caller_name, "descendants": tree}
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_ping(args: argparse.Namespace) -> None:
    anima_dir = _get_anima_dir()
    caller_name = anima_dir.name
    data_dir = get_data_dir()
    animas_dir = data_dir / "animas"
    sockets_dir = data_dir / "run" / "sockets"

    target_name = getattr(args, "name", None)
    if target_name:
        if ".." in target_name or "/" in target_name or "\\" in target_name:
            print("Error: invalid target name", file=sys.stderr)
            sys.exit(1)
        targets = [target_name]
    else:
        supervisor_map = _load_supervisor_map(animas_dir)
        targets = _get_descendants(supervisor_map, caller_name)

    result: list[dict] = []
    for name in targets:
        sock_path = sockets_dir / f"{name}.sock"
        alive = sock_path.exists()
        result.append({"name": name, "alive": alive})
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_read_state(args: argparse.Namespace) -> None:
    target_name = getattr(args, "name", "")
    if not target_name:
        print("Error: NAME is required", file=sys.stderr)
        sys.exit(1)

    if ".." in target_name or "/" in target_name or "\\" in target_name:
        print("Error: invalid target name", file=sys.stderr)
        sys.exit(1)

    anima_dir = _get_anima_dir()
    caller_name = anima_dir.name
    data_dir = get_data_dir()
    animas_dir = data_dir / "animas"

    supervisor_map = _load_supervisor_map(animas_dir)
    if not _is_ancestor(supervisor_map, caller_name, target_name):
        print(
            f"Error: {caller_name} is not an ancestor of {target_name}",
            file=sys.stderr,
        )
        sys.exit(1)

    target_dir = animas_dir / target_name
    current_task = ""
    pending = ""
    current_task_path = target_dir / "state" / "current_task.md"
    pending_path = target_dir / "state" / "pending.md"
    if current_task_path.exists():
        try:
            current_task = current_task_path.read_text(encoding="utf-8").strip()
        except OSError:
            pass
    if pending_path.exists():
        try:
            pending = pending_path.read_text(encoding="utf-8").strip()
        except OSError:
            pass

    result = {"current_task": current_task or None, "pending": pending or None}
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_task_tracker(args: argparse.Namespace) -> None:
    anima_dir = _get_anima_dir()
    status_filter = getattr(args, "status", "delegated")

    from core.memory.task_queue import TaskQueueManager

    manager = TaskQueueManager(anima_dir)
    tasks = manager.list_tasks(status=status_filter)
    result = [t.model_dump() for t in tasks]
    print(json.dumps(result, ensure_ascii=False, indent=2))


def register_supervisor_command(subparsers) -> None:
    """Register the supervisor subcommand under animaworks-tool."""
    p_supervisor = subparsers.add_parser("supervisor", help="Supervisor tools for animas")
    sup_sub = p_supervisor.add_subparsers(dest="supervisor_command")

    sup_sub.add_parser("org-dashboard", help="Show org tree with status and tasks")

    p_ping = sup_sub.add_parser("ping", help="Check if subordinate animas are alive")
    p_ping.add_argument("--name", default=None, help="Specific anima name (omit for all subordinates)")

    p_read = sup_sub.add_parser("read-state", help="Read subordinate state (current_task, pending)")
    p_read.add_argument("name", help="Target anima name")

    p_tracker = sup_sub.add_parser("task-tracker", help="Track delegated tasks")
    p_tracker.add_argument(
        "--status",
        default="delegated",
        help="Filter by status (default: delegated)",
    )

    p_supervisor.set_defaults(func=cmd_supervisor)
