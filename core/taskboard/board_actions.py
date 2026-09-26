from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Lease-guarded task board writes shared by the CLI and the internal API.

Sandboxed animas cannot write the shared task database, so the CLI falls back
to ``POST /api/internal/task-board-action``, which runs the same function on
the host. Keeping one implementation keeps the lease rules identical.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

LEASE_ACTIONS = frozenset({"claim", "release", "done", "cancel", "note"})
_ACTIVE_STATUSES = frozenset({"pending", "in_progress", "delegated"})


class BoardActionError(Exception):
    """A refused board action; ``exit_code`` mirrors the CLI contract."""

    def __init__(self, message: str, exit_code: int = 1, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.payload = payload


def get_task_store():
    from core.paths import get_taskboard_db_path
    from core.taskboard.tasks import TaskStore

    return TaskStore(get_taskboard_db_path())


def find_task_matches(store, task_id: str, owner: str | None = None) -> list[dict[str, Any]]:
    """Resolve canonical IDs and viewer aliases without assuming a current anima."""
    matches: dict[tuple[str, str], dict[str, Any]] = {}
    with store.reader() as db:
        direct = db.execute("SELECT anima,task_id,entry_json FROM tasks WHERE task_id=?", (task_id,)).fetchall()
        for row in direct:
            if owner is None or row["anima"] == owner:
                matches[(row["anima"], row["task_id"])] = {
                    "anima": row["anima"],
                    "task_id": row["task_id"],
                    "requested_id": task_id,
                    "entry": json.loads(row["entry_json"]),
                }
        aliases = db.execute(
            "SELECT a.anima,a.task_id,t.entry_json FROM task_aliases a "
            "JOIN tasks t ON t.anima=a.anima AND t.task_id=a.task_id WHERE a.alias=?",
            (task_id,),
        ).fetchall()
        for row in aliases:
            if owner is None or row["anima"] == owner:
                matches.setdefault(
                    (row["anima"], row["task_id"]),
                    {
                        "anima": row["anima"],
                        "task_id": row["task_id"],
                        "requested_id": task_id,
                        "entry": json.loads(row["entry_json"]),
                    },
                )
    return list(matches.values())


def resolve_task(store, task_id: str) -> dict[str, Any]:
    matches = find_task_matches(store, task_id)
    if not matches:
        raise BoardActionError(f"task not found: {task_id}", 1)
    if len(matches) > 1:
        owners = ", ".join(f"{item['anima']}/{item['task_id']}" for item in matches)
        raise BoardActionError(f"task ID is ambiguous ({owners}); use task show ID --anima OWNER", 2)
    return matches[0]


def notify_task_owner(actor: str, owner: str, task_id: str, action: str, detail: str) -> str | None:
    """Tell the owner another actor changed their task. Returns a warning on failure."""
    if actor == owner:
        return None
    return _send_task_notice(actor, owner, task_id, action, detail)


def task_delegator(entry: dict[str, Any], owner: str) -> str | None:
    """Return the anima that delegated this task, if it still exists."""
    from core.paths import get_animas_dir

    if entry.get("source") != "anima":
        return None
    for name in entry.get("relay_chain") or []:
        if isinstance(name, str) and name and name != owner:
            return name if (get_animas_dir() / name).is_dir() else None
    return None


def notify_task_delegator(
    actor: str, owner: str, entry: dict[str, Any], task_id: str, action: str, detail: str
) -> str | None:
    """Tell the delegator their delegated task was closed, so it is not re-sent."""
    delegator = task_delegator(entry, owner)
    if delegator is None or delegator == actor:
        return None
    return _send_task_notice(actor, delegator, task_id, action, detail, owner=owner)


def _send_task_notice(
    actor: str, to: str, task_id: str, action: str, detail: str, *, owner: str | None = None
) -> str | None:
    from core.taskboard.notices import queue_task_notice

    return queue_task_notice(actor, to, task_id, action, detail, owner=owner)


def run_board_action(
    *,
    actor: str,
    action: str,
    task_id: str,
    ttl_seconds: int | None = None,
    text: str | None = None,
    store=None,
) -> dict[str, Any]:
    """Apply one lease-guarded action and return a JSON-safe result.

    Raises ``BoardActionError`` for refusals. Storage errors propagate so the
    CLI can decide whether to retry through the host.
    """
    from core.memory.task_queue import TaskQueueManager
    from core.paths import get_animas_dir

    if action not in LEASE_ACTIONS:
        raise BoardActionError(f"unknown board action: {action}", 2)
    store = store or get_task_store()
    match = resolve_task(store, task_id)
    owner, canonical_id = match["anima"], match["task_id"]
    entry = match["entry"]

    if action == "claim":
        if not ttl_seconds or ttl_seconds <= 0:
            raise BoardActionError("TTL must be greater than 0", 2)
        if entry.get("status") not in _ACTIVE_STATUSES:
            raise BoardActionError(f"task is not active: {task_id}", 1)
        lease = store.acquire_lease(owner, canonical_id, actor, ttl_seconds)
        if lease is None:
            current = store.get_lease(owner, canonical_id)
            holder = current["holder"] if current else "another actor"
            expiry = f" until {current['expires_at']}" if current else ""
            raise BoardActionError(f"Lease held by {holder}{expiry}", 2, {"ok": False, "lease": current})
        return {
            "ok": True,
            "lease": lease,
            "message": f"Lease acquired for {owner}/{canonical_id} until {lease['expires_at']}",
        }

    if action == "release":
        if not store.release_lease(owner, canonical_id, actor):
            raise BoardActionError(
                f"No lease held by {actor} for {owner}/{canonical_id}",
                1,
                {"ok": False, "owner": owner, "task_id": canonical_id},
            )
        return {
            "ok": True,
            "owner": owner,
            "task_id": canonical_id,
            "message": f"Lease released for {owner}/{canonical_id}",
        }

    if entry.get("status") in {"done", "cancelled"}:
        return {
            "ok": True,
            "unchanged": True,
            "owner": owner,
            "task_id": canonical_id,
            "status": entry["status"],
            "message": f"Task is already {entry['status']}; unchanged",
        }

    lease = store.get_lease(owner, canonical_id)
    if lease and lease["holder"] != actor:
        raise BoardActionError(f"task is leased by {lease['holder']} until {lease['expires_at']}", 2)
    if actor != owner and lease is None:
        raise BoardActionError("claim a lease before changing another anima's task", 2)
    if not (text or "").strip():
        raise BoardActionError("note/reason must not be empty", 2)

    manager = TaskQueueManager(get_animas_dir() / owner)
    notes = entry.get("meta", {}).get("notes", [])
    if not isinstance(notes, list):
        notes = []
    notes = [*notes, {"ts": datetime.now(UTC).isoformat(), "by": actor, "text": text}]
    updated = manager.update_meta(canonical_id, {"notes": notes})
    if updated is None:
        raise BoardActionError(f"task not found: {canonical_id}", 1)
    if action in {"done", "cancel"}:
        status = "done" if action == "done" else "cancelled"
        updated = manager.update_status(canonical_id, status)
        if updated is None:
            raise BoardActionError(f"failed to update task status: {canonical_id}", 3)
    result: dict[str, Any] = {
        "ok": True,
        "owner": owner,
        "task_id": canonical_id,
        "status": updated.status,
        "note": text,
        "lease": store.get_lease(owner, canonical_id),
        "message": f"Task {owner}/{canonical_id} {action} recorded (status: {updated.status})",
    }
    warnings = [notify_task_owner(actor, owner, canonical_id, action, text or "")]
    if action in {"done", "cancel"}:
        warnings.append(notify_task_delegator(actor, owner, entry, canonical_id, action, text or ""))
    warnings = [w for w in warnings if w]
    if warnings:
        result["warning"] = "; ".join(warnings)
    return result
