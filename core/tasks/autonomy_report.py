from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Read-only autonomy metrics for delegated work.

The report answers whether an Anima still acts on its own or has drifted into
being a plain sub-agent.  It reads the task SQLite store and the per-Anima
activity JSONL files directly, so it works while the server is down and never
takes a write lock.
"""

import json
import logging
import re
import sqlite3
from collections.abc import Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Any

from core.tasks.board.tasks import TaskStore
from core.time_utils import ensure_aware, now_local

logger = logging.getLogger(__name__)

DEFAULT_DAYS = 7

# Trigger events used by the activity timeline (core/activity/timeline.py).
# message_received counts only for the chat channel (inbox deliveries are counted
# once per inbox_processing_start), and command-type cron runs (meta.command)
# do not start an LLM session, so neither is a launch.
LAUNCH_EVENT_TYPES: dict[str, str] = {
    "heartbeat_start": "heartbeat",
    "cron_executed": "cron",
    "inbox_processing_start": "inbox",
    "message_received": "chat",
    "task_exec_start": "task_exec",
}
_TASK_ID_TOKEN = re.compile(r"\b[0-9a-f]{12}\b")

DM_EVENT_TYPES = frozenset({"message_sent", "message_received", "dm_sent", "dm_received"})
TASK_START_CLASSES = ("self", "delegated", "human", "unknown")


def build_autonomy_report(
    data_dir: Path,
    *,
    days: int = DEFAULT_DAYS,
    anima: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Aggregate autonomy metrics for one runtime data directory.

    Args:
        data_dir: Runtime data directory (the equivalent of ``~/.animaworks``).
        days: Rolling period length in days.  Must be at least one.
        anima: Optional anima name to restrict the report to.
        now: Injectable clock for deterministic tests.
    """
    if days < 1:
        raise ValueError("days must be >= 1")

    until = ensure_aware(now) if now is not None else now_local()
    since = until - timedelta(days=days)
    data_dir = Path(data_dir)
    animas_dir = data_dir / "animas"
    db_path = data_dir / "shared" / "taskboard.sqlite3"

    attempts, terminal_rows = _load_task_rows(db_path, since=since, until=until)

    names: set[str] = set()
    if anima:
        names.add(anima)
    else:
        names.update(_discover_animas(animas_dir))
        names.update(row["anima"] for row in attempts)
        names.update(row["anima"] for row in terminal_rows)

    reports: dict[str, dict[str, Any]] = {name: _empty_anima_report(name) for name in sorted(names)}
    delegated_tasks: dict[str, set[str]] = {name: set() for name in reports}
    known_task_ids = {str(row["task_id"]) for row in attempts}
    dm_counts: dict[str, dict[str, int]] = {
        name: _read_activity_stats(
            animas_dir / name / "activity_log",
            since=since,
            until=until,
            launch_counts=reports[name]["launch_counts"],
            known_task_ids=known_task_ids,
        )
        for name in reports
    }

    for row in attempts:
        name = row["anima"]
        report = reports.get(name)
        if report is None:
            continue
        entry = _load_object(row["entry_json"])
        payload = _load_object(row["input_json"])
        classification = _classify_task(entry, payload, name)
        report["task_starts"][classification] += 1
        report["task_starts"]["total"] += 1
        if classification == "delegated":
            delegated_tasks[name].add(row["task_id"])

    for row in terminal_rows:
        name = row["anima"]
        report = reports.get(name)
        if report is None:
            continue
        entry = _load_object(row["entry_json"])
        if not _within_period(entry.get("updated_at") or entry.get("ts"), since, until):
            continue
        status = str(entry.get("status") or "")
        meta = entry.get("meta")
        if not isinstance(meta, dict):
            meta = {}
        if status in {"done", "cancelled"}:
            if status == "cancelled":
                payload = _load_object(row["input_json"])
                if _classify_task(entry, payload, name) == "delegated":
                    report["discretion"]["delegated_cancelled"] += 1
            notes = meta.get("scope_notes")
            if isinstance(notes, list):
                report["discretion"]["scope_notes"] += len(notes)
        elif status == "pending" and meta.get("waiting_for"):
            report["discretion"]["waiting_for"] += 1

    total_cost = 0.0
    total_sessions = 0
    for name, report in reports.items():
        cost, sessions = _read_cost(animas_dir / name, days)
        report["cost"]["total_estimated_cost_usd"] = cost
        report["cost"]["total_sessions"] = sessions
        report["cost"]["cost_available"] = cost > 0
        total_cost += cost
        total_sessions += sessions
        report["round_trips"] = _round_trip_summary(
            [(name, task_id) for task_id in delegated_tasks[name]],
            {(name, task_id): count for task_id, count in dm_counts[name].items()},
            delegated_task_count=len(delegated_tasks[name]),
            include_anima=False,
        )

    totals = _build_totals(reports, total_cost, total_sessions)
    for report in reports.values():
        report["spontaneity_ratio"] = _ratio(report["task_starts"]["self"], report["task_starts"]["total"])
        report["launch_share"] = _ratio(report["launch_counts"]["total"], totals["launch_counts"]["total"])
        report["cost"]["cost_share"] = _ratio(report["cost"]["total_estimated_cost_usd"], total_cost)
        report["cost_share"] = report["cost"]["cost_share"]
    totals["round_trips"] = _round_trip_summary(
        [(name, task_id) for name, tasks in delegated_tasks.items() for task_id in tasks],
        {(name, task_id): count for name, counts in dm_counts.items() for task_id, count in counts.items()},
        delegated_task_count=sum(len(tasks) for tasks in delegated_tasks.values()),
        include_anima=True,
    )
    totals["spontaneity_ratio"] = _ratio(totals["task_starts"]["self"], totals["task_starts"]["total"])
    totals["launch_share"] = _ratio(totals["launch_counts"]["total"], totals["launch_counts"]["total"])
    totals["cost"]["cost_available"] = total_cost > 0
    totals["cost"]["cost_share"] = _ratio(total_cost, total_cost)
    totals["cost_share"] = totals["cost"]["cost_share"]

    return {
        "days": days,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "animas": reports,
        "totals": totals,
    }


