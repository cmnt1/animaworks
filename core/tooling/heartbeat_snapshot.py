from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Read-only heartbeat observation snapshot helpers."""

import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.memory.task_queue import TaskQueueManager
from core.paths import get_animas_dir, get_shared_dir
from core.time_utils import get_app_timezone, now_local

_SAFE_ANIMA_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_RECENT_EXCLUDED_DIRS = {".claude", "activity_log", "run", "shortterm", "vectordb", "__pycache__"}
_ACTIVE_STATUSES = {"pending", "in_progress", "blocked", "delegated"}
_INBOX_PREVIEW_CHARS = 500


def build_heartbeat_observe_snapshot(
    anima_dir: Path,
    *,
    peers: list[str] | None = None,
    recent_minutes: int = 60,
    max_items: int = 5,
) -> dict[str, Any]:
    """Return a compact read-only snapshot for heartbeat Observe.

    The snapshot intentionally exposes only small structured summaries from
    well-known AnimaWorks runtime locations. It accepts peer names, not paths,
    so heartbeat can avoid arbitrary shell reads for routine health checks.
    """
    recent_minutes = _clamp_int(recent_minutes, minimum=1, maximum=24 * 60)
    max_items = _clamp_int(max_items, minimum=1, maximum=20)
    anima_dir = anima_dir.resolve()
    anima_name = anima_dir.name
    observed_at = now_local()

    peer_names = _resolve_peer_names(anima_name, peers)

    return {
        "status": "ok",
        "tool": "heartbeat_observe_snapshot",
        "observed_at": observed_at.isoformat(),
        "anima": anima_name,
        "scope": {
            "data": "counts, timestamps, bounded inbox previews, latest status summaries only",
            "mutates": False,
            "arbitrary_paths": False,
        },
        "inbox": _snapshot_inbox(anima_name, max_items=max_items),
        "task_queue": _snapshot_task_queue(anima_dir, observed_at=observed_at, max_items=max_items),
        "pending_files": _snapshot_pending_files(anima_dir, max_items=max_items),
        "background_notifications": _snapshot_background_notifications(anima_dir, max_items=max_items),
        "peer_activity": _snapshot_peer_activity(peer_names, max_items=max_items),
        "recent_own_files": _snapshot_recent_own_files(
            anima_dir,
            observed_at=observed_at,
            recent_minutes=recent_minutes,
            max_items=max_items,
        ),
    }


def _clamp_int(value: Any, *, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return minimum
    return max(minimum, min(maximum, parsed))


def _mtime_iso(path: Path) -> str | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=get_app_timezone()).isoformat()
    except OSError:
        return None


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        return path.name


def _safe_anima_name(name: str) -> str | None:
    clean = str(name).strip()
    if not clean or not _SAFE_ANIMA_RE.fullmatch(clean):
        return None
    return clean


def _resolve_peer_names(anima_name: str, peers: list[str] | None) -> list[str]:
    if peers:
        names = [_safe_anima_name(name) for name in peers]
        return sorted({name for name in names if name and name != anima_name})

    try:
        from core.config.models import load_config

        config = load_config()
        mine = config.animas.get(anima_name)
        supervisor = mine.supervisor if mine else None
        resolved: set[str] = set()
        for other_name, other_cfg in config.animas.items():
            if other_name == anima_name:
                continue
            if other_cfg.supervisor == anima_name or (supervisor is not None and other_cfg.supervisor == supervisor):
                safe = _safe_anima_name(other_name)
                if safe:
                    resolved.add(safe)
        return sorted(resolved)
    except Exception:
        return []


def _snapshot_inbox(anima_name: str, *, max_items: int) -> dict[str, Any]:
    inbox_dir = get_shared_dir() / "inbox" / anima_name
    files = _list_files(inbox_dir, "*.json")
    files.sort(key=lambda p: _safe_stat_mtime(p) or 0)
    sample_files = files[:max_items]
    return {
        "path_kind": "shared/inbox/{anima}",
        "exists": inbox_dir.is_dir(),
        "unread_count": len(files),
        "oldest_mtime": _mtime_iso(files[0]) if files else None,
        "newest_mtime": _mtime_iso(files[-1]) if files else None,
        "sample_files": [p.name for p in sample_files],
        "message_previews": [_snapshot_inbox_message(path) for path in sample_files],
    }


def _snapshot_inbox_message(path: Path) -> dict[str, Any]:
    preview: dict[str, Any] = {
        "file": path.name,
        "mtime": _mtime_iso(path),
        "size_bytes": _safe_size(path),
    }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError) as exc:
        preview.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        return preview

    if not isinstance(data, dict):
        preview.update({"status": "unsupported", "json_type": type(data).__name__})
        return preview

    content = _first_text(data, "content", "message", "text", "body", "summary", "original_instruction")
    meta = data.get("meta")
    if not isinstance(meta, dict):
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}

    preview.update(
        {
            "status": "ok",
            "id": _first_text(data, "id", "message_id", "source_message_id"),
            "thread_id": _first_text(data, "thread_id"),
            "from": _first_text(data, "from_person", "from", "sender", "source"),
            "to": _first_text(data, "to_person", "to", "recipient", "target"),
            "type": _first_text(data, "type", "kind", "message_type"),
            "intent": _first_text(data, "intent"),
            "source": _first_text(data, "source"),
            "priority": _first_text(data, "priority", "urgency"),
            "timestamp": _first_text(data, "timestamp", "ts", "created_at", "sent_at"),
            "routing_hint": _inbox_routing_hint(data, content),
            "content_preview": _trim(content, _INBOX_PREVIEW_CHARS),
            "meta_keys": sorted(str(key) for key in meta)[:20],
        }
    )
    return preview


def _first_text(data: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _inbox_routing_hint(data: dict[str, Any], content: str) -> str:
    haystack = " ".join(
        [
            _first_text(data, "from_person", "from", "sender", "source"),
            _first_text(data, "type", "kind", "message_type"),
            _first_text(data, "intent"),
            content,
        ]
    ).lower()
    if "governor" in haystack:
        return "governor"
    if "changelog" in haystack:
        return "changelog"
    if any(token in haystack for token in ("owner", "human", "<@")):
        return "human_or_owner"
    if _first_text(data, "from_person", "from", "sender"):
        return "anima_or_external"
    return "unknown"


def _snapshot_task_queue(anima_dir: Path, *, observed_at: datetime, max_items: int) -> dict[str, Any]:
    manager = TaskQueueManager(anima_dir)
    queue_path = manager.queue_path
    archive_path = manager.archive_path
    result: dict[str, Any] = {
        "path_kind": "state/task_queue.jsonl",
        "exists": queue_path.is_file(),
        "size_bytes": _safe_size(queue_path),
        "mtime": _mtime_iso(queue_path),
        "archive_size_bytes": _safe_size(archive_path),
        "archive_mtime": _mtime_iso(archive_path),
        "active_count": 0,
        "active_by_status": {},
        "overdue_count": 0,
        "stale_count": 0,
        "active_samples": [],
    }
    try:
        active = manager.load_active_tasks()
    except Exception as exc:
        result.update({"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        return result

    status_counts = Counter(task.status for task in active.values())
    result["active_count"] = len(active)
    result["active_by_status"] = dict(sorted(status_counts.items()))

    samples: list[dict[str, Any]] = []
    overdue_count = 0
    stale_count = 0
    for task in sorted(active.values(), key=lambda t: t.updated_at or t.ts)[:max_items]:
        overdue = _deadline_overdue(task.deadline, observed_at)
        stale_minutes = _age_minutes(task.updated_at or task.ts, observed_at)
        if overdue:
            overdue_count += 1
        if stale_minutes is not None and stale_minutes >= 30:
            stale_count += 1
        samples.append(
            {
                "task_id": task.task_id,
                "status": task.status,
                "summary": _trim(task.summary, 120),
                "deadline": task.deadline,
                "updated_at": task.updated_at,
                "overdue": overdue,
                "stale_minutes": stale_minutes,
            }
        )

    for task in list(active.values())[max_items:]:
        if _deadline_overdue(task.deadline, observed_at):
            overdue_count += 1
        stale_minutes = _age_minutes(task.updated_at or task.ts, observed_at)
        if stale_minutes is not None and stale_minutes >= 30:
            stale_count += 1

    result["overdue_count"] = overdue_count
    result["stale_count"] = stale_count
    result["active_samples"] = samples
    result["active_statuses"] = sorted(_ACTIVE_STATUSES)
    return result


def _snapshot_pending_files(anima_dir: Path, *, max_items: int) -> dict[str, Any]:
    pending_dir = anima_dir / "state" / "pending"
    direct = _list_files(pending_dir, "*.md")
    recursive = _list_files(pending_dir, "*.md", recursive=True)
    direct.sort(key=lambda p: p.name)
    return {
        "path_kind": "state/pending",
        "exists": pending_dir.is_dir(),
        "direct_count": len(direct),
        "recursive_count": len(recursive),
        "sample_files": [_rel(p, pending_dir) for p in direct[:max_items]],
    }


def _snapshot_background_notifications(anima_dir: Path, *, max_items: int) -> dict[str, Any]:
    notif_dir = anima_dir / "state" / "background_notifications"
    files = _list_files(notif_dir, "*.md")
    files.sort(key=lambda p: _safe_stat_mtime(p) or 0, reverse=True)
    return {
        "path_kind": "state/background_notifications",
        "exists": notif_dir.is_dir(),
        "count": len(files),
        "newest_mtime": _mtime_iso(files[0]) if files else None,
        "sample_files": [p.name for p in files[:max_items]],
    }


def _snapshot_peer_activity(peer_names: list[str], *, max_items: int) -> dict[str, Any]:
    animas_dir = get_animas_dir()
    peers: dict[str, Any] = {}
    for name in peer_names[:20]:
        peers[name] = _snapshot_one_peer_activity(animas_dir / name, max_items=max_items)
    return {"count": len(peers), "peers": peers}


def _snapshot_one_peer_activity(peer_dir: Path, *, max_items: int) -> dict[str, Any]:
    activity_dir = peer_dir / "activity_log"
    logs = _list_files(activity_dir, "*.jsonl")
    logs.sort(key=lambda p: (p.name, _safe_stat_mtime(p) or 0), reverse=True)
    if not logs:
        return {"exists": activity_dir.is_dir(), "latest_log": None, "latest_event": None}

    latest = logs[0]
    latest_events = _read_latest_jsonl_events(latest, max_items=1)
    return {
        "exists": True,
        "latest_log": latest.name,
        "latest_log_mtime": _mtime_iso(latest),
        "latest_event": latest_events[0] if latest_events else None,
    }


def _snapshot_recent_own_files(
    anima_dir: Path,
    *,
    observed_at: datetime,
    recent_minutes: int,
    max_items: int,
) -> dict[str, Any]:
    cutoff = observed_at - timedelta(minutes=recent_minutes)
    recent: list[Path] = []
    try:
        for path in anima_dir.rglob("*"):
            if not path.is_file():
                continue
            if any(part in _RECENT_EXCLUDED_DIRS for part in path.relative_to(anima_dir).parts[:-1]):
                continue
            mtime = _safe_stat_mtime(path)
            if mtime is None:
                continue
            dt = datetime.fromtimestamp(mtime, tz=get_app_timezone())
            if dt >= cutoff:
                recent.append(path)
    except OSError:
        recent = []

    recent.sort(key=lambda p: _safe_stat_mtime(p) or 0, reverse=True)
    return {
        "path_kind": "own_anima_dir_recent_files",
        "recent_minutes": recent_minutes,
        "count": len(recent),
        "sample_files": [{"path": _rel(p, anima_dir), "mtime": _mtime_iso(p)} for p in recent[:max_items]],
        "excluded_dirs": sorted(_RECENT_EXCLUDED_DIRS),
    }


def _list_files(path: Path, pattern: str, *, recursive: bool = False) -> list[Path]:
    try:
        if not path.is_dir():
            return []
        iterator = path.rglob(pattern) if recursive else path.glob(pattern)
        return [p for p in iterator if p.is_file()]
    except OSError:
        return []


def _safe_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _safe_stat_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _read_latest_jsonl_events(path: Path, *, max_items: int) -> list[dict[str, Any]]:
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    tail = raw[-64_000:].decode("utf-8", errors="replace")
    events: list[dict[str, Any]] = []
    for line in reversed(tail.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(
            {
                "ts": data.get("ts"),
                "type": data.get("type"),
                "tool": data.get("tool"),
                "summary": _trim(data.get("summary") or data.get("content") or "", 180),
            }
        )
        if len(events) >= max_items:
            break
    return events


def _deadline_overdue(deadline: str | None, observed_at: datetime) -> bool:
    if not deadline:
        return False
    try:
        dt = datetime.fromisoformat(deadline)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=get_app_timezone())
        return dt <= observed_at
    except (TypeError, ValueError):
        return False


def _age_minutes(ts: str | None, observed_at: datetime) -> int | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=get_app_timezone())
        return max(0, int((observed_at - dt).total_seconds() // 60))
    except (TypeError, ValueError):
        return None


def _trim(text: Any, limit: int) -> str:
    value = str(text or "").replace("\r", " ").replace("\n", " ").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "..."
