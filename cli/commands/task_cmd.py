from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI subcommand for task queue management (A1 mode).

Usage via animaworks-tool:
    animaworks-tool task add --source human --instruction "..." --assignee rin
    animaworks-tool task update --task-id abc123 --status in_progress
    animaworks-tool task list [--status pending]
"""

import argparse
import json
import os
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path


def cmd_task(args: argparse.Namespace) -> None:
    """Dispatch task subcommand."""
    sub = getattr(args, "task_command", None)
    if sub == "board":
        _cmd_board(args)
        return
    if sub == "show":
        _cmd_show(args)
        return
    if sub in {"claim", "release", "done", "cancel", "note"}:
        _cmd_lease_action(args)
        return

    anima_dir_str = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
    if not anima_dir_str:
        print(
            "Error: ANIMAWORKS_ANIMA_DIR not set.\n"
            "`animaworks-tool task` runs inside an anima's tool context (the server sets this variable).\n"
            "To hand work to an anima from outside, use:\n"
            '  animaworks send <your-name> <anima> "<instruction>"',
            file=sys.stderr,
        )
        sys.exit(1)

    anima_dir = Path(anima_dir_str)
    if not anima_dir.is_dir():
        print(f"Error: anima_dir not found: {anima_dir}", file=sys.stderr)
        sys.exit(1)

    from core.memory.task_queue import TaskQueueManager

    manager = TaskQueueManager(anima_dir)

    if sub == "add":
        _cmd_add(args, manager)
    elif sub == "update":
        _cmd_update(args, manager)
    elif sub == "resume":
        _cmd_resume(args, manager)
    elif sub == "list":
        _cmd_list(args, manager)
    else:
        print(
            "Usage: animaworks-tool task {board|show|claim|release|done|cancel|note|add|update|resume|list}",
            file=sys.stderr,
        )
        sys.exit(1)


def _get_task_store():
    from core.taskboard.board_actions import get_task_store

    return get_task_store()


def _find_task_matches(store, task_id: str, owner: str | None = None) -> list[dict]:
    from core.taskboard.board_actions import find_task_matches

    return find_task_matches(store, task_id, owner)


def _resolve_task(store, task_id: str) -> dict:
    from core.taskboard.board_actions import BoardActionError, resolve_task

    try:
        return resolve_task(store, task_id)
    except BoardActionError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        sys.exit(exc.exit_code)


def _task_details(store, match: dict) -> dict:
    owner, task_id = match["anima"], match["task_id"]
    with store.reader() as db:
        attempts = [
            dict(row)
            for row in db.execute(
                "SELECT number,started_at,ended_at,stop_kind,result_ref FROM task_attempts "
                "WHERE anima=? AND task_id=? ORDER BY number",
                (owner, task_id),
            )
        ]
        aliases = [
            dict(row)
            for row in db.execute(
                "SELECT viewer,alias FROM task_aliases WHERE anima=? AND task_id=? ORDER BY viewer,alias",
                (owner, task_id),
            )
        ]
    return {
        "requested_id": match["requested_id"],
        "owner": owner,
        "task_id": task_id,
        "entry": match["entry"],
        "attempts": attempts,
        "lease": store.get_lease(owner, task_id),
        "aliases": aliases,
    }


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _format_age(value: str | None, now: datetime | None = None) -> str:
    updated = _parse_timestamp(value)
    if updated is None:
        return "?"
    seconds = max(0, int(((now or datetime.now(UTC)) - updated).total_seconds()))
    if seconds >= 86400:
        return f"{seconds // 86400}d"
    if seconds >= 3600:
        return f"{seconds // 3600}h"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def _remaining_lease(expires_at: str, now: datetime | None = None) -> str:
    expiry = _parse_timestamp(expires_at)
    if expiry is None:
        return "?"
    seconds = max(0, int((expiry - (now or datetime.now(UTC))).total_seconds()))
    if seconds >= 3600:
        return f"{seconds // 3600}h"
    if seconds >= 60:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def _cmd_board(args: argparse.Namespace) -> None:
    from core.paths import get_animas_dir

    store = _get_task_store()
    actor_dir = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
    if actor_dir and not Path(actor_dir).is_dir():
        print(f"Error: anima_dir not found: {actor_dir}", file=sys.stderr)
        sys.exit(1)
    actor = Path(actor_dir).name if actor_dir else None
    requested_owner = getattr(args, "anima", None)
    all_owners = bool(getattr(args, "all", False))
    if requested_owner:
        owner_filter = requested_owner
        viewer = requested_owner
    elif all_owners or actor is None:
        owner_filter = None
        viewer = None
    else:
        owner_filter = actor
        viewer = actor
    if viewer and not (get_animas_dir() / viewer).is_dir():
        print(f"Error: anima_dir not found: {get_animas_dir() / viewer}", file=sys.stderr)
        sys.exit(1)

    rows = store.board_rows(anima=owner_filter, viewer=viewer)
    now = datetime.now(UTC)
    stale_days = getattr(args, "stale", None)
    if stale_days is not None:
        if stale_days < 0:
            print("Error: --stale must be non-negative", file=sys.stderr)
            sys.exit(2)
        cutoff = now - timedelta(days=stale_days)
        rows = [
            row
            for row in rows
            if (updated := _parse_timestamp(row.get("updated_at") or row.get("ts"))) is not None and updated <= cutoff
        ]

    def group(row: dict) -> int:
        if row.get("waiting") or row.get("status") == "delegated":
            return 2
        return 0 if row.get("status") == "in_progress" else 1

    min_time = datetime.min.replace(tzinfo=UTC)
    rows.sort(
        key=lambda row: (
            group(row),
            _parse_timestamp(row.get("updated_at") or row.get("ts")) or min_time,
            row.get("task_id", ""),
        )
    )
    counts = {
        "todo": sum(1 for row in rows if group(row) == 1),
        "running": sum(1 for row in rows if group(row) == 0),
        "waiting": sum(1 for row in rows if group(row) == 2),
    }
    limit = getattr(args, "limit", 50)
    if limit < 1:
        print("Error: --limit must be at least 1", file=sys.stderr)
        sys.exit(2)
    visible, more = rows[:limit], max(0, len(rows) - limit)
    if getattr(args, "json", False):
        print(json.dumps({"counts": counts, "tasks": visible, "more": more}, ensure_ascii=False, indent=2))
        return
    print(f"todo {counts['todo']} / running {counts['running']} / waiting {counts['waiting']}")
    for row in visible:
        state = "waiting" if group(row) == 2 else ("running" if group(row) == 0 else "todo")
        lease = row.get("lease")
        lock = f"{lease['holder']} ({_remaining_lease(lease['expires_at'], now)})" if lease else "-"
        summary = str(row.get("summary", "")).replace("\n", " ")[:80]
        age = _format_age(row.get("updated_at") or row.get("ts"), now)
        print(f"{row['task_id']}  {row['anima']}  {state}  {age}  {lock}  {summary}")
    if more:
        print(f"… {more} more (use --limit)")


def _cmd_show(args: argparse.Namespace) -> None:
    store = _get_task_store()
    task_id = args.task_id
    owner_filter = getattr(args, "anima", None)
    matches = _find_task_matches(store, task_id, owner_filter)
    if not matches:
        print(f"Error: task not found: {task_id}", file=sys.stderr)
        sys.exit(1)
    if len(matches) > 1:
        owners = ", ".join(f"{item['anima']}/{item['task_id']}" for item in matches)
        print(f"Error: task ID is ambiguous ({owners}); specify --anima OWNER", file=sys.stderr)
        sys.exit(2)
    details = _task_details(store, matches[0])
    if getattr(args, "json", False):
        print(json.dumps(details, ensure_ascii=False, indent=2))
        return
    entry = details["entry"]
    print(f"Task: {details['requested_id']} (owner: {details['owner']}, canonical ID: {details['task_id']})")
    print(f"Summary: {entry.get('summary', '')}")
    print(f"Status: {entry.get('status', '')}  Assignee: {entry.get('assignee', '')}")
    print(f"Created: {entry.get('ts', '')}  Updated: {entry.get('updated_at', '')}")
    print("Original instruction:")
    print(entry.get("original_instruction", ""))
    print("Meta:")
    print(json.dumps(entry.get("meta", {}), ensure_ascii=False, indent=2))
    print("Attempts:")
    print(json.dumps(details["attempts"], ensure_ascii=False, indent=2))
    print(f"Lease: {json.dumps(details['lease'], ensure_ascii=False) if details['lease'] else '-'}")
    print("Delegator aliases:")
    print(json.dumps(details["aliases"], ensure_ascii=False, indent=2))


def _parse_ttl(value: str) -> int:
    match = re.fullmatch(r"(\d+)([smh])", value.strip().lower())
    if not match:
        raise ValueError("TTL must use seconds, minutes, or hours (for example 30m)")
    amount = int(match.group(1))
    seconds = amount * {"s": 1, "m": 60, "h": 3600}[match.group(2)]
    if seconds <= 0 or seconds > 4 * 3600:
        raise ValueError("TTL must be greater than 0 and no more than 4h")
    return seconds


def _actor() -> str:
    actor_dir = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
    if not actor_dir:
        return "human"
    path = Path(actor_dir)
    if not path.is_dir():
        print(f"Error: anima_dir not found: {path}", file=sys.stderr)
        sys.exit(1)
    return path.name


def _post_board_action(payload: dict) -> dict:
    """Run the action on the host when the sandbox cannot write the task DB."""
    import httpx

    from core.tasks_dispatch import _server_url

    response = httpx.post(f"{_server_url()}/api/internal/task-board-action", json=payload, timeout=60.0)
    response.raise_for_status()
    return response.json()


def _cmd_lease_action(args: argparse.Namespace) -> None:
    from core.taskboard.board_actions import BoardActionError, run_board_action
    from core.tasks_dispatch import is_task_permission_error

    as_json = getattr(args, "json", False)
    action = args.task_command
    ttl_seconds = None
    if action == "claim":
        try:
            ttl_seconds = _parse_ttl(args.ttl)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(2)
    text = {"note": getattr(args, "text", None), "done": getattr(args, "note", None)}.get(
        action, getattr(args, "reason", None)
    )
    payload = {"actor": _actor(), "action": action, "task_id": args.task_id, "ttl_seconds": ttl_seconds, "text": text}

    try:
        result = run_board_action(**payload)
    except BoardActionError as exc:
        _exit_board_error(exc.message, exc.exit_code, exc.payload, as_json)
    except Exception as exc:
        if not is_task_permission_error(exc):
            raise
        try:
            response = _post_board_action(payload)
        except Exception as post_exc:
            print(f"Error: task DB is read-only here and the server fallback failed: {post_exc}", file=sys.stderr)
            sys.exit(3)
        if not response.get("ok"):
            _exit_board_error(
                str(response.get("error", "board action failed")),
                int(response.get("exit_code", 1)),
                response.get("payload"),
                as_json,
            )
        result = response["result"]

    if result.get("warning"):
        print(f"Warning: {result['warning']}", file=sys.stderr)
    if as_json:
        print(json.dumps({k: v for k, v in result.items() if k != "message"}, ensure_ascii=False, indent=2))
    else:
        print(result["message"])


def _exit_board_error(message: str, exit_code: int, payload: dict | None, as_json: bool) -> None:
    if as_json and payload is not None:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(f"Error: {message}" if not message.startswith("Lease held") else message, file=sys.stderr)
    sys.exit(exit_code)


def _cmd_add(args: argparse.Namespace, manager) -> None:
    from core.tasks_dispatch import publish_tasks
    from core.workspace import resolve_workspace

    source = getattr(args, "source", "anima")
    instruction = getattr(args, "instruction", "")
    assignee = getattr(args, "assignee", "")
    summary = getattr(args, "summary", "") or instruction[:100]
    relay_chain_raw = getattr(args, "relay_chain", None)
    relay_chain = relay_chain_raw.split(",") if relay_chain_raw else []
    workspace_raw = getattr(args, "workspace", None)

    if not instruction:
        print("Error: --instruction is required", file=sys.stderr)
        sys.exit(1)
    if not assignee:
        print("Error: --assignee is required", file=sys.stderr)
        sys.exit(1)

    # 1-1: This CLI only adds to your own queue. Foreign assignees would land
    # in another anima's ledger while the descriptor is written to this one.
    anima_name = manager.anima_dir.name
    if assignee != anima_name:
        print(
            f"Error: --assignee must be '{anima_name}'. This command only adds tasks to your own queue.\n"
            "To hand work to another anima, use the delegate_task tool instead.",
            file=sys.stderr,
        )
        sys.exit(2)

    # 1-3: optional workspace resolution
    resolved_wd = ""
    if workspace_raw:
        try:
            resolved_wd = str(resolve_workspace(workspace_raw))
        except ValueError as e:
            print(f"Error: workspace resolution failed: {e}", file=sys.stderr)
            sys.exit(2)

    submitted_by = relay_chain[0] if relay_chain else anima_name
    task_desc = {
        "task_type": "llm",
        "task_id": uuid.uuid4().hex[:12],
        "title": summary,
        "description": instruction,
        "context": "",
        "acceptance_criteria": [],
        "constraints": [],
        "file_paths": [],
        "submitted_by": submitted_by,
        "submitted_at": datetime.now(UTC).isoformat(),
        "reply_to": submitted_by,
        "source": "cli",
        "working_directory": resolved_wd,
        "model": "",
    }
    try:
        entry = publish_tasks(manager.anima_dir, [task_desc], source=source, meta={"relay_chain": relay_chain})[0]
    except Exception as e:
        print(f"Error: failed to submit task: {e}", file=sys.stderr)
        sys.exit(3)

    result = entry.model_dump()
    result["executable"] = True
    result["note"] = "picked up by the pending watcher within a few seconds"
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_update(args: argparse.Namespace, manager) -> None:
    from core.i18n import t
    from core.tasks_dispatch import update_task

    task_id = getattr(args, "task_id", "")
    status = getattr(args, "status", "")
    summary = getattr(args, "summary", None)

    if not task_id:
        print("Error: --task-id is required", file=sys.stderr)
        sys.exit(1)
    if not status:
        print("Error: --status is required", file=sys.stderr)
        sys.exit(1)
    if status == "in_progress":
        print(
            "Error: status 'in_progress' is written only by the running TaskExec.\n"
            "To (re)start a task, submit it with the submit_tasks tool. To close it, use --status done or cancelled.",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        entry = update_task(manager, task_id, status, summary=summary)
    except Exception as exc:
        print(t("tooling.task_update_failed", error=str(exc)), file=sys.stderr)
        sys.exit(3)
    if entry is None:
        print(f"Error: task not found or invalid status: {task_id}", file=sys.stderr)
        sys.exit(1)

    result = entry.model_dump()
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_resume(args: argparse.Namespace, manager) -> None:
    """Requeue a task under the same task_id using its saved execution input."""
    from core.tasks_dispatch import update_task

    task_id = getattr(args, "task_id", "")

    if not task_id:
        print("Error: --task-id is required", file=sys.stderr)
        sys.exit(1)

    try:
        entry = update_task(manager, task_id, "pending", resume=True)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(3)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(4)
    if entry is None:
        print(f"Error: task not found or invalid status: {task_id}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(entry.model_dump(), ensure_ascii=False, indent=2))


def _cmd_list(args: argparse.Namespace, manager) -> None:
    from core.memory.task_queue import mark_executability

    status_filter = getattr(args, "status", None)
    tasks = manager.list_tasks(status=status_filter)
    result = [t.model_dump() for t in tasks]
    mark_executability(result, manager.anima_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def register_task_command(subparsers) -> None:
    """Register the task subcommand under animaworks-tool."""
    p_task = subparsers.add_parser("task", help="Manage persistent task queue")
    task_sub = p_task.add_subparsers(dest="task_command")

    # Read-only board inspection is also available to human operators without an anima context.
    p_board = task_sub.add_parser("board", help="List active tasks across the task board")
    board_scope = p_board.add_mutually_exclusive_group()
    board_scope.add_argument("--anima", default=None, help="Show an owner's tasks and delegated work")
    board_scope.add_argument("--all", action="store_true", help="Show all owners")
    p_board.add_argument("--stale", type=float, default=None, help="Only tasks older than DAYS")
    p_board.add_argument("--limit", type=int, default=50, help="Maximum rows (default: 50)")
    p_board.add_argument("--json", action="store_true", help="Emit JSON")

    p_show = task_sub.add_parser("show", help="Show complete task details")
    p_show.add_argument("task_id", help="Task ID or delegator alias")
    p_show.add_argument("--anima", default=None, help="Disambiguate by task owner")
    p_show.add_argument("--json", action="store_true", help="Emit JSON")

    p_claim = task_sub.add_parser("claim", help="Acquire a time-limited task lease")
    p_claim.add_argument("task_id")
    p_claim.add_argument("--ttl", default="30m", help="Lease duration up to 4h (default: 30m)")
    p_claim.add_argument("--json", action="store_true", help="Emit JSON")

    p_release = task_sub.add_parser("release", help="Release your task lease")
    p_release.add_argument("task_id")
    p_release.add_argument("--json", action="store_true", help="Emit JSON")

    p_done = task_sub.add_parser("done", help="Mark a task done")
    p_done.add_argument("task_id")
    p_done.add_argument("--note", required=True)
    p_done.add_argument("--json", action="store_true", help="Emit JSON")

    p_cancel = task_sub.add_parser("cancel", help="Cancel a task")
    p_cancel.add_argument("task_id")
    p_cancel.add_argument("--reason", required=True)
    p_cancel.add_argument("--json", action="store_true", help="Emit JSON")

    p_note = task_sub.add_parser("note", help="Append a note to a task")
    p_note.add_argument("task_id")
    p_note.add_argument("text")
    p_note.add_argument("--json", action="store_true", help="Emit JSON")

    # task add
    p_add = task_sub.add_parser("add", help="Add a new task")
    p_add.add_argument("--source", default="anima", choices=["human", "anima"])
    p_add.add_argument("--instruction", required=True, help="Original instruction text")
    p_add.add_argument("--assignee", required=True, help="Assignee anima name")
    p_add.add_argument("--summary", default=None, help="1-line summary (default: instruction[:100])")
    p_add.add_argument("--relay-chain", default=None, help="Comma-separated relay chain")
    p_add.add_argument("--workspace", default=None, help="Workspace alias or path for the task's working_directory")

    # task update
    p_update = task_sub.add_parser("update", help="Update task status")
    p_update.add_argument("--task-id", required=True, help="Task ID")
    p_update.add_argument("--status", required=True, choices=["pending", "delegated", "done", "cancelled"])
    p_update.add_argument("--summary", default=None, help="Updated summary")

    # task resume
    p_resume = task_sub.add_parser("resume", help="Requeue a task with its saved execution input")
    p_resume.add_argument("--task-id", required=True, help="Task ID")

    # task list
    p_list = task_sub.add_parser("list", help="List tasks")
    p_list.add_argument("--status", default=None, choices=["pending", "in_progress", "delegated", "done", "cancelled"])

    p_task.set_defaults(func=cmd_task)
