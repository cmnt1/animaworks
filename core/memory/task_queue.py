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
import re
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from core.exceptions import TaskPersistenceError as TaskPersistenceError  # noqa: F401
from core.i18n import t
from core.schemas import TaskEntry
from core.time_utils import ensure_aware, now_iso, now_local

logger = logging.getLogger("animaworks.task_queue")

# Valid task statuses
_VALID_STATUSES = frozenset({"pending", "in_progress", "done", "cancelled", "blocked", "delegated", "failed"})
_TERMINAL_STATUSES = frozenset({"done", "cancelled", "failed"})
_ACTIVE_STATUSES = frozenset({"pending", "in_progress", "blocked", "delegated"})
_DELEGATION_TRACKING_STATUSES = frozenset({"delegated", "blocked"})

# Valid task sources
_VALID_SOURCES = frozenset({"human", "anima"})
# Maximum characters for original_instruction
_MAX_INSTRUCTION_CHARS = 10_000
# Stale task threshold: 30 minutes (one heartbeat cycle)
_STALE_TASK_THRESHOLD_SEC = 1800
# Relative deadline pattern: digits + unit (m=minutes, h=hours, d=days)
_RELATIVE_DEADLINE_RE = re.compile(r"^(\d+)([mhd])$")
_HEARTBEAT_OBSERVATION_PREFIX_RE = re.compile(r"^\s*(?:\d{1,2}:\d{2}\s*(?:jst)?\s*)?(?:hb|heartbeat)\s*:", re.I)
_TIMED_OBSERVATION_PREFIX_RE = re.compile(r"^\s*\d{1,2}:\d{2}\s*jst\b", re.I)
_STATUS_REPORT_SUMMARY_MAX_CHARS = 120
_STATUS_REPORT_MARKERS = (
    "原因",
    "修正済み",
    "実装",
    "テスト済み",
    "登録済み",
    "記録済み",
    "対応済み",
    "確認済み",
    "再起動済み",
    "恒久対応",
    "検証済み",
    "root cause",
    "fixed",
    "implemented",
    "verified",
)
_OBSERVATION_LOG_MARKERS = (
    "inbox",
    "未読",
    "governor",
    "pending",
    "background",
    "通知",
    "直近活動",
    "新規未着",
    "重複通知",
    "検収待機",
    "待機",
    "件",
)


def _is_observation_log_summary(summary: str | None) -> bool:
    """Return True when a TaskBoard summary is a heartbeat-style observation log."""
    if not summary:
        return False
    text = summary.strip()
    lowered = text.lower()
    if _HEARTBEAT_OBSERVATION_PREFIX_RE.search(text):
        return True
    if ("heartbeat" in lowered or " hb:" in lowered) and any(marker in lowered for marker in _OBSERVATION_LOG_MARKERS):
        return True
    return bool(_TIMED_OBSERVATION_PREFIX_RE.search(text)) and any(
        marker in lowered for marker in _OBSERVATION_LOG_MARKERS
    )


def _reject_observation_log_summary(summary: str) -> None:
    if _is_observation_log_summary(summary):
        raise ValueError(
            "Task summary must describe actionable work, not a heartbeat observation log. "
            "Put observations in context, task_results, or activity_log."
        )


def _is_status_report_summary(summary: str | None) -> bool:
    """Return True when an update summary is report text, not a task title."""
    if not summary:
        return False
    text = summary.strip()
    if len(text) <= _STATUS_REPORT_SUMMARY_MAX_CHARS:
        return False
    lowered = text.lower()
    marker_count = sum(1 for marker in _STATUS_REPORT_MARKERS if marker.lower() in lowered)
    sentence_count = sum(text.count(sep) for sep in ("。", ".", "\n", "；", ";"))
    return marker_count >= 2 or (marker_count >= 1 and sentence_count >= 2)


def _append_status_note(meta: dict[str, Any], *, note: str, status: str, ts: str) -> dict[str, Any]:
    """Return metadata with a bounded status_notes history appended."""
    if not note:
        return meta
    merged = dict(meta)
    notes_raw = merged.get("status_notes")
    notes = list(notes_raw) if isinstance(notes_raw, list) else []
    notes.append(
        {
            "ts": ts,
            "status": status,
            "note": note,
        }
    )
    merged["status_notes"] = notes[-20:]
    return merged


_QUEUE_LOCKS: dict[Path, threading.RLock] = {}
_QUEUE_LOCKS_GUARD = threading.Lock()


def _process_lock(path: Path) -> threading.RLock:
    resolved = path.resolve()
    with _QUEUE_LOCKS_GUARD:
        if resolved not in _QUEUE_LOCKS:
            _QUEUE_LOCKS[resolved] = threading.RLock()
        return _QUEUE_LOCKS[resolved]


