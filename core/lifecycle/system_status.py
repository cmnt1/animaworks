from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""System consolidation job status tracking.

Persists job state to ``shared/system/consolidation_status.json`` and
provides helpers for missed-job detection and payload construction.
"""

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

from core.time_utils import now_iso, now_local

logger = logging.getLogger("animaworks.lifecycle.system_status")

JOB_TYPES = ("daily", "weekly", "monthly")

_file_lock = threading.Lock()


# ── Defaults ──────────────────────────────────────────────────────


def _default_job() -> dict:
    return {
        "last_started_at": None,
        "last_finished_at": None,
        "last_success_at": None,
        "last_status": "never",
        "last_error": None,
        "running": False,
    }


def _default_status() -> dict:
    return {jt: _default_job() for jt in JOB_TYPES}


# ── Path ──────────────────────────────────────────────────────────


def _status_path() -> Path:
    from core.paths import get_data_dir

    return get_data_dir() / "shared" / "system" / "consolidation_status.json"


# ── Load / Save ───────────────────────────────────────────────────


def load_status() -> dict:
    """Load consolidation status from disk. Returns defaults if missing."""
    path = _status_path()
    if not path.is_file():
        return _default_status()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        # Ensure all job types exist
        result = _default_status()
        for jt in JOB_TYPES:
            if jt in raw and isinstance(raw[jt], dict):
                result[jt].update(raw[jt])
        return result
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to load consolidation status, using defaults", exc_info=True)
        return _default_status()


def _save_status(status: dict) -> None:
    """Atomically write consolidation status to disk."""
    from core.memory._io import atomic_write_text

    with _file_lock:
        atomic_write_text(_status_path(), json.dumps(status, ensure_ascii=False, indent=2))


# ── State Transitions ─────────────────────────────────────────────


def mark_started(job_type: str) -> dict:
    """Mark a job as started. Returns the updated job entry."""
    status = load_status()
    entry = status[job_type]
    entry["running"] = True
    entry["last_started_at"] = now_iso()
    entry["last_status"] = "running"
    _save_status(status)
    return entry


def mark_succeeded(job_type: str) -> dict:
    """Mark a job as succeeded. Returns the updated job entry."""
    ts = now_iso()
    status = load_status()
    entry = status[job_type]
    entry["running"] = False
    entry["last_finished_at"] = ts
    entry["last_success_at"] = ts
    entry["last_status"] = "success"
    entry["last_error"] = None
    _save_status(status)
    return entry


def mark_failed(job_type: str, error: str) -> dict:
    """Mark a job as failed. Returns the updated job entry."""
    status = load_status()
    entry = status[job_type]
    entry["running"] = False
    entry["last_finished_at"] = now_iso()
    entry["last_status"] = "failed"
    entry["last_error"] = error[:500] if error else None
    _save_status(status)
    return entry


# ── Query ─────────────────────────────────────────────────────────


def is_running(job_type: str) -> bool:
    """Check if a job is currently running."""
    return load_status().get(job_type, {}).get("running", False)


def _parse_success_dt(entry: dict) -> datetime | None:
    """Parse last_success_at into a timezone-aware datetime."""
    raw = entry.get("last_success_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except (ValueError, TypeError):
        return None


def is_daily_missed(now: datetime) -> bool:
    """Daily is missed if today's 02:00 has passed and no success today."""
    schedule_time = now.replace(hour=2, minute=0, second=0, microsecond=0)
    if now < schedule_time:
        return False
    last_success = _parse_success_dt(load_status().get("daily", {}))
    if last_success is None:
        return True
    return last_success.date() < now.date()


def is_weekly_missed(now: datetime) -> bool:
    """Weekly is missed if this week's Sunday 03:00 has passed and no success this week."""
    # Find this week's Sunday (weekday 6)
    days_since_monday = now.weekday()
    days_to_sunday = 6 - days_since_monday
    sunday = (now + timedelta(days=days_to_sunday)).replace(
        hour=3,
        minute=0,
        second=0,
        microsecond=0,
    )
    # If today is after Sunday 03:00 this week
    if now < sunday:
        return False
    last_success = _parse_success_dt(load_status().get("weekly", {}))
    if last_success is None:
        return True
    # Check if last success was in this ISO week
    return last_success.isocalendar()[:2] < now.isocalendar()[:2]


def is_monthly_missed(now: datetime) -> bool:
    """Monthly is missed if this month's 1st 03:00 has passed and no success this month."""
    schedule_time = now.replace(day=1, hour=3, minute=0, second=0, microsecond=0)
    if now < schedule_time:
        return False
    last_success = _parse_success_dt(load_status().get("monthly", {}))
    if last_success is None:
        return True
    return (last_success.year, last_success.month) < (now.year, now.month)


# ── Already-ran detection (for skipping scheduled runs) ──────────


def already_ran_in_period(job_type: str, now: datetime | None = None) -> bool:
    """Return True if the job has a successful run within the current period.

    - daily: success timestamp on today (local date)
    - weekly: success timestamp within the current ISO week
    - monthly: success timestamp within the current calendar month

    Used by the scheduler to skip a scheduled run when the job has already
    been triggered manually within the same period.
    """
    if now is None:
        now = now_local()
    last_success = _parse_success_dt(load_status().get(job_type, {}))
    if last_success is None:
        return False
    if job_type == "daily":
        return last_success.date() == now.date()
    if job_type == "weekly":
        return last_success.isocalendar()[:2] == now.isocalendar()[:2]
    if job_type == "monthly":
        return (last_success.year, last_success.month) == (now.year, now.month)
    return False


# ── Payload ───────────────────────────────────────────────────────


def build_status_payload() -> dict:
    """Build API/WebSocket payload with status + missed flags."""
    now = now_local()
    status = load_status()
    missed_checks = {
        "daily": is_daily_missed,
        "weekly": is_weekly_missed,
        "monthly": is_monthly_missed,
    }
    for jt in JOB_TYPES:
        status[jt]["missed"] = missed_checks[jt](now)
    return status


# ── Cleanup ───────────────────────────────────────────────────────


def clear_stale_running() -> None:
    """Reset any 'running' entries to 'failed' (call on startup)."""
    status = load_status()
    changed = False
    for jt in JOB_TYPES:
        if status[jt].get("running"):
            status[jt]["running"] = False
            status[jt]["last_status"] = "failed"
            status[jt]["last_error"] = "interrupted by server restart"
            status[jt]["last_finished_at"] = now_iso()
            changed = True
            logger.info("Cleared stale running state for %s consolidation", jt)
    if changed:
        _save_status(status)
