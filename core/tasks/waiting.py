from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Validation and presentation helpers for task ``waiting_for`` declarations."""

from datetime import datetime
from typing import Any

from core.i18n import t

WAITING_KINDS = frozenset({"task", "time", "message", "external"})
_WAKE_KINDS = frozenset({"task", "time"})


def _iso(value: Any) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError("waiting_for.until is required for kind='time'")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("waiting_for.until must be an ISO8601 timestamp") from exc
    return text


def normalize_waiting_for(value: Any, status: str | None) -> dict[str, str]:
    """Validate a ``waiting_for`` declaration for a pending task.

    Returns only the canonical keys (``kind``, ``ref`` and, when supplied,
    ``until``) so the stored shape stays predictable across host and sandbox
    paths.
    """
    if status != "pending":
        raise ValueError("waiting_for is only valid together with status='pending'")
    if not isinstance(value, dict):
        raise ValueError("waiting_for must be an object")
    kind = value.get("kind")
    if kind not in WAITING_KINDS:
        raise ValueError("waiting_for.kind must be one of task, time, message, external")
    until = value.get("until")
    if kind == "time":
        return {"kind": "time", "until": _iso(until)}
    ref = value.get("ref")
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError("waiting_for.ref is required")
    return {"kind": str(kind), "ref": ref.strip()}


def is_wakeable(waiting_for: Any) -> bool:
    return isinstance(waiting_for, dict) and waiting_for.get("kind") in _WAKE_KINDS


def _time_label(value: Any) -> str:
    text = str(value or "")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%m/%d %H:%M")
    except ValueError:
        return text


def waiting_target(waiting_for: dict[str, Any]) -> str:
    """Describe what a task is waiting for, without the display prefix."""
    kind = waiting_for.get("kind")
    ref = str(waiting_for.get("ref") or "")
    if kind == "task":
        return t("task_wait.target_task", ref=ref)
    if kind == "time":
        return t("task_wait.target_time", until=_time_label(waiting_for.get("until")))
    if kind == "message":
        return t("task_wait.target_message", ref=ref)
    return t("task_wait.target_external", ref=ref)


def waiting_label(waiting_for: Any) -> str | None:
    """Return a one-line display label such as ``待ち: タスク abc の完了``."""
    if not isinstance(waiting_for, dict) or waiting_for.get("kind") not in WAITING_KINDS:
        return None
    return t("task_wait.label", target=waiting_target(waiting_for))