def _parse_deadline(value: str) -> str:
    """Parse deadline string into ISO8601 format.

    Accepts relative formats ("30m", "2h", "1d") or ISO8601 absolute format.
    Relative formats are resolved to absolute ISO8601 from current time.

    Raises:
        ValueError: If the format is not recognized.
    """
    value = value.strip()
    m = _RELATIVE_DEADLINE_RE.match(value)
    if m:
        amount = int(m.group(1))
        unit = m.group(2)
        if unit == "m":
            delta = timedelta(minutes=amount)
        elif unit == "h":
            delta = timedelta(hours=amount)
        else:  # "d"
            delta = timedelta(days=amount)
        return (now_local() + delta).isoformat()

    # Try parsing as ISO8601
    try:
        datetime.fromisoformat(value)
        return value
    except (ValueError, TypeError):
        raise ValueError(
            f"Invalid deadline format: {value!r}. Use relative format ('30m', '2h', '1d') or ISO8601."
        ) from None


def _elapsed_seconds(updated_at: str, now: datetime) -> float | None:
    """Return seconds since updated_at, or None on parse failure."""
    try:
        updated = ensure_aware(datetime.fromisoformat(updated_at))
        return (now - updated).total_seconds()
    except (ValueError, TypeError):
        return None


def _format_elapsed_from_sec(elapsed_sec: float | None) -> str:
    """Format elapsed time as human-readable string (e.g. '⏱️ 47分経過').

    Takes pre-computed elapsed seconds to avoid redundant datetime parsing.
    Returns empty string for None or negative values.
    """
    if elapsed_sec is None or elapsed_sec < 0:
        return ""
    minutes = int(elapsed_sec / 60)
    if minutes < 60:
        return t("task_queue.elapsed_minutes", minutes=minutes)
    hours = minutes // 60
    remaining_min = minutes % 60
    if remaining_min:
        return t("task_queue.elapsed_hours_min", hours=hours, remaining_min=remaining_min)
    return t("task_queue.elapsed_hours", hours=hours)


def _format_deadline_display(deadline: str, now: datetime) -> str:
    """Format deadline for display. Returns OVERDUE marker if past."""
    try:
        dl = ensure_aware(datetime.fromisoformat(deadline))
    except (ValueError, TypeError):
        return ""
    if now >= dl:
        return t("task_queue.overdue", time=dl.strftime("%H:%M"))
    return t("task_queue.deadline_by", time=dl.strftime("%H:%M"))


def _is_overdue(deadline: str, now: datetime) -> bool:
    """Return True if the deadline has passed."""
    try:
        dl = ensure_aware(datetime.fromisoformat(deadline))
        return now >= dl
    except (ValueError, TypeError):
        return False


def _metadata_expired(expires_at: str | None) -> bool:
    """Return True when a TaskBoard metadata expiry timestamp is in the past."""
    if not expires_at:
        return False
    try:
        return now_local() >= ensure_aware(datetime.fromisoformat(expires_at))
    except (ValueError, TypeError):
        return False


