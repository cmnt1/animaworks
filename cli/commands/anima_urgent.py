"""CLI commands for urgent-mode task submission."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _anima_dir(name: str) -> Path:
    from core.paths import get_animas_dir

    path = get_animas_dir() / name
    if not path.exists():
        print(f"Error: Anima '{name}' not found at {path}", file=sys.stderr)
        sys.exit(1)
    return path


def cmd_anima_urgent_submit(args: argparse.Namespace) -> None:
    """Submit an urgent task that bypasses rate limits and cooldowns.

    Writes the task to ``state/pending/`` for immediate pickup by the
    PendingTaskExecutor, registers it in ``task_queue.jsonl`` with
    ``priority=urgent``, and marks the Anima as urgent-active.
    """
    from core.memory.task_queue import TaskQueueManager
    from core.urgent import add_urgent

    anima_dir = _anima_dir(args.name)

    body: str = args.body.strip()
    if not body:
        print("Error: body must not be empty", file=sys.stderr)
        sys.exit(1)

    summary = args.summary or body.splitlines()[0][:100]
    task_id = uuid.uuid4().hex[:12]
    submitted_at = datetime.now().astimezone().isoformat(timespec="seconds")

    pending_dir = anima_dir / "state" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    task_desc = {
        "task_type": "llm",
        "task_id": task_id,
        "title": summary,
        "description": body,
        "parallel": False,
        "depends_on": [],
        "context": "",
        "acceptance_criteria": [],
        "constraints": [],
        "file_paths": [],
        "submitted_by": "human:urgent-submit",
        "submitted_at": submitted_at,
        "reply_to": "human",
        "working_directory": "",
        "priority": "urgent",
    }

    path = pending_dir / f"{task_id}.json"
    path.write_text(json.dumps(task_desc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        manager = TaskQueueManager(anima_dir)
        manager.add_task(
            source="human",
            original_instruction=body[:5000],
            assignee=args.name,
            summary=summary,
            task_id=task_id,
            status="in_progress",
            deadline=args.deadline,
            priority="urgent",
            meta={
                "executor": "taskexec",
                "urgent": True,
                "submitted_via": "cli:urgent-submit",
            },
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("task_queue registration failed: %s", exc)

    add_urgent(anima_dir, task_id, note=f"cli:urgent-submit from human")

    print(f"[urgent] submitted task {task_id} to {args.name}")
    print(f"  summary: {summary}")
    print(f"  file: {path}")
    print("  throttles (rate limits, cooldowns, activity scaling) bypassed until completion.")


def cmd_anima_urgent_status(args: argparse.Namespace) -> None:
    """Show active urgent tasks for the given Anima."""
    from core.urgent import _load  # noqa: PLC2701

    anima_dir = _anima_dir(args.name)
    data = _load(anima_dir)
    if not data:
        print(f"[{args.name}] no active urgent tasks")
        return
    print(f"[{args.name}] {len(data)} active urgent task(s):")
    for task_id, info in data.items():
        added = info.get("added_at", "?")
        note = info.get("note", "") or ""
        print(f"  {task_id}  added={added}  {note}")


def cmd_anima_urgent_clear(args: argparse.Namespace) -> None:
    """Clear all active urgent tasks for the given Anima (emergency reset)."""
    from core.urgent import clear_urgent

    anima_dir = _anima_dir(args.name)
    clear_urgent(anima_dir)
    print(f"[{args.name}] all urgent tasks cleared")
