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
from pathlib import Path
from typing import Any

from core.platform.state_writer import get_state_writer, is_task_runner_process, run_writer_sync
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

    def overflow_to_files(self, messages: list[Any]) -> tuple[list[Any], int] | Any:
        """Keep first N messages, write the rest to overflow_inbox/ as individual files.

        Also runs auto-cleanup to prevent unbounded accumulation.

        Returns:
            Tuple of (kept_messages, overflow_count).
        """
        if is_task_runner_process():
            return self.aoverflow_to_files(messages)
        return run_writer_sync(get_state_writer(self.anima_dir), self.aoverflow_to_files(messages))

    async def aoverflow_to_files(self, messages: list[Any]) -> tuple[list[Any], int]:
        """Async overflow persistence used by task-runner inbox contracts."""
        writer = get_state_writer(self.anima_dir)
        await writer.cleanup_inbox_overflow()
        if len(messages) <= _NON_CRITICAL_LIMIT:
            return messages, 0

        kept = messages[:_NON_CRITICAL_LIMIT]
        overflow = messages[_NON_CRITICAL_LIMIT:]
        for message in overflow:
            await writer.write_inbox_overflow_file(
                {
                    "from_person": getattr(message, "from_person", "unknown"),
                    "ts": now_iso(),
                    "intent": getattr(message, "intent", ""),
                    "type": getattr(message, "type", "message"),
                    "content": getattr(message, "content", str(message)),
                }
            )
        return kept, len(overflow)

    def _write_overflow_file(self, msg: Any) -> None:
        """Write one overflow item via the process state writer."""
        writer = get_state_writer(self.anima_dir)
        run_writer_sync(
            writer,
            writer.write_inbox_overflow_file(
                {
                    "from_person": getattr(msg, "from_person", "unknown"),
                    "ts": now_iso(),
                    "intent": getattr(msg, "intent", ""),
                    "type": getattr(msg, "type", "message"),
                    "content": getattr(msg, "content", str(msg)),
                }
            ),
        )

    def _cleanup_overflow(self) -> None:
        """Remove stale overflow files via the process state writer."""
        writer = get_state_writer(self.anima_dir)
        run_writer_sync(writer, writer.cleanup_inbox_overflow())
