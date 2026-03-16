from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger("animaworks.lifecycle")


class RateLimiterMixin:
    """Mixin providing rate limiting and cascade detection for message-triggered heartbeats."""

    def _is_in_cooldown(self, name: str) -> bool:
        """Return True if a message-triggered heartbeat finished too recently."""
        last = self._last_msg_heartbeat_end.get(name, 0.0)
        return (time.monotonic() - last) < self._cooldown_s

    def _check_cascade(self, anima_name: str, senders: set[str]) -> bool:
        """Return True if any (anima, sender) pair exceeds cascade threshold."""
        cascade_window = self._cascade_window_s
        cascade_threshold = self._cascade_threshold
        now = time.monotonic()
        for sender in senders:
            keys = [(anima_name, sender), (sender, anima_name)]
            total = 0
            for k in keys:
                times = self._pair_heartbeat_times.get(k, [])
                # Evict expired entries
                times = [t for t in times if now - t < cascade_window]
                self._pair_heartbeat_times[k] = times
                if not times and k in self._pair_heartbeat_times:
                    del self._pair_heartbeat_times[k]
                total += len(times)
            if total >= cascade_threshold:
                logger.warning(
                    "CASCADE DETECTED: %s <-> %s (%d round-trips in %ds window). "
                    "Suppressing message-triggered heartbeat.",
                    anima_name,
                    sender,
                    total,
                    cascade_window,
                )
                return True
        return False

    def _record_pair_heartbeat(self, anima_name: str, senders: set[str]) -> None:
        """Record a heartbeat exchange for cascade tracking."""
        now = time.monotonic()
        for sender in senders:
            key = (anima_name, sender)
            self._pair_heartbeat_times.setdefault(key, []).append(now)
