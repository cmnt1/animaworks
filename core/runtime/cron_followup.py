"""Shared command-cron follow-up policy for legacy and isolated runners."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.config.models import load_config
from core.platform.atomic_io import atomic_write_json
from core.schemas import CronTask
from core.time_utils import now_local

logger = logging.getLogger(__name__)

FINGERPRINT_STATE_FILE = "cron_followup_fingerprints.json"


def command_followup_output(task: CronTask, result: dict[str, Any]) -> str | None:
    """Suppress only successful, explicitly quiet output; surface failures.

    ``trigger_heartbeat=False`` delegates notification to the command itself.
    A successful command with stderr is not demonstrably quiet, even if its
    stdout matches a normal-output pattern. The original result remains in
    the command audit log regardless of this decision.
    """
    if not task.trigger_heartbeat:
        return None
    stdout = str(result.get("stdout") or "").strip()
    stderr = str(result.get("stderr") or "").strip()
    if result.get("exit_code", 1) != 0 or stderr:
        return json.dumps(
            {"exit_code": result.get("exit_code"), "stdout": stdout, "stderr": stderr},
            ensure_ascii=False,
        )
    if not stdout:
        return None
    if task.skip_pattern:
        try:
            if re.search(task.skip_pattern, stdout):
                return None
        except re.error as exc:
            logger.warning(
                "Invalid skip_pattern %r for task %r: %s; continuing without skip",
                task.skip_pattern,
                task.name,
                exc,
            )
    return stdout


def fingerprint_cron_followup_output(command_output: str) -> str:
    """Return the stable SHA-256 fingerprint of a follow-up input."""
    return hashlib.sha256(command_output.encode("utf-8")).hexdigest()


def _fingerprint_state_path(anima_dir: Path) -> Path:
    return anima_dir / "state" / FINGERPRINT_STATE_FILE


def _read_fingerprint_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read cron follow-up fingerprint state %s; starting fresh", path, exc_info=True)
        return {}
    if not isinstance(data, dict):
        logger.warning("Cron follow-up fingerprint state %s is not an object; starting fresh", path)
        return {}
    return data


def _parse_timestamp(value: Any, *, reference: datetime) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=reference.tzinfo)
    return parsed


def cron_followup_repeat_suppress_hours() -> float:
    """Return the configured repeat-suppression window in hours (0 = disabled)."""
    try:
        value = float(load_config().heartbeat.cron_followup_repeat_suppress_hours)
    except (AttributeError, TypeError, ValueError):
        logger.warning("Invalid cron_followup_repeat_suppress_hours; using 6 hours")
        return 6.0
    return max(value, 0.0)


def should_suppress_cron_followup(
    anima_dir: Path,
    task_name: str,
    command_output: str,
    *,
    suppress_hours: float | None = None,
    now: datetime | None = None,
) -> bool:
    """Decide whether an identical follow-up should be suppressed.

    This also persists the decision to ``state/cron_followup_fingerprints.json``:
    a suppressed run increments ``suppressed``; a run that is allowed through
    refreshes ``last_followup_at`` so it becomes the new notification anchor.
    The state file is written atomically via a sibling temporary file + rename.
    """
    hours = cron_followup_repeat_suppress_hours() if suppress_hours is None else max(float(suppress_hours), 0.0)
    current_time = now or now_local()
    current_iso = current_time.isoformat()
    fingerprint = fingerprint_cron_followup_output(command_output)
    state_path = _fingerprint_state_path(anima_dir)
    state = _read_fingerprint_state(state_path)
    previous = state.get(task_name)

    if isinstance(previous, dict) and previous.get("sha256") == fingerprint:
        first_seen = previous.get("first_seen")
        if not isinstance(first_seen, str):
            first_seen = current_iso
        last_followup_at = _parse_timestamp(previous.get("last_followup_at"), reference=current_time)
        suppressed_count = previous.get("suppressed")
        if not isinstance(suppressed_count, int) or isinstance(suppressed_count, bool):
            suppressed_count = 0
        elapsed = current_time - last_followup_at if last_followup_at is not None else None
        if hours > 0 and elapsed is not None and elapsed < timedelta(hours=hours):
            suppressed_count += 1
            state[task_name] = {
                "sha256": fingerprint,
                "first_seen": first_seen,
                "last_followup_at": previous.get("last_followup_at") or current_iso,
                "suppressed": suppressed_count,
            }
            suppress = True
            logger.info(
                "Suppressed repeated cron follow-up for task %r (%d suppression(s) in %.1f hours)",
                task_name,
                suppressed_count,
                hours,
            )
        else:
            state[task_name] = {
                "sha256": fingerprint,
                "first_seen": first_seen,
                "last_followup_at": current_iso,
                "suppressed": suppressed_count,
            }
            suppress = False
    else:
        state[task_name] = {
            "sha256": fingerprint,
            "first_seen": current_iso,
            "last_followup_at": current_iso,
            "suppressed": 0,
        }
        suppress = False

    try:
        atomic_write_json(state_path, state, sort_keys=True)
    except OSError:
        logger.warning("Failed to persist cron follow-up fingerprint state %s", state_path, exc_info=True)
    return suppress