def _empty_anima_report(name: str) -> dict[str, Any]:
    return {
        "anima": name,
        "task_starts": {"self": 0, "delegated": 0, "human": 0, "unknown": 0, "total": 0},
        "spontaneity_ratio": None,
        "launch_counts": {kind: 0 for kind in LAUNCH_EVENT_TYPES.values()} | {"total": 0},
        "launch_share": None,
        "discretion": {"delegated_cancelled": 0, "scope_notes": 0, "waiting_for": 0},
        "cost": {
            "total_estimated_cost_usd": 0.0,
            "total_sessions": 0,
            "cost_share": None,
            "cost_available": False,
        },
        "round_trips": {
            "delegated_tasks": 0,
            "event_count": 0,
            "median": None,
            "max": 0,
            "top_task_ids": [],
        },
    }


def _build_totals(reports: dict[str, dict[str, Any]], total_cost: float, total_sessions: int) -> dict[str, Any]:
    task_starts = {classification: 0 for classification in TASK_START_CLASSES}
    launch_counts = {kind: 0 for kind in LAUNCH_EVENT_TYPES.values()}
    discretion = {"delegated_cancelled": 0, "scope_notes": 0, "waiting_for": 0}
    for report in reports.values():
        for classification in TASK_START_CLASSES:
            task_starts[classification] += report["task_starts"][classification]
        for kind in LAUNCH_EVENT_TYPES.values():
            launch_counts[kind] += report["launch_counts"][kind]
        for key in discretion:
            discretion[key] += report["discretion"][key]
    task_starts["total"] = sum(report["task_starts"]["total"] for report in reports.values())
    launch_counts["total"] = sum(launch_counts[kind] for kind in LAUNCH_EVENT_TYPES.values())
    return {
        "task_starts": task_starts,
        "spontaneity_ratio": None,
        "launch_counts": launch_counts,
        "discretion": discretion,
        "cost": {
            "total_estimated_cost_usd": round(total_cost, 4),
            "total_sessions": total_sessions,
            "cost_available": total_cost > 0,
        },
        "round_trips": {
            "delegated_tasks": 0,
            "event_count": 0,
            "median": None,
            "max": 0,
            "top_task_ids": [],
        },
    }


