from __future__ import annotations
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Persistent task queue manager.

Implements append-only JSONL task queue at ``{anima_dir}/state/task_queue.jsonl``.
Each line represents either a task creation or a status update event.
The current state is reconstructed by replaying the log (latest status wins).
"""

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from core.schemas import TaskEntry

logger = logging.getLogger("animaworks.task_queue")

# Valid task statuses
_VALID_STATUSES = frozenset({"pending", "in_progress", "done", "cancelled", "blocked"})
# Valid task sources
_VALID_SOURCES = frozenset({"human", "anima"})
# Maximum characters for original_instruction
_MAX_INSTRUCTION_CHARS = 10_000


class TaskQueueManager:
    """Manages a persistent task queue backed by JSONL.

    The queue file is an append-only log at ``state/task_queue.jsonl``.
    """

    def __init__(self, anima_dir: Path) -> None:
        self.anima_dir = anima_dir
        self._queue_path = anima_dir / "state" / "task_queue.jsonl"

    @property
    def queue_path(self) -> Path:
        return self._queue_path

    # ── Write operations ─────────────────────────────────────

    def add_task(
        self,
        *,
        source: str,
        original_instruction: str,
        assignee: str,
        summary: str,
        deadline: str | None = None,
        relay_chain: list[str] | None = None,
    ) -> TaskEntry:
        """Add a new task to the queue.

        Returns the created TaskEntry.

        Raises:
            ValueError: If source is not 'human' or 'anima'.
        """
        if source not in _VALID_SOURCES:
            raise ValueError(f"Invalid source: {source!r} (must be 'human' or 'anima')")
        if len(original_instruction) > _MAX_INSTRUCTION_CHARS:
            original_instruction = original_instruction[:_MAX_INSTRUCTION_CHARS]
            logger.warning("original_instruction truncated to %d chars", _MAX_INSTRUCTION_CHARS)
        now = datetime.now().isoformat()
        entry = TaskEntry(
            task_id=uuid.uuid4().hex[:12],
            ts=now,
            source=source,
            original_instruction=original_instruction,
            assignee=assignee,
            status="pending",
            summary=summary,
            deadline=deadline,
            relay_chain=relay_chain or [],
            updated_at=now,
        )
        self._append(entry.model_dump())
        logger.info(
            "Task added: id=%s source=%s assignee=%s summary=%s",
            entry.task_id, source, assignee, summary[:50],
        )
        return entry

    def update_status(
        self,
        task_id: str,
        status: str,
        *,
        summary: str | None = None,
    ) -> TaskEntry | None:
        """Update the status of an existing task.

        Appends an update event to the JSONL log.
        Returns the updated task or None if not found.
        """
        if status not in _VALID_STATUSES:
            logger.warning("Invalid task status: %s", status)
            return None

        tasks = self._load_all()
        task = tasks.get(task_id)
        if task is None:
            logger.warning("Task not found: %s", task_id)
            return None

        now = datetime.now().isoformat()
        update: dict[str, Any] = {
            "task_id": task_id,
            "status": status,
            "updated_at": now,
            "_event": "update",
        }
        if summary is not None:
            update["summary"] = summary
        self._append(update)

        # Return reconstructed entry
        task.status = status
        task.updated_at = now
        if summary is not None:
            task.summary = summary
        logger.info("Task updated: id=%s status=%s", task_id, status)
        return task

    # ── Read operations ──────────────────────────────────────

    def _load_all(self) -> dict[str, TaskEntry]:
        """Replay the JSONL log and return current task states.

        Returns dict mapping task_id to latest TaskEntry.
        Corrupted lines are skipped with a warning.
        """
        tasks: dict[str, TaskEntry] = {}
        if not self._queue_path.exists():
            return tasks

        for line in self._queue_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("Skipping corrupted task_queue line: %s", line[:80])
                continue

            task_id = raw.get("task_id", "")
            if not task_id:
                continue

            if raw.get("_event") == "update":
                # Status update event
                existing = tasks.get(task_id)
                if existing:
                    if "status" in raw:
                        existing.status = raw["status"]
                    if "summary" in raw:
                        existing.summary = raw["summary"]
                    if "updated_at" in raw:
                        existing.updated_at = raw["updated_at"]
            else:
                # Task creation event — strip internal fields
                raw.pop("_event", None)
                try:
                    tasks[task_id] = TaskEntry(**raw)
                except Exception:
                    logger.warning("Skipping invalid task entry: %s", task_id)
                    continue

        return tasks

    def get_pending(self) -> list[TaskEntry]:
        """Return tasks with status 'pending' or 'in_progress'."""
        tasks = self._load_all()
        return [
            t for t in tasks.values()
            if t.status in ("pending", "in_progress")
        ]

    def get_human_tasks(self) -> list[TaskEntry]:
        """Return pending/in_progress tasks with source='human'."""
        return [t for t in self.get_pending() if t.source == "human"]

    def get_all_active(self) -> list[TaskEntry]:
        """Return all non-terminal tasks (pending, in_progress, blocked)."""
        tasks = self._load_all()
        return [
            t for t in tasks.values()
            if t.status in ("pending", "in_progress", "blocked")
        ]

    def list_tasks(self, status: str | None = None) -> list[TaskEntry]:
        """List tasks, optionally filtered by status."""
        tasks = self._load_all()
        if status:
            return [t for t in tasks.values() if t.status == status]
        return list(tasks.values())

    # ── Formatting ───────────────────────────────────────────

    def format_for_priming(self, budget_tokens: int = 400) -> str:
        """Format pending tasks for system prompt injection.

        Human-origin tasks are displayed with 🔴 HIGH priority marker.
        """
        tasks = self.get_pending()
        if not tasks:
            return ""

        chars_per_token = 4
        max_chars = budget_tokens * chars_per_token
        lines: list[str] = []
        total = 0

        # Sort: human tasks first, then by creation time
        tasks.sort(key=lambda t: (0 if t.source == "human" else 1, t.ts))

        for task in tasks:
            priority = "🔴 HIGH" if task.source == "human" else "⚪"
            status_icon = "🔄" if task.status == "in_progress" else "📋"
            line = (
                f"- {status_icon} {priority} [{task.task_id[:8]}] "
                f"{task.summary} (assignee: {task.assignee})"
            )
            if task.relay_chain:
                line += f" chain: {' → '.join(task.relay_chain)}"
            if total + len(line) > max_chars:
                break
            lines.append(line)
            total += len(line) + 1

        return "\n".join(lines)

    # ── Maintenance ────────────────────────────────────────────

    def compact(self) -> int:
        """Rewrite JSONL file with only active (non-terminal) tasks.

        Terminal statuses (done, cancelled) are removed.
        Returns the number of tasks removed.
        """
        tasks = self._load_all()
        active = {tid: t for tid, t in tasks.items() if t.status not in ("done", "cancelled")}
        removed = len(tasks) - len(active)
        if removed == 0:
            return 0

        # Rewrite atomically via temp file
        tmp_path = self._queue_path.with_suffix(".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                for entry in active.values():
                    f.write(json.dumps(entry.model_dump(), ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(self._queue_path)
            logger.info("Task queue compacted: removed %d terminal tasks", removed)
        except Exception:
            logger.exception("Failed to compact task queue")
            tmp_path.unlink(missing_ok=True)
            removed = 0
        return removed

    # ── Internal ─────────────────────────────────────────────

    def _append(self, data: dict[str, Any]) -> None:
        """Append a JSON line to the queue file with fsync."""
        try:
            self._queue_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(data, ensure_ascii=False)
            with self._queue_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            logger.exception("Failed to append to task queue")
