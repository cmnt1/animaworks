from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Message overflow handler for inbox processing.

Replaces the former 3-stage dedup filter (rate_limit / consolidate /
resolved_topic) with a simple intent-based critical bypass + overflow
inbox.  Critical messages (intent="delegation") always pass through;
non-critical messages beyond a configurable limit are written as
individual files to ``state/overflow_inbox/`` for the Anima to process
at its own pace via ``read_memory_file`` / ``archive_memory_file``.
"""

import logging
import time
from pathlib import Path
from typing import Any

from core.time_utils import now_iso

logger = logging.getLogger("animaworks.dedup")

_NON_CRITICAL_LIMIT = 10
_OVERFLOW_MAX_AGE_DAYS = 7
_OVERFLOW_MAX_FILES = 500


class MessageDeduplicator:
    """Message overflow handler for inbox processing."""

    def __init__(self, anima_dir: Path) -> None:
        self.anima_dir = anima_dir
        self._overflow_dir = anima_dir / "state" / "overflow_inbox"

    def split_critical(self, messages: list[Any]) -> tuple[list[Any], list[Any]]:
        """Split into critical (bypass all filtering) and non-critical.

        Critical messages are those with ``intent="delegation"``; they
        are never subject to overflow limits.
        """
        critical = [m for m in messages if getattr(m, "intent", "") == "delegation"]
        non_critical = [m for m in messages if getattr(m, "intent", "") != "delegation"]
        return critical, non_critical

    def overflow_to_files(self, messages: list[Any]) -> tuple[list[Any], int]:
        """Keep first N messages, write the rest to overflow_inbox/ as individual files.

        Also runs auto-cleanup to prevent unbounded accumulation.

        Returns:
            Tuple of (kept_messages, overflow_count).
        """
        self._cleanup_overflow()

        if len(messages) <= _NON_CRITICAL_LIMIT:
            return messages, 0

        kept = messages[:_NON_CRITICAL_LIMIT]
        overflow = messages[_NON_CRITICAL_LIMIT:]

        self._overflow_dir.mkdir(parents=True, exist_ok=True)
        for m in overflow:
            self._write_overflow_file(m)

        return kept, len(overflow)

    def _write_overflow_file(self, msg: Any) -> None:
        """Write a single message as an individual .md file."""
        ts = now_iso()
        ts_short = ts[:19].replace(":", "").replace("-", "").replace("T", "_")
        sender = getattr(msg, "from_person", "unknown")
        base = f"{ts_short}_{sender}"
        path = self._overflow_dir / f"{base}.md"

        counter = 2
        while path.exists():
            path = self._overflow_dir / f"{base}_{counter}.md"
            counter += 1

        content_parts = [
            "---",
            f"from: {sender}",
            f"ts: {ts}",
            f"intent: {getattr(msg, 'intent', '')}",
            f"type: {getattr(msg, 'type', 'message')}",
            "---",
            "",
            getattr(msg, "content", str(msg)),
        ]
        path.write_text("\n".join(content_parts), encoding="utf-8")

    def _cleanup_overflow(self) -> None:
        """Remove overflow files older than _OVERFLOW_MAX_AGE_DAYS and cap total count."""
        if not self._overflow_dir.exists():
            return

        files = sorted(self._overflow_dir.glob("*.md"), key=lambda p: p.stat().st_mtime)
        if not files:
            return

        cutoff = time.time() - _OVERFLOW_MAX_AGE_DAYS * 86400
        removed = 0
        for f in files:
            try:
                if f.stat().st_mtime < cutoff:
                    f.unlink()
                    removed += 1
            except OSError:
                pass

        remaining = sorted(self._overflow_dir.glob("*.md"), key=lambda p: p.stat().st_mtime)
        if len(remaining) > _OVERFLOW_MAX_FILES:
            excess = remaining[: len(remaining) - _OVERFLOW_MAX_FILES]
            for f in excess:
                try:
                    f.unlink()
                    removed += 1
                except OSError:
                    pass

        if removed:
            logger.info(
                "Cleaned up %d overflow_inbox files (age>%dd or count>%d)",
                removed,
                _OVERFLOW_MAX_AGE_DAYS,
                _OVERFLOW_MAX_FILES,
            )
