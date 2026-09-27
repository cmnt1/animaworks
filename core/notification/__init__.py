from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Human notification subsystem.

Provides ``HumanNotifier`` and channel implementations for sending
notifications from top-level Animas to human administrators via
external messaging services (Slack, LINE, Telegram, Chatwork, ntfy).
"""

import hashlib
import secrets
import threading

from core.notification.notifier import HumanNotifier, NotificationChannel

__all__ = ["HumanNotifier", "NotificationChannel"]


def notification_key_for(subject: str, body: str) -> str:
    """Return the fallback human notification key."""
    return hashlib.sha256(f"{subject}\n{body}".encode()).hexdigest()


class CallHumanKeys:
    """Random per-session confirmation keys for ``call_human``.

    Kept only in this process's memory: nothing an Anima can read or compute
    reveals a key except the denial message that carries the instructions.
    """

    _MAX_SESSIONS = 256

    def __init__(self) -> None:
        self._keys: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()

    def check(self, anima_name: str, session_id: str, sha: str) -> str | None:
        """Return ``None`` if *sha* matches this session's key, else the key to hand out."""
        with self._lock:
            slot = (anima_name, session_id)
            key = self._keys.get(slot)
            if key is None:
                if len(self._keys) >= self._MAX_SESSIONS:
                    self._keys.pop(next(iter(self._keys)))
                key = self._keys[slot] = secrets.token_hex(4)
        return None if str(sha or "").strip().lower() == key else key
