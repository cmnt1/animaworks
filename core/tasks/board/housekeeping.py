from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""TaskBoard-aware stale runtime artifact cleanup.

TaskBoard now reads the canonical TaskStore directly; there is no separate
presentation metadata to reconcile, so housekeeping only cleans runtime
artifacts that could resurface stale work (background tasks and current_state).
"""

import json
import logging
import time
from pathlib import Path
from typing import Any

from core.time_utils import today_local

logger = logging.getLogger("animaworks.housekeeping.taskboard")


def cleanup_taskboard_stale_artifacts(
    data_dir: Path,
    pending_processing_stale_hours: int,
    background_running_stale_hours: int,
    current_state_stale_hours: int,
) -> dict[str, Any]:
    """Clean runtime artifacts that can resurface stale task work."""
    del pending_processing_stale_hours
    animas_dir = data_dir / "animas"
    if not animas_dir.exists():
        return {"skipped": True}

    results: dict[str, Any] = {}

    background = _cleanup_background_running(animas_dir, background_running_stale_hours)
    results.update({f"background_{key}": value for key, value in background.items()})

    current_state = _cleanup_current_state(animas_dir, current_state_stale_hours)
    results.update({f"current_state_{key}": value for key, value in current_state.items()})

    return results


def _cleanup_background_running(animas_dir: Path, stale_hours: int) -> dict[str, int]:
    cutoff_ts = time.time() - (stale_hours * 3600)
    deleted = 0
    errors = 0

    for anima_dir in _iter_anima_dirs(animas_dir):
        background_dir = anima_dir / "state" / "background_tasks"
        if not background_dir.is_dir():
            continue
        for path in sorted(background_dir.glob("*.json")):
            try:
                payload, valid_json = _read_json_object(path)
                if not valid_json or payload.get("status") != "running":
                    continue
                created_at = _float_or_none(payload.get("created_at"))
                if created_at is not None and created_at < cutoff_ts:
                    path.unlink()
                    deleted += 1
            except OSError:
                errors += 1
                logger.warning("Failed to delete stale background task: %s", path, exc_info=True)

    return {"running_deleted": deleted, "errors": errors}


def _cleanup_current_state(animas_dir: Path, stale_hours: int) -> dict[str, int]:
    cutoff_ts = time.time() - (stale_hours * 3600)
    now = today_local()
    archived = 0
    active_visible = 0
    skipped_idle = 0
    changed = 0
    errors = 0

    for anima_dir in _iter_anima_dirs(animas_dir):
        state_path = anima_dir / "state" / "current_state.md"
        try:
            if not state_path.is_file():
                continue
            observed_mtime = state_path.stat().st_mtime
            if observed_mtime >= cutoff_ts:
                continue
            content = state_path.read_text(encoding="utf-8")
            if not content.strip() or content.strip() == "status: idle":
                skipped_idle += 1
                continue
            if _has_active_visible_task(anima_dir, now):
                active_visible += 1
                continue
            outcome = _archive_current_state_for_housekeeping(
                anima_dir,
                state_path,
                content,
                expected_mtime=observed_mtime,
            )
            if outcome == "archived":
                archived += 1
            elif outcome == "changed":
                changed += 1
            else:
                errors += 1
        except OSError:
            errors += 1
            logger.warning("Failed to cleanup current_state: %s", state_path, exc_info=True)

    return {
        "archived": archived,
        "active_visible": active_visible,
        "skipped_idle": skipped_idle,
        "changed": changed,
        "errors": errors,
    }


def _iter_anima_dirs(animas_dir: Path) -> list[Path]:
    if not animas_dir.exists():
        return []
    return [path for path in sorted(animas_dir.iterdir()) if path.is_dir()]


def _read_json_object(path: Path) -> tuple[dict[str, Any], bool]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}, False
    if not isinstance(payload, dict):
        return {}, False
    return payload, True


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_active_visible_task(anima_dir: Path, now: Any) -> bool:
    """Retain working notes while any canonical task is unfinished."""
    del now
    try:
        from core.tasks.queue import TaskQueueManager

        return bool(TaskQueueManager(anima_dir).load_active_tasks())
    except Exception:
        logger.debug("Failed to read canonical tasks for %s", anima_dir.name, exc_info=True)
        return True


def _archive_current_state_for_housekeeping(
    anima_dir: Path,
    state_path: Path,
    content: str,
    *,
    expected_mtime: float | None = None,
) -> str:
    try:
        from core.memory.state_lock import StateFileLock
        from core.platform.atomic_io import atomic_write_text

        with StateFileLock(anima_dir):
            if expected_mtime is not None and state_path.stat().st_mtime != expected_mtime:
                return "changed"
            episodes_dir = anima_dir / "episodes"
            episodes_dir.mkdir(parents=True, exist_ok=True)
            episode_path = episodes_dir / f"{today_local().isoformat()}.md"
            existing = (
                episode_path.read_text(encoding="utf-8")
                if episode_path.exists()
                else f"# {today_local().isoformat()}\n"
            )
            entry = f"\n## Working notes archived by TaskBoard housekeeping\n\n{content.rstrip()}\n"
            atomic_write_text(episode_path, existing.rstrip() + "\n\n" + entry.lstrip())
            atomic_write_text(state_path, "status: idle\n")
        return "archived"
    except Exception:
        logger.warning("Failed to archive current_state for housekeeping: %s", state_path, exc_info=True)
        return "error"