def _delegated_child_ids(meta: dict[str, Any]) -> list[str]:
    """Return delegated child task ids from single-id and multi-id metadata."""
    child_ids = meta.get("delegated_task_ids")
    if isinstance(child_ids, list):
        result: list[str] = []
        for item in child_ids:
            if isinstance(item, str) and item:
                result.append(item)
            elif isinstance(item, dict):
                child_id = item.get("task_id")
                if isinstance(child_id, str) and child_id:
                    result.append(child_id)
        if result:
            return result
    child_id = meta.get("delegated_task_id")
    if isinstance(child_id, str) and child_id:
        return [child_id]
    return []


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

    @property
    def archive_path(self) -> Path:
        return self._queue_path.parent / "task_queue_archive.jsonl"

    # ── Write operations ─────────────────────────────────────

    def _build_task_entry(
        self,
        *,
        source: Literal["human", "anima"],
        original_instruction: str,
        assignee: str,
        summary: str,
        deadline: str | None = None,
        relay_chain: list[str] | None = None,
        task_id: str | None = None,
        meta: dict[str, Any] | None = None,
        status: str = "pending",
        priority: Literal["normal", "urgent"] = "normal",
    ) -> TaskEntry:
        if source not in _VALID_SOURCES:
            raise ValueError(f"Invalid source: {source!r} (must be 'human' or 'anima')")
        if status not in ("pending", "in_progress"):
            raise ValueError(f"Invalid status: {status!r} (must be 'pending' or 'in_progress')")
        if deadline is not None and deadline != "":
            parsed_deadline: str | None = _parse_deadline(deadline)
        elif deadline == "":
            raise ValueError("deadline is required when provided. Use relative format ('30m', '2h', '1d') or ISO8601.")
        else:
            parsed_deadline = None
        if len(original_instruction) > _MAX_INSTRUCTION_CHARS:
            original_instruction = original_instruction[:_MAX_INSTRUCTION_CHARS]
            logger.warning("original_instruction truncated to %d chars", _MAX_INSTRUCTION_CHARS)
        now = now_iso()
        return TaskEntry(
            task_id=task_id if task_id else uuid.uuid4().hex[:12],
            ts=now,
            source=source,
            original_instruction=original_instruction,
            assignee=assignee,
            status=status,
            summary=summary,
            deadline=parsed_deadline,
            relay_chain=relay_chain or [],
            updated_at=now,
            priority=priority,
            meta=meta or {},
        )

    def add_task(
        self,
        *,
        source: Literal["human", "anima"],
        original_instruction: str,
        assignee: str,
        summary: str,
        deadline: str | None = None,
        relay_chain: list[str] | None = None,
        task_id: str | None = None,
        meta: dict[str, Any] | None = None,
        status: str = "pending",
        priority: Literal["normal", "urgent"] = "normal",
    ) -> TaskEntry:
        """Add a new task to the queue.

        Returns the created TaskEntry.

        Args:
            source: Origin of the task ('human' or 'anima').
            original_instruction: Full instruction text.
            assignee: Anima name responsible for the task.
            summary: One-line summary.
            deadline: Optional. Relative ('30m', '2h', '1d') or ISO8601.
                None for tasks without deadline (e.g. submit_tasks).
            relay_chain: Optional delegation path.
            task_id: Optional. Use LLM-specified ID (e.g. from submit_tasks).
                If None, a UUID-based ID is generated.
            meta: Optional metadata (e.g. executor for TaskExec tracking).
            status: Initial status. Default "pending"; "in_progress" for
                submit_tasks tasks picked up by TaskExec.

        Returns:
            The created TaskEntry.

        Raises:
            ValueError: If source is invalid or deadline format is invalid
                when deadline is explicitly provided (non-empty).
        """
        _reject_observation_log_summary(summary)
        entry = self._build_task_entry(
            source=source,
            original_instruction=original_instruction,
            assignee=assignee,
            summary=summary,
            deadline=deadline,
            relay_chain=relay_chain,
            meta=meta,
            task_id=task_id,
            status=status,
            priority=priority,
        )
        self._append(entry.model_dump())
        logger.info(
            "Task added: id=%s source=%s assignee=%s summary=%s",
            entry.task_id,
            source,
            assignee,
            summary[:50],
        )
        return entry

    def add_task_if_absent(
        self,
        predicate: Callable[[TaskEntry], bool],
        *,
        source: Literal["human", "anima"],
        original_instruction: str,
        assignee: str,
        summary: str,
        deadline: str | None = None,
        relay_chain: list[str] | None = None,
        task_id: str | None = None,
        meta: dict[str, Any] | None = None,
        status: str = "pending",
    ) -> TaskEntry | None:
        """Atomically add a task only when no active task matches ``predicate``."""
        with self._locked_queue():
            for task in self._load_all().values():
                if task.status in _ACTIVE_STATUSES and predicate(task):
                    return None
            entry = self._build_task_entry(
                source=source,
                original_instruction=original_instruction,
                assignee=assignee,
                summary=summary,
                deadline=deadline,
                relay_chain=relay_chain,
                task_id=task_id,
                meta=meta,
                status=status,
            )
            self._append_unlocked(entry.model_dump())
        logger.info(
            "Task added: id=%s source=%s assignee=%s summary=%s",
            entry.task_id,
            source,
            assignee,
            summary[:50],
        )
        return entry

    def add_delegated_task(
        self,
        *,
        original_instruction: str,
        assignee: str,
        summary: str,
        deadline: str,
        relay_chain: list[str] | None = None,
        meta: dict[str, Any] | None = None,
        priority: Literal["normal", "urgent"] = "normal",
        task_id: str | None = None,
    ) -> TaskEntry:
        """Add a task with 'delegated' status for tracking delegation.

        Used by the delegating supervisor to record that a task was sent
        to a subordinate. The meta field stores delegated_to and delegated_task_id.
        """
        if not deadline:
            raise ValueError("deadline is required")
        _reject_observation_log_summary(summary)
        parsed_deadline = _parse_deadline(deadline)
        if len(original_instruction) > _MAX_INSTRUCTION_CHARS:
            original_instruction = original_instruction[:_MAX_INSTRUCTION_CHARS]
        now = now_iso()
        entry = TaskEntry(
            task_id=task_id if task_id else uuid.uuid4().hex[:12],
            ts=now,
            source="anima",
            original_instruction=original_instruction,
            assignee=assignee,
            status="delegated",
            summary=summary,
            deadline=parsed_deadline,
            relay_chain=relay_chain or [],
            updated_at=now,
            priority=priority,
            meta=meta or {},
        )
        self._append(entry.model_dump())
        logger.info(
            "Delegated task added: id=%s assignee=%s summary=%s",
            entry.task_id,
            assignee,
            summary[:50],
        )
        return entry

    def update_status(
        self,
        task_id: str,
        status: str,
        *,
        summary: str | None = None,
        note: str | None = None,
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

        clean_summary = summary
        if _is_observation_log_summary(summary):
            clean_summary = None
            logger.warning("Ignoring heartbeat observation log summary for task %s", task_id)
        elif _is_status_report_summary(summary):
            clean_summary = None
            note = summary if not note else f"{note}\n{summary}"
            logger.warning("Storing report-like update summary as status note for task %s", task_id)

        if status == "done":
            rejected = self._reject_unmet_completion_criteria(task)
            if rejected is not None:
                return rejected

        now = now_iso()
        merged_meta: dict[str, Any] | None = None
        if note:
            merged_meta = _append_status_note(task.meta or {}, note=note, status=status, ts=now)
        update: dict[str, Any] = {
            "task_id": task_id,
            "status": status,
            "updated_at": now,
            "_event": "update",
        }
        if clean_summary is not None:
            update["summary"] = clean_summary
        if merged_meta is not None:
            update["meta"] = merged_meta
        self._append(update)

        if status == "cancelled":
            self._cancel_delegated_child(task, summary=clean_summary)

        # Return reconstructed entry
        task.status = status
        task.updated_at = now
        if clean_summary is not None:
            task.summary = clean_summary
        if merged_meta is not None:
            task.meta = merged_meta
        logger.info("Task updated: id=%s status=%s", task_id, status)
        return task

    def _reject_unmet_completion_criteria(self, task: TaskEntry) -> TaskEntry | None:
        """Gate the transition to ``done`` behind machine-verified criteria.

        Returns the task unchanged (status preserved, rejection recorded as a
        status note) when ``meta.completion_criteria`` is present and unmet,
        or None when the transition may proceed.
        """
        from core.memory.task_verification import extract_criteria, verify_completion_criteria

        criteria = extract_criteria(task.meta)
        if not criteria:
            return None
        failures = verify_completion_criteria(criteria)
        if not failures:
            return None

        now = now_iso()
        rejection_note = "done rejected — completion criteria unmet:\n" + "\n".join(f"- {f}" for f in failures)
        merged_meta = _append_status_note(task.meta or {}, note=rejection_note, status=task.status, ts=now)
        self._append(
            {
                "task_id": task.task_id,
                "status": task.status,
                "updated_at": now,
                "meta": merged_meta,
                "_event": "update",
            }
        )
        task.updated_at = now
        task.meta = merged_meta
        logger.warning(
            "Task %s: done rejected, %d completion criteria unmet",
            task.task_id,
            len(failures),
        )
        return task

    def _cancel_delegated_child(self, task: TaskEntry, *, summary: str | None = None) -> bool:
        """Cancel the active subordinate task for a cancelled delegated entry."""
        meta = task.meta or {}
        target = meta.get("delegated_to")
        child_ids = _delegated_child_ids(meta)
        if not isinstance(target, str) or not target:
            return False
        if not child_ids:
            return False

        target_dir = self.anima_dir.parent / target
        if not target_dir.is_dir():
            logger.debug("cancel_delegated_child: target dir missing for %s", target)
            return False

        cancelled = False
        try:
            child_manager = TaskQueueManager(target_dir)
            for child_id in child_ids:
                child = child_manager.get_task_by_id(child_id)
                if child is None or child.status in _TERMINAL_STATUSES:
                    continue
                child_summary = summary or f"Cancelled because upstream delegated task {task.task_id} was cancelled"
                cancelled = (
                    child_manager.update_status(child_id, "cancelled", summary=child_summary) is not None or cancelled
                )
            return cancelled
        except Exception:
            logger.debug(
                "cancel_delegated_child: failed to cancel subordinate task(s) %s/%s",
                target,
                ",".join(child_ids),
                exc_info=True,
            )
            return False

    def update_meta(
        self,
        task_id: str,
        meta_patch: dict[str, Any],
        *,
        summary: str | None = None,
    ) -> TaskEntry | None:
        """Merge task metadata and append a durable update event."""
        tasks = self._load_all()
        task = tasks.get(task_id)
        if task is None:
            logger.warning("Task not found: %s", task_id)
            return None

        clean_summary = summary
        if _is_observation_log_summary(summary):
            clean_summary = None
            logger.warning("Ignoring heartbeat observation log summary for task metadata update %s", task_id)

        now = now_iso()
        merged_meta = dict(task.meta or {})
        merged_meta.update(meta_patch)
        update: dict[str, Any] = {
            "task_id": task_id,
            "meta": merged_meta,
            "updated_at": now,
            "_event": "update",
        }
        if clean_summary is not None:
            update["summary"] = clean_summary
        self._append(update)

        task.meta = merged_meta
        task.updated_at = now
        if clean_summary is not None:
            task.summary = clean_summary
        logger.info("Task metadata updated: id=%s keys=%s", task_id, sorted(meta_patch))
        return task

    def load_active_tasks(self) -> dict[str, TaskEntry]:
        """Load all non-terminal tasks (single JSONL replay).

        Use this for batch operations to avoid repeated file reads.
        """
        return {tid: t for tid, t in self._load_all().items() if t.status in _ACTIVE_STATUSES}

    # ── Read operations ──────────────────────────────────────

    def _load_all(self) -> dict[str, TaskEntry]:
        """Replay the JSONL log and return current task states.

        Returns dict mapping task_id to latest TaskEntry.
        Corrupted lines are skipped with a warning.
        """
        tasks: dict[str, TaskEntry] = {}
        if not self._queue_path.exists():
            return tasks

        # Tolerate stray non-UTF-8 bytes (e.g. CP932 lines accidentally appended
        # by external scripts). With errors="replace", bad bytes become U+FFFD
        # and the offending line fails json.loads → skipped below, so a single
        # corrupted line cannot take down the whole queue read.
        raw_text = self._queue_path.read_bytes().decode("utf-8", errors="replace")
        for line in raw_text.splitlines():
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
                    if "meta" in raw and isinstance(raw["meta"], dict):
                        existing.meta = raw["meta"]
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
        return [t for t in tasks.values() if t.status in ("pending", "in_progress")]

    def get_human_tasks(self) -> list[TaskEntry]:
        """Return pending/in_progress tasks with source='human'."""
        return [t for t in self.get_pending() if t.source == "human"]

    def get_all_active(self) -> list[TaskEntry]:
        """Return all non-terminal tasks (pending, in_progress, blocked)."""
        tasks = self._load_all()
        return [t for t in tasks.values() if t.status in ("pending", "in_progress", "blocked")]

    def list_tasks(self, status: str | None = None) -> list[TaskEntry]:
        """List tasks, optionally filtered by status.

        When status is omitted, returns only active tasks
        (pending, in_progress, blocked, delegated).
        """
        tasks = self._load_all()
        if status:
            return [t for t in tasks.values() if t.status == status]
        return [t for t in tasks.values() if t.status in _ACTIVE_STATUSES]

    def get_delegated_tasks(self) -> list[TaskEntry]:
        """Return tasks with status 'delegated'."""
        tasks = self._load_all()
        return [t for t in tasks.values() if t.status == "delegated"]

    def get_delegation_tracking_tasks(self) -> list[TaskEntry]:
        """Return active parent tasks that track a delegated child."""
        tasks = self._load_all()
        result: list[TaskEntry] = []
        for task in tasks.values():
            if task.status not in _DELEGATION_TRACKING_STATUSES:
                continue
            meta = task.meta or {}
            if meta.get("delegated_to") and _delegated_child_ids(meta):
                result.append(task)
        return result

    def get_failed_taskexec(self) -> list[TaskEntry]:
        """Return failed tasks executed by TaskExec (meta.executor == 'taskexec').

        Used for format_for_priming to show tasks that need human attention.
        """
        tasks = self._load_all()
        return [t for t in tasks.values() if t.status == "failed" and t.meta.get("executor") == "taskexec"]

    def get_task_by_id(self, task_id: str) -> TaskEntry | None:
        """Look up a single task by its ID."""
        return self._load_all().get(task_id)

    def get_active_goal_task(self, goal_id: str) -> TaskEntry | None:
        """Return an active task linked to a persistent goal, ignoring suppressed board rows.

        Archived, tombstoned, and expired TaskBoard metadata do not block goal
        continuation; snoozed/active pending work still counts as an existing
        continuation to avoid duplicate tasks.
        """
        if not goal_id:
            return None
        for task in self.load_active_tasks().values():
            if task.meta.get("goal_id") != goal_id:
                continue
            if self._goal_task_suppressed_by_taskboard(task.task_id):
                continue
            return task
        return None

    def list_goal_tasks(self, goal_id: str) -> list[TaskEntry]:
        """Return all queue tasks linked to a persistent goal."""
        if not goal_id:
            return []
        return sorted(
            [task for task in self._load_all().values() if task.meta.get("goal_id") == goal_id],
            key=lambda task: task.updated_at,
            reverse=True,
        )

    def _goal_task_suppressed_by_taskboard(self, task_id: str) -> bool:
        try:
            from core.taskboard.models import AttentionVisibility
            from core.taskboard.store import TaskBoardStore

            metadata = TaskBoardStore().get_metadata(self.anima_dir.name, task_id)
            if metadata is None:
                return False
            if _metadata_expired(metadata.expires_at):
                return True
            return metadata.visibility in {
                AttentionVisibility.ARCHIVED,
                AttentionVisibility.TOMBSTONED,
                AttentionVisibility.EXPIRED,
            }
        except Exception:
            logger.debug("TaskBoard metadata check failed for goal task %s", task_id, exc_info=True)
            return False

    # ── Formatting ───────────────────────────────────────────

    def format_for_priming(self, budget_tokens: int = 400) -> str:
        """Format pending tasks for system prompt injection.

        Active (non-OVERDUE) tasks are shown first with full detail.
        OVERDUE tasks are aggregated into a compact summary line.
        Failed TaskExec tasks are shown in a separate section.
        """
        tasks = self.get_pending()
        now = now_local()
        chars_per_token = 4
        max_chars = budget_tokens * chars_per_token
        lines: list[str] = []
        total = 0

        if tasks:
            active: list[TaskEntry] = []
            overdue: list[TaskEntry] = []
            for task in tasks:
                if task.deadline and _is_overdue(task.deadline, now):
                    overdue.append(task)
                else:
                    active.append(task)

            active.sort(
                key=lambda t: (
                    0 if t.source == "human" else 1,
                    t.updated_at or t.ts,
                ),
                reverse=False,
            )

            for task in active:
                priority = "🔴 HIGH" if task.source == "human" else "⚪"
                status_icon = "🔄" if task.status == "in_progress" else "📋"
                line = f"- {status_icon} {priority} [{task.task_id[:8]}] {task.summary} (assignee: {task.assignee})"
                if task.status == "in_progress" and task.meta.get("executor") == "taskexec":
                    line += f" {t('task_queue.auto_taskexec')}"
                if task.relay_chain:
                    line += f" chain: {' → '.join(task.relay_chain)}"

                elapsed_sec = _elapsed_seconds(task.updated_at, now)
                elapsed_str = _format_elapsed_from_sec(elapsed_sec)
                if elapsed_str:
                    line += f" {elapsed_str}"

                if elapsed_sec is not None and elapsed_sec >= _STALE_TASK_THRESHOLD_SEC:
                    line += " ⚠️ STALE"

                if task.deadline:
                    deadline_str = _format_deadline_display(task.deadline, now)
                    if deadline_str:
                        line += f" {deadline_str}"

                if total + len(line) > max_chars:
                    break
                lines.append(line)
                total += len(line) + 1

            if overdue:
                summaries_str = ", ".join(task.summary[:20] for task in overdue)
                aggregate_line = t(
                    "task_queue.overdue_aggregate",
                    count=len(overdue),
                    summaries=summaries_str,
                )
                if total + len(aggregate_line) + 1 <= max_chars:
                    lines.append(aggregate_line)
                    total += len(aggregate_line) + 1

        # Failed TaskExec tasks (within remaining budget)
        failed = self.get_failed_taskexec()
        if failed and total < max_chars:
            header = t("task_queue.failed_section_header")
            if total + len(header) <= max_chars:
                lines.append(header)
                total += len(header) + 1
            for task in failed:
                if total >= max_chars:
                    break
                line = t(
                    "task_queue.failed_line",
                    task_id=task.task_id[:8],
                    summary=task.summary,
                )
                if total + len(line) <= max_chars:
                    lines.append(line)
                    total += len(line) + 1

        # Delegated tasks (within remaining budget)
        delegated = self.get_delegated_tasks()
        if delegated and total < max_chars:
            try:
                from core.paths import get_animas_dir

                del_section = self.format_delegated_for_priming(get_animas_dir(), budget_chars=max_chars - total)
                if del_section:
                    lines.append(del_section)
                    total += len(del_section) + 1
            except Exception:
                logger.debug("format_for_priming: delegated section failed", exc_info=True)

        return "\n".join(lines) if lines else ""

    def get_stale_tasks(self) -> list[TaskEntry]:
        """Return pending/in_progress tasks not updated for 30+ minutes."""
        now = now_local()
        result: list[TaskEntry] = []
        for task in self.get_pending():
            elapsed = _elapsed_seconds(task.updated_at, now)
            if elapsed is not None and elapsed >= _STALE_TASK_THRESHOLD_SEC:
                result.append(task)
        return result

    # ── Delegation sync ─────────────────────────────────────────

    def sync_delegated(self, animas_dir: Path) -> int:
        """Sync delegated tasks with subordinate completion status.

        For each task in ``delegated`` status, reads the subordinate's
        queue (with archive fallback) and transitions:
        - subordinate done/cancelled → own entry ``done``
        - subordinate failed → own entry ``failed``

        Returns the number of tasks synced.
        """
        delegated = self.get_delegation_tracking_tasks()
        synced = 0
        for task in delegated:
            meta = task.meta or {}
            target = meta.get("delegated_to", "")
            child_ids = _delegated_child_ids(meta)
            if not target or not child_ids:
                continue
            target_dir = animas_dir / target
            if not target_dir.is_dir():
                logger.debug("sync_delegated: target dir missing for %s", target)
                continue
            child_statuses = {
                child_id: self._resolve_subordinate_status(target_dir, child_id, include_active=True)
                for child_id in child_ids
            }
            resolved_statuses = [status for status in child_statuses.values() if status is not None]
            if len(resolved_statuses) != len(child_ids):
                continue
            if any(status in _ACTIVE_STATUSES for status in resolved_statuses):
                if task.status == "blocked":
                    active_children = ", ".join(
                        f"{target}:{child_id}={status}"
                        for child_id, status in child_statuses.items()
                        if status in _ACTIVE_STATUSES
                    )
                    self.update_status(
                        task.task_id,
                        "delegated",
                        summary=f"Delegated child task(s) active: {active_children}; tracking continues",
                    )
                    synced += 1
                continue
            if all(status == "done" for status in resolved_statuses):
                self.update_status(
                    task.task_id,
                    "done",
                    summary=t("task_queue.sync_done", orig=task.summary, target=target),
                )
                _post_delegation_completion_to_discord(
                    task,
                    self.anima_dir,
                    target,
                    ",".join(child_ids),
                    animas_dir,
                    status="done",
                )
                synced += 1
            elif any(status == "cancelled" for status in resolved_statuses):
                cancelled_children = ", ".join(
                    f"{target}:{child_id}" for child_id, status in child_statuses.items() if status == "cancelled"
                )
                self.update_status(
                    task.task_id,
                    "blocked",
                    summary=(
                        f"BLOCKED: delegated child task(s) {cancelled_children} were cancelled; "
                        "re-delegation or explicit closure required"
                    ),
                )
                _post_delegation_completion_to_discord(
                    task,
                    self.anima_dir,
                    target,
                    ",".join(child_ids),
                    animas_dir,
                    status="cancelled",
                )
                synced += 1
            elif any(status == "failed" for status in resolved_statuses):
                self.update_status(
                    task.task_id,
                    "failed",
                    summary=t("task_queue.sync_failed", orig=task.summary, target=target),
                )
                _post_delegation_completion_to_discord(
                    task,
                    self.anima_dir,
                    target,
                    ",".join(child_ids),
                    animas_dir,
                    status="failed",
                )
                synced += 1
        return synced

    def _resolve_subordinate_status(
        self, target_dir: Path, child_id: str, *, include_active: bool = False
    ) -> str | None:
        """Look up subordinate task status, falling back to archive."""
        try:
            sub_tqm = TaskQueueManager(target_dir)
            sub_task = sub_tqm.get_task_by_id(child_id)
            if sub_task:
                if sub_task.status in _TERMINAL_STATUSES or include_active:
                    return sub_task.status
                return None
            return self._search_archive(target_dir, child_id)
        except Exception:
            logger.debug(
                "sync_delegated: failed to read subordinate queue at %s",
                target_dir,
                exc_info=True,
            )
            return None

    @staticmethod
    def _search_archive(target_dir: Path, child_id: str) -> str | None:
        """Search task_queue_archive.jsonl for a terminal task entry."""
        archive = target_dir / "state" / "task_queue_archive.jsonl"
        if not archive.exists():
            return None
        try:
            for line in reversed(archive.read_text(encoding="utf-8").strip().splitlines()):
                try:
                    data = json.loads(line)
                    if data.get("task_id") == child_id and data.get("status") in _TERMINAL_STATUSES:
                        return data["status"]
                except (json.JSONDecodeError, KeyError):
                    continue
        except OSError:
            logger.debug("sync_delegated: archive unreadable at %s", archive, exc_info=True)
        return None

    def format_delegated_for_priming(
        self,
        animas_dir: Path,
        budget_chars: int = 400,
    ) -> str:
        """Format delegated tasks with subordinate status for Priming display."""
        delegated = self.get_delegated_tasks()
        if not delegated:
            return ""
        now = now_local()
        lines: list[str] = []
        total = 0
        _status_icons = {"done": "✅", "failed": "❌", "cancelled": "🚫"}
        unknown_label = t("task_queue.delegated_unknown")
        for task in delegated[:5]:
            meta = task.meta or {}
            target = meta.get("delegated_to", unknown_label)
            child_id = meta.get("delegated_task_id", "")
            sub_status = "?"
            if child_id and target != unknown_label:
                sub_status = self._resolve_subordinate_display(animas_dir / target, child_id)
            icon = _status_icons.get(sub_status, "⏳")
            elapsed_sec = _elapsed_seconds(task.updated_at, now)
            elapsed_str = _format_elapsed_from_sec(elapsed_sec) or ""
            line = f"- 📌 [{task.task_id[:8]}] {task.summary} → {target} ({target}: {sub_status} {icon}) {elapsed_str}"
            if total + len(line) > budget_chars:
                break
            lines.append(line)
            total += len(line) + 1
        return "\n".join(lines)

    def _resolve_subordinate_display(self, target_dir: Path, child_id: str) -> str:
        """Resolve subordinate task status for display (single queue read)."""
        if not target_dir.is_dir():
            return "?"
        try:
            sub_tqm = TaskQueueManager(target_dir)
            sub_task = sub_tqm.get_task_by_id(child_id)
            if sub_task:
                return sub_task.status
            archived = self._search_archive(target_dir, child_id)
            return archived if archived else t("task_queue.delegated_archived")
        except Exception:
            return "?"

    # ── Maintenance ────────────────────────────────────────────

    def _archive(self, tasks: dict[str, TaskEntry]) -> None:
        """Append terminal tasks to archive file before removal."""
        with self.archive_path.open("a", encoding="utf-8") as f:
            for entry in tasks.values():
                f.write(json.dumps(entry.model_dump(), ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def compact(self) -> int:
        """Rewrite JSONL file with only active (non-terminal) tasks.

        Terminal statuses (done, cancelled, failed) are archived first,
        then removed from the queue.
        Returns the number of tasks removed.
        """
        tasks = self._load_all()
        active: dict[str, TaskEntry] = {}
        terminal: dict[str, TaskEntry] = {}
        for tid, entry in tasks.items():
            if entry.status in _TERMINAL_STATUSES:
                terminal[tid] = entry
            else:
                active[tid] = entry
        removed = len(terminal)
        if removed == 0:
            return 0
        # Archive first, then rewrite
        self._archive(terminal)
        tmp_path = self._queue_path.with_suffix(".tmp")
        try:
            with tmp_path.open("w", encoding="utf-8") as f:
                for entry in active.values():
                    f.write(json.dumps(entry.model_dump(), ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())
            tmp_path.replace(self._queue_path)
            logger.info("Task queue compacted: removed %d terminal tasks (archived)", removed)
        except Exception:
            logger.exception("Failed to compact task queue")
            tmp_path.unlink(missing_ok=True)
            removed = 0
        return removed

    # ── Internal ─────────────────────────────────────────────────

    @contextmanager
    def _locked_queue(self) -> Iterator[None]:
        self._queue_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._queue_path.with_suffix(self._queue_path.suffix + ".lock")
        thread_lock = _process_lock(lock_path)
        with thread_lock:
            try:
                lock_file = lock_path.open("a+", encoding="utf-8")
            except OSError:
                logger.debug("Task queue lock file unavailable for %s", lock_path, exc_info=True)
                yield
                return
            with lock_file:
                locked = False
                try:
                    from core.platform.locks import acquire_file_lock

                    acquire_file_lock(lock_file, exclusive=True)
                    locked = True
                except OSError:
                    logger.debug("OS file lock unavailable for %s", lock_path, exc_info=True)
                try:
                    yield
                finally:
                    if locked:
                        try:
                            from core.platform.locks import release_file_lock

                            release_file_lock(lock_file)
                        except OSError:
                            logger.debug("Failed to release task queue lock %s", lock_path, exc_info=True)

    def _append(self, data: dict[str, Any]) -> None:
        """Append a JSON line to the queue file with fsync."""
        with self._locked_queue():
            self._append_unlocked(data)

    def _append_unlocked(self, data: dict[str, Any]) -> None:
        """Append a JSON line while the queue lock is already held."""
        try:
            self._queue_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(data, ensure_ascii=False)
            with self._queue_path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
                f.flush()
                os.fsync(f.fileno())
        except OSError as exc:
            logger.exception("Failed to append to task queue")
            raise TaskPersistenceError(str(exc)) from exc


def _post_delegation_completion_to_discord(
    task: Any,
    delegator_dir: Path,
    target: str,
    child_id: str,
    animas_dir: Path,
    *,
    status: str,
) -> None:
    """Auto-post completion of a delegated task to its originating Discord thread.

    Looks up the subordinate's completion summary (if available) and the
    origin channel/thread recorded on the delegated task's meta, then
    fires a webhook post as the delegating Anima.  Silently no-ops if
    Discord origin info is absent or the webhook manager is unavailable.
    """
    meta = task.meta or {}
    channel_id = meta.get("discord_origin_channel_id", "")
    if not channel_id:
        return
    thread_ts = meta.get("discord_origin_thread_ts", "") or None
    user_id = meta.get("discord_origin_user_id", "")

    # Delegator name = parent dir of the delegator's anima_dir
    delegator = delegator_dir.name

    # Fetch subordinate's completion summary for a richer message
    sub_summary = ""
    try:
        target_dir = animas_dir / target
        sub_tqm = TaskQueueManager(target_dir)
        sub_task = sub_tqm.get_task_by_id(child_id)
        if sub_task:
            sub_summary = sub_task.summary or ""
    except Exception:
        logger.debug(
            "delegation-completion-to-discord: failed to read subordinate task %s/%s",
            target,
            child_id,
            exc_info=True,
        )

    mention = f"<@{user_id}> " if user_id else ""
    status_icon = "✅" if status == "done" else "❌"
    status_label = "完了" if status == "done" else "失敗"
    orig_summary = task.summary or "(no summary)"
    body = f"{mention}{status_icon} 委任タスク{status_label}報告\n\n依頼内容: {orig_summary}\n担当: {target}\n"
    if sub_summary:
        body += f"\n【{target}からの完了報告】\n{sub_summary}"

    try:
        from core.discord_webhooks import get_webhook_manager

        wm = get_webhook_manager()
        wm.send_as_anima(channel_id, delegator, body, thread_id=thread_ts)
        logger.info(
            "delegation-completion-to-discord: posted completion for %s → #%s thread=%s",
            child_id,
            channel_id,
            thread_ts or "(none)",
        )
    except Exception:
        logger.warning(
            "delegation-completion-to-discord: failed to post for %s",
            child_id,
            exc_info=True,
        )
        return

    # Mirror to the AnimaWorks board so the full completion text is
    # recorded even if Discord presentation truncates it.  Without this
    # mirror the body only lives on Discord, and any truncation or
    # webhook failure means the content is lost.
    try:
        from core.outbound_auto import DiscordAutoResponder

        DiscordAutoResponder._mirror_to_board(channel_id, body, delegator)
    except Exception:
        logger.debug(
            "delegation-completion-to-discord: board mirror failed for %s",
            child_id,
            exc_info=True,
        )
