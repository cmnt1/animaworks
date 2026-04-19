from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Urgent-mode state management.

Urgent mode is tied to task IDs.  When at least one urgent task is active
for an Anima, several throttles are bypassed:

  * Outbound rate limits (``max_outbound_per_hour`` / ``per_day``)
  * Message cooldowns (``msg_heartbeat_cooldown_s`` etc.)
  * ``activity_pct`` scaling (treated as 100% for scheduling purposes)
  * ``PendingTaskExec`` poll interval (immediate wake)
  * Per-run 2-person DM cap and single-message-per-recipient cap

``completion_gate`` is NOT bypassed — speed must not sacrifice completion.

State is stored per-Anima at ``state/urgent_active.json`` as a JSON object
mapping ``task_id`` → ``{"added_at": ISO8601, "note": str | None}``.
"""

import json
import logging
import re
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("animaworks.urgent")

_URGENT_FILE = "urgent_active.json"

# Lock for local reads/writes within this process.  Cross-process safety is
# less critical: the file is append/replace style and worst-case a stale read
# only costs one extra cycle of normal-mode throttling.
_file_lock = threading.Lock()

# Japanese / English prefixes that mark an inbox message as urgent.  Detection
# is case-insensitive and tolerates surrounding whitespace.
_URGENT_PREFIX_RE = re.compile(
    r"^\s*[\[【]\s*(至急|緊急|urgent)\s*[\]】]",
    re.IGNORECASE,
)


def _urgent_path(anima_dir: Path) -> Path:
    return anima_dir / "state" / _URGENT_FILE


def _load(anima_dir: Path) -> dict[str, dict]:
    path = _urgent_path(anima_dir)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError) as exc:
        logger.warning("urgent_active.json unreadable (%s); treating as empty", exc)
    return {}


def _save(anima_dir: Path, data: dict[str, dict]) -> None:
    path = _urgent_path(anima_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def detect_urgent_prefix(text: str) -> bool:
    """Return True if ``text`` starts with [至急] / [緊急] / [urgent]."""
    if not text:
        return False
    return bool(_URGENT_PREFIX_RE.match(text))


def is_urgent_active(anima_dir: Path) -> bool:
    with _file_lock:
        return bool(_load(anima_dir))


def active_task_ids(anima_dir: Path) -> list[str]:
    with _file_lock:
        return list(_load(anima_dir).keys())


def add_urgent(anima_dir: Path, task_id: str, note: str | None = None) -> None:
    """Mark ``task_id`` as urgent for this Anima."""
    if not task_id:
        return
    with _file_lock:
        data = _load(anima_dir)
        data[task_id] = {
            "added_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "note": note,
        }
        _save(anima_dir, data)
    logger.info("urgent: +%s (%s)", task_id, note or "")


def remove_urgent(anima_dir: Path, task_id: str) -> None:
    if not task_id:
        return
    with _file_lock:
        data = _load(anima_dir)
        if task_id in data:
            data.pop(task_id, None)
            _save(anima_dir, data)
            logger.info("urgent: -%s", task_id)


def clear_urgent(anima_dir: Path) -> None:
    with _file_lock:
        _save(anima_dir, {})
    logger.info("urgent: cleared all")


__all__ = [
    "detect_urgent_prefix",
    "is_urgent_active",
    "active_task_ids",
    "add_urgent",
    "remove_urgent",
    "clear_urgent",
]