def _round_trip_summary(
    pairs: list[tuple[str, str]],
    dm_counts: dict[tuple[str, str], int],
    *,
    delegated_task_count: int,
    include_anima: bool,
) -> dict[str, Any]:
    """Summarise DM events per delegated task.

    When no delegated task started in the period, fall back to the tasks that
    actually have task-scoped DM events so the activity is still visible.
    """
    if pairs:
        counts = [dm_counts.get(pair, 0) for pair in pairs]
    else:
        pairs = sorted(dm_counts)
        counts = [dm_counts[pair] for pair in pairs]

    ranked = sorted(
        ((pair, dm_counts.get(pair, 0)) for pair in pairs if dm_counts.get(pair, 0) > 0),
        key=lambda item: (-item[1], item[0]),
    )[:5]
    top_task_ids = []
    for (name, task_id), count in ranked:
        item = {"task_id": task_id, "count": count}
        if include_anima:
            item["anima"] = name
        top_task_ids.append(item)

    return {
        "delegated_tasks": delegated_task_count,
        "event_count": sum(counts),
        "median": float(median(counts)) if counts else None,
        "max": max(counts) if counts else 0,
        "top_task_ids": top_task_ids,
    }


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _classify_task(entry: dict[str, Any], payload: dict[str, Any], owner: str) -> str:
    """Classify a task by its origin, preferring the saved execution input."""
    source = str(payload.get("source") or "").strip().lower()
    entry_source = str(entry.get("source") or "").strip().lower()

    if source == "delegation":
        return "delegated"
    if source in {"cron", "cron_task"}:
        return "self"
    if source == "human" or entry_source == "human":
        return "human"
    if payload.get("submitted_by") == owner:
        return "self"
    if entry_source == "anima" and payload.get("reply_to") == owner:
        return "self"
    return "unknown"


