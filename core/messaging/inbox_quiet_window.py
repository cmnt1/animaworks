from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import logging
from pathlib import Path

from core.schemas import Message

logger = logging.getLogger(__name__)


def is_deferrable_inbox_message(msg: Message) -> bool:
    """Return whether an inbox message may wait for the quiet window."""
    return msg.source == "system" or msg.intent == "report" or msg.meta.get("event") == "task_completed"


def classify_unread_messages(inbox_dir: Path) -> tuple[int, bool]:
    """Return unread count and whether every unread file is safely deferrable.

    Invalid or unreadable inbox files are classified as immediate so the normal
    inbox processing path can quarantine them without waiting for the timer.
    """
    files = sorted(inbox_dir.glob("*.json"))
    if not files:
        return 0, False

    for path in files:
        try:
            msg = Message.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            logger.debug("Unread inbox file cannot be classified for quiet window: %s", path, exc_info=True)
            return len(files), False
        if not is_deferrable_inbox_message(msg):
            return len(files), False

    return len(files), True
