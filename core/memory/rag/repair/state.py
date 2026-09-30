"""Persistent repair-state helpers for RAG auto-repair."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from core.platform.atomic_io import atomic_write_json

from .types import RepairResult

ACTIVE_REPAIR_STATUSES = frozenset({"requested", "stopping", "repairing"})
STAGE_FENCE_ACCESS = "fence_access"
STAGE_REPAIR = "repair"
STAGE_UNFENCE = "unfence"


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def iso(dt: datetime | None = None) -> str:
    return (dt or utc_now()).isoformat()


def state_path(anima_name: str, *, animas_dir: Path | None = None) -> Path:
    if animas_dir is None:
        from core.paths import get_animas_dir

        animas_dir = get_animas_dir()

    return animas_dir / anima_name / "state" / "rag_repair.json"


def read_state(anima_name: str, *, animas_dir: Path | None = None) -> dict[str, Any]:
    path = state_path(anima_name, animas_dir=animas_dir)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(anima_name: str, state: dict[str, Any], *, animas_dir: Path | None = None) -> None:
    path = state_path(anima_name, animas_dir=animas_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, state, indent=2, ensure_ascii=False)


def state_with_defaults(state: dict[str, Any] | None = None) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "status": "healthy",
        "stage": "complete",
        "pid": None,
        "started_at": None,
        "requested_at": None,
        "updated_at": iso(),
        "heartbeat_at": None,
        "reason": None,
        "collection": None,
        "source": None,
        "include_shared": False,
        "repair_nonce": None,
        "last_error": None,
        "last_quarantine_path": None,
        "last_chunks_indexed": 0,
    }
    if state:
        merged.update(state)
    return merged


def _update_state(
    anima_name: str,
    updates: dict[str, Any],
    *,
    animas_dir: Path | None = None,
    current: dict[str, Any] | None = None,
    with_defaults: bool = True,
) -> dict[str, Any]:
    state = read_state(anima_name, animas_dir=animas_dir) if current is None else current
    if with_defaults:
        state = state_with_defaults(state)
    state.update(updates)
    write_state(anima_name, state, animas_dir=animas_dir)
    return state


def prune_recent_signals(signals: list[dict[str, Any]], cutoff: datetime) -> list[dict[str, Any]]:
    return [signal for signal in signals[-50:] if (parse_dt(signal.get("at")) or utc_now()) >= cutoff]


def write_repair_request_state(
    anima_name: str,
    *,
    reason: str,
    collection: str | None,
    source: str,
    include_shared: bool,
    animas_dir: Path | None = None,
) -> None:
    now = iso()
    _update_state(
        anima_name,
        {
            "status": "requested",
            "stage": "detect",
            "pid": None,
            "requested_at": now,
            "updated_at": now,
            "heartbeat_at": now,
            "reason": reason,
            "collection": collection,
            "source": source,
            "include_shared": bool(include_shared),
            "last_error": None,
        },
        animas_dir=animas_dir,
    )


def write_blocked_state(anima_name: str, result: RepairResult, *, animas_dir: Path | None = None) -> None:
    now = iso()
    _update_state(
        anima_name,
        {
            "status": result.status,
            "stage": result.stage or result.status,
            "updated_at": now,
            "heartbeat_at": now,
            "reason": result.reason,
            "last_error": result.error,
        },
        animas_dir=animas_dir,
    )


def update_repair_state(
    anima_name: str,
    *,
    animas_dir: Path | None = None,
    **updates: Any,
) -> dict[str, Any]:
    now = iso()
    return _update_state(
        anima_name,
        {**updates, "updated_at": now, "heartbeat_at": now},
        animas_dir=animas_dir,
    )


def append_state_signal(
    anima_name: str,
    signal: dict[str, Any],
    window: timedelta,
    *,
    animas_dir: Path | None = None,
) -> None:
    state = read_state(anima_name, animas_dir=animas_dir)
    signals = state.get("recent_signals")
    if not isinstance(signals, list):
        signals = []
    cutoff = utc_now() - window
    signals.append(signal)
    _update_state(
        anima_name,
        {"recent_signals": prune_recent_signals(signals, cutoff)},
        animas_dir=animas_dir,
        current=state,
        with_defaults=False,
    )