def _load_task_rows(
    db_path: Path,
    *,
    since: datetime,
    until: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read attempts started in the period and recently terminal task rows."""
    store = TaskStore.open(db_path, read_only=True)
    if not store.has_database:
        return [], []

    since_iso = since.isoformat()
    until_iso = until.isoformat()
    attempts: list[dict[str, Any]] = []
    terminal_rows: list[dict[str, Any]] = []
    try:
        with store.reader() as db:
            attempts = [
                dict(row)
                for row in db.execute(
                    "SELECT a.anima AS anima, a.task_id AS task_id, MIN(a.started_at) AS started_at, "
                    "t.entry_json AS entry_json, t.input_json AS input_json "
                    "FROM task_attempts a "
                    "LEFT JOIN tasks t ON t.anima=a.anima AND t.task_id=a.task_id "
                    "WHERE datetime(a.started_at) >= datetime(?) "
                    "AND datetime(a.started_at) <= datetime(?) "
                    "GROUP BY a.anima, a.task_id "
                    "ORDER BY a.anima, MIN(a.started_at)",
                    (since_iso, until_iso),
                ).fetchall()
            ]
            terminal_rows = [
                dict(row)
                for row in db.execute(
                    "SELECT anima, task_id, entry_json, input_json FROM tasks "
                    "WHERE json_extract(entry_json, '$.status') IN ('done', 'cancelled', 'pending') "
                    "AND datetime(COALESCE(json_extract(entry_json, '$.updated_at'), "
                    "json_extract(entry_json, '$.ts'))) >= datetime(?) "
                    "AND datetime(COALESCE(json_extract(entry_json, '$.updated_at'), "
                    "json_extract(entry_json, '$.ts'))) <= datetime(?) "
                    "ORDER BY anima, task_id",
                    (since_iso, until_iso),
                ).fetchall()
            ]
    except (OSError, sqlite3.Error):
        logger.warning("Failed to read task store for autonomy report: %s", db_path, exc_info=True)
        return [], []
    return attempts, terminal_rows


def _discover_animas(animas_dir: Path) -> list[str]:
    try:
        return [path.name for path in animas_dir.iterdir() if path.is_dir()]
    except OSError:
        return []


def _load_object(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _within_period(value: Any, since: datetime, until: datetime) -> bool:
    parsed = _parse_timestamp(value)
    return parsed is not None and since <= parsed <= until


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return ensure_aware(datetime.fromisoformat(value))
    except (TypeError, ValueError):
        return None


def _activity_dates(since: datetime, until: datetime) -> Iterator[date]:
    current = since.date()
    end = until.date()
    while current <= end:
        yield current
        current += timedelta(days=1)


def _read_activity_stats(
    log_dir: Path,
    *,
    since: datetime,
    until: datetime,
    launch_counts: dict[str, int],
    known_task_ids: set[str] | None = None,
) -> dict[str, int]:
    """Stream the period's JSONL files once and aggregate launch/DM counts."""
    dm_counts: dict[str, int] = {}
    if not log_dir.is_dir():
        return dm_counts

    for day in _activity_dates(since, until):
        path = log_dir / f"{day.isoformat()}.jsonl"
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(raw, dict):
                        continue
                    timestamp = _parse_timestamp(raw.get("ts") or raw.get("timestamp"))
                    if timestamp is None or not (since <= timestamp <= until):
                        continue
                    event_type = str(raw.get("type") or raw.get("event") or raw.get("event_type") or "")
                    kind = _launch_kind(event_type, raw)
                    if kind is not None:
                        launch_counts[kind] += 1
                        launch_counts["total"] += 1
                    if event_type in DM_EVENT_TYPES:
                        for task_id in _dm_task_ids(raw, known_task_ids or set()):
                            dm_counts[task_id] = dm_counts.get(task_id, 0) + 1
        except OSError:
            logger.warning("Failed to read activity log for autonomy report: %s", path, exc_info=True)
    return dm_counts


def _launch_kind(event_type: str, raw: dict[str, Any]) -> str | None:
    kind = LAUNCH_EVENT_TYPES.get(event_type)
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    if kind == "chat" and raw.get("channel") != "chat":
        return None
    if kind == "cron" and meta.get("command"):
        return None
    return kind


def _dm_task_ids(raw: dict[str, Any], known_task_ids: set[str]) -> set[str]:
    """DM events rarely carry meta.task_id; fall back to ctx and IDs in the text."""
    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    found: set[str] = set()
    task_id = meta.get("task_id")
    if isinstance(task_id, str) and task_id:
        found.add(task_id)
    ctx = raw.get("ctx")
    if isinstance(ctx, str) and ctx.startswith("task:"):
        found.add(ctx[5:])
    text = f"{raw.get('content') or ''} {raw.get('summary') or ''}"
    found.update(token for token in _TASK_ID_TOKEN.findall(text) if token in known_task_ids)
    return found


def _read_cost(anima_dir: Path, days: int) -> tuple[float, int]:
    """Reuse the existing token-usage summary instead of re-deriving costs."""
    if not anima_dir.is_dir():
        return 0.0, 0
    try:
        from core.usage.token_usage import TokenUsageLogger

        summary = TokenUsageLogger(anima_dir).summarize(days)
    except Exception:
        logger.warning("Failed to read token usage for autonomy report: %s", anima_dir, exc_info=True)
        return 0.0, 0
    try:
        cost = float(summary.get("total_estimated_cost_usd") or 0.0)
    except (TypeError, ValueError):
        cost = 0.0
    try:
        sessions = int(summary.get("total_sessions") or 0)
    except (TypeError, ValueError):
        sessions = 0
    return cost, sessions
