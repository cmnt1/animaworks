from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Recipient inbox state shown to a sender right after an internal DM.

A recipient whose inbox lane is busy does not read new DMs until that run
ends.  The sender otherwise sees only "Message sent", so a long inbox run
looks like the recipient stopped (2026-10-26: one inbox run held for 3h).
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from core.time_utils import ensure_aware, now_local

logger = logging.getLogger(__name__)

# Normal inbox runs finish within a few minutes; below this the notice is noise.
BUSY_NOTICE_MIN_ELAPSED = timedelta(minutes=10)


@dataclass(frozen=True)
class RecipientInboxBusy:
    since: datetime
    unread_count: int
    oldest_unread_at: datetime | None


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return ensure_aware(datetime.fromisoformat(value))
    except (ValueError, TypeError):
        return None


def read_recipient_inbox_busy(shared_dir: Path, name: str) -> RecipientInboxBusy | None:
    """Return inbox-busy state when *name* has been in an inbox run long enough.

    Reads the busy sidecar written by the recipient's process
    (``run/animas/{name}.busy.json``) and counts unread files in
    ``shared/inbox/{name}/``.  Returns None when the inbox lane is idle,
    busy for less than :data:`BUSY_NOTICE_MIN_ELAPSED`, or on any read error.
    """
    sidecar = shared_dir.parent / "run" / "animas" / f"{name}.busy.json"
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or "inbox" not in (data.get("lanes") or []):
        return None

    lane_started = data.get("lane_started_at") or {}
    since = _parse_ts(lane_started.get("inbox") if isinstance(lane_started, dict) else None)
    since = since or _parse_ts(data.get("busy_since"))
    if since is None or now_local() - since < BUSY_NOTICE_MIN_ELAPSED:
        return None

    unread_count = 0
    oldest: float | None = None
    try:
        for f in (shared_dir / "inbox" / name).glob("*.json"):
            try:
                mtime = f.stat().st_mtime
            except OSError:
                continue
            unread_count += 1
            oldest = mtime if oldest is None else min(oldest, mtime)
    except OSError:
        logger.debug("Failed to count unread inbox for %s", name, exc_info=True)

    oldest_at = datetime.fromtimestamp(oldest).astimezone() if oldest is not None else None
    return RecipientInboxBusy(since=since, unread_count=unread_count, oldest_unread_at=oldest_at)
