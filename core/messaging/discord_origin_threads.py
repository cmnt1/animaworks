from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Remember which Discord thread an internal Anima thread was started for.

When an Anima handles a Discord message by asking another Anima (send_message
or delegate_task), the colleague's reply arrives as an ``anima``-sourced inbox
item and would otherwise lose the link to the human's Discord thread.  The
sender records ``internal thread_id -> Discord origin`` here, and the inbox
cycle that processes the reply posts the response back to that thread.
"""

import json
import logging
from datetime import timedelta
from pathlib import Path

from core.time_utils import now_local

logger = logging.getLogger("animaworks.discord_origin_threads")

_FILENAME = "discord_origin_threads.json"
# Origin of the inbox cycle in progress.  Mode S tools run in a separate MCP
# process, so the inbox processor shares it through this file.
_ACTIVE_FILENAME = "discord_inbox_origin.json"
_TTL = timedelta(days=7)


def _path(anima_dir: Path) -> Path:
    return Path(anima_dir) / "run" / _FILENAME


def set_active_origin(anima_dir: Path, origin: dict[str, str] | None) -> None:
    """Publish (or clear, with ``None``/empty) the current inbox cycle's Discord origin."""
    path = Path(anima_dir) / "run" / _ACTIVE_FILENAME
    if not origin:
        path.unlink(missing_ok=True)
        return
    from core.platform.atomic_io import atomic_write_text

    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(origin, ensure_ascii=False))


def active_origin(anima_dir: Path, in_process: dict[str, str] | None = None, trigger: str = "") -> dict[str, str]:
    """Return the Discord origin of the inbox cycle in progress, or ``{}``.

    Only inbox sessions see it, so a heartbeat or chat running alongside the
    inbox cycle does not link its own sends to the Discord thread.
    """
    from core.platform.env import get_env

    if not (trigger.startswith("inbox") or get_env("ANIMAWORKS_SESSION_TYPE", "").strip() == "inbox"):
        return {}
    if in_process:
        return in_process
    try:
        data = json.loads((Path(anima_dir) / "run" / _ACTIVE_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) and data.get("channel_id") else {}


def _load(anima_dir: Path) -> dict[str, dict[str, str]]:
    try:
        data = json.loads(_path(anima_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record_origin(anima_dir: Path, thread_id: str, origin: dict[str, str]) -> None:
    """Link internal *thread_id* to a Discord origin (channel_id/thread_ts/user_id)."""
    if not thread_id or not origin.get("channel_id"):
        return
    from core.platform.atomic_io import atomic_write_text

    now = now_local()
    cutoff = (now - _TTL).isoformat()
    entries = {k: v for k, v in _load(anima_dir).items() if isinstance(v, dict) and v.get("ts", "") >= cutoff}
    entries[thread_id] = {
        "channel_id": origin["channel_id"],
        "thread_ts": origin.get("thread_ts", ""),
        "user_id": origin.get("user_id", ""),
        "ts": now.isoformat(),
    }
    try:
        path = _path(anima_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(path, json.dumps(entries, ensure_ascii=False, indent=2))
    except Exception:
        logger.warning("Failed to record Discord origin for thread %s", thread_id, exc_info=True)


def lookup_origin(anima_dir: Path, thread_id: str) -> dict[str, str] | None:
    """Return the Discord origin recorded for internal *thread_id*, if any."""
    if not thread_id:
        return None
    entry = _load(anima_dir).get(thread_id)
    if not isinstance(entry, dict) or not entry.get("channel_id"):
        return None
    return entry
