from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Helpers for re-queueing TaskExec tasks from task_queue state."""

import json
import logging
from pathlib import Path
from typing import Any

from core.memory.task_queue import TaskQueueManager
from core.schemas import TaskEntry
from core.time_utils import now_iso

logger = logging.getLogger("animaworks.task_retry")

MAX_TASK_RETRY = 3
_TERMINAL_STATUSES = {"done", "cancelled", "failed"}


class TaskRetryError(RuntimeError):
    """Raised when a task cannot be safely retried."""


class TaskRetrySuppressedError(TaskRetryError):
    """Raised when TaskBoard attention metadata suppresses a retry."""


def retry_task(
    anima_dir: Path,
    task_id: str,
    *,
    summary: str | None = None,
    submitted_by: str | None = None,
    max_retries: int = MAX_TASK_RETRY,
) -> TaskEntry:
    """Mark a task for retry and regenerate its pending TaskExec JSON.

    The task is moved through ``pending`` and then ``in_progress`` so existing
    TaskBoard/queue projections see that work has been re-submitted.
    """

    manager = TaskQueueManager(anima_dir)
    entry = manager.get_task_by_id(task_id)
    if entry is None:
        raise TaskRetryError(f"Task not found: {task_id}")
    if entry.status in _TERMINAL_STATUSES:
        raise TaskRetryError(f"Task {task_id} is terminal ({entry.status}); not retrying")
    suppression_reason = _retry_suppression_reason(entry)
    if suppression_reason:
        raise TaskRetryError(f"Task {task_id} is not retryable: {suppression_reason}")

    regenerated = regenerate_pending_json(
        anima_dir,
        entry,
        submitted_by=submitted_by,
        max_retries=max_retries,
    )
    if not regenerated:
        raise TaskRetryError(f"Task {task_id} could not be regenerated for retry")

    display_summary = _retry_display_summary(manager.queue_path, entry)
    manager.update_status(task_id, "pending", summary=display_summary, note=summary)
    updated = manager.update_status(task_id, "in_progress", summary=display_summary)
    if updated is None:
        raise TaskRetryError(f"Task not found after retry regeneration: {task_id}")
    return updated


def regenerate_pending_json(
    anima_dir: Path,
    entry: TaskEntry,
    *,
    submitted_by: str | None = None,
    max_retries: int = MAX_TASK_RETRY,
) -> bool:
    """Regenerate ``state/pending/{task_id}.json`` for a queue task."""

    pending_dir = anima_dir / "state" / "pending"
    processing_dir = pending_dir / "processing"
    task_file = f"{entry.task_id}.json"

    suppression_reason = _retry_suppression_reason(entry)
    if suppression_reason:
        raise TaskRetryError(f"Task {entry.task_id} is not retryable: {suppression_reason}")

    if (pending_dir / task_file).exists() or (processing_dir / task_file).exists():
        logger.warning("Task %s already in pipeline, skip regeneration", entry.task_id)
        return True

    decision = _retry_attention_decision(anima_dir, entry.task_id)
    if not getattr(decision, "executable", True):
        raise TaskRetrySuppressedError(f"Task {entry.task_id} is suppressed by TaskBoard: {decision.reason}")

    retry_count = _coerce_retry_count((entry.meta or {}).get("retry_count"))
    if retry_count >= max_retries:
        logger.warning("Task %s exceeded max retries (%d), skip", entry.task_id, max_retries)
        return False

    next_retry_count = retry_count + 1
    manager = TaskQueueManager(anima_dir)
    updated = manager.update_meta(entry.task_id, {"retry_count": next_retry_count})
    if updated is not None:
        entry = updated

    task_desc = _build_task_desc(entry, submitted_by=submitted_by)
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / task_file
    path.write_text(json.dumps(task_desc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("Regenerated pending JSON for retry: %s", entry.task_id)
    return True


def _build_task_desc(entry: TaskEntry, *, submitted_by: str | None = None) -> dict[str, Any]:
    meta = entry.meta or {}
    task_desc_meta = meta.get("task_desc")
    if not isinstance(task_desc_meta, dict):
        task_desc_meta = {}

    task_desc = dict(task_desc_meta)
    task_desc.update(
        {
            "task_type": task_desc_meta.get("task_type", "llm"),
            "task_id": entry.task_id,
            "batch_id": task_desc_meta.get("batch_id", meta.get("batch_id", "")),
            "title": task_desc_meta.get("title", _retry_title(entry)),
            "description": task_desc_meta.get("description", entry.original_instruction),
            "parallel": False,
            "depends_on": [],
            "context": task_desc_meta.get("context", ""),
            "acceptance_criteria": task_desc_meta.get("acceptance_criteria", []),
            "constraints": task_desc_meta.get("constraints", []),
            "file_paths": task_desc_meta.get("file_paths", []),
            "submitted_by": submitted_by or task_desc_meta.get("submitted_by") or entry.assignee,
            "submitted_at": now_iso(),
            "reply_to": task_desc_meta.get("reply_to", submitted_by or entry.assignee),
            "working_directory": task_desc_meta.get("working_directory", ""),
            "source": task_desc_meta.get("source", "retry"),
            "priority": task_desc_meta.get("priority", entry.priority),
            "allow_multistage": bool(task_desc_meta.get("allow_multistage")),
        }
    )
    return task_desc


def _retry_attention_decision(anima_dir: Path, task_id: str):
    try:
        from core.taskboard.attention_resolver import resolver_for_anima_dir

        return resolver_for_anima_dir(anima_dir).should_execute(
            anima_dir.name,
            task_id,
            queue_status="pending",
        )
    except Exception:
        logger.warning("TaskBoard retry gate unavailable for task %s; failing open", task_id, exc_info=True)
        from core.taskboard.models import AttentionDecision

        return AttentionDecision(reason="active")


def _coerce_retry_count(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _retry_suppression_reason(entry: TaskEntry) -> str | None:
    meta = entry.meta or {}
    if bool(meta.get("needs_human")):
        return "needs_human"
    reason = meta.get("do_not_retry_reason")
    if isinstance(reason, str) and reason.strip():
        return reason.strip()
    superseded_by = meta.get("superseded_by")
    if isinstance(superseded_by, str) and superseded_by.strip():
        return f"superseded_by {superseded_by.strip()}"
    return None


def _retry_display_summary(queue_path: Path, entry: TaskEntry) -> str:
    """Return a human task title for a retried card, not retry plumbing text."""
    historical_summary = _last_human_summary(queue_path, entry.task_id)
    if historical_summary:
        return historical_summary

    meta = entry.meta or {}
    task_desc = meta.get("task_desc")
    if isinstance(task_desc, dict):
        title = task_desc.get("title")
        if isinstance(title, str) and title.strip() and not _is_retry_plumbing_summary(title):
            return title.strip()

    return _retry_title(entry)


def _last_human_summary(queue_path: Path, task_id: str) -> str | None:
    if not queue_path.exists():
        return None

    candidate: str | None = None
    raw_text = queue_path.read_bytes().decode("utf-8", errors="replace")
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if raw.get("task_id") != task_id:
            continue
        summary = raw.get("summary")
        if isinstance(summary, str) and summary.strip() and not _is_retry_plumbing_summary(summary):
            candidate = summary.strip()
    return candidate


def _is_retry_plumbing_summary(summary: str) -> bool:
    text = summary.strip()
    lowered = text.casefold()
    if lowered.startswith(("blocked:", "failed:")):
        return True
    return any(
        marker in lowered
        for marker in (
            "retry queued",
            "auto retry queued",
            "recovered orphaned processing task",
            "tool call(s)",
            "自動再実行待ち",
            "再実行待ち",
        )
    )


def _retry_title(entry: TaskEntry) -> str:
    summary = (entry.summary or "").strip()
    if summary.casefold().startswith(("blocked:", "failed:")):
        return (entry.original_instruction or summary)[:100]
    return summary or (entry.original_instruction or entry.task_id)[:100]
