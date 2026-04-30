from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Checkpoint manager for resumable migration."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


# ── CheckpointManager ──────────────────────────────────────────


class CheckpointManager:
    """Track migration progress for resume capability."""

    def __init__(self, checkpoint_path: Path) -> None:
        self._path = checkpoint_path
        self._completed: set[str] = set()
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            for line in self._path.read_text(encoding="utf-8").splitlines():
                try:
                    entry = json.loads(line)
                    if entry.get("status") == "done":
                        self._completed.add(entry["key"])
                except (json.JSONDecodeError, KeyError):
                    continue

    def is_done(self, key: str) -> bool:
        """Check whether *key* has already been migrated."""
        return key in self._completed

    def mark_done(self, key: str, *, anima: str = "", file: str = "") -> None:
        """Record successful migration of *key*."""
        self._completed.add(key)
        entry = {
            "key": key,
            "anima": anima,
            "file": file,
            "status": "done",
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def mark_error(self, key: str, error: str, *, anima: str = "", file: str = "") -> None:
        """Record a failed migration attempt for *key*."""
        entry = {
            "key": key,
            "anima": anima,
            "file": file,
            "status": "error",
            "error": error,
        }
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    @property
    def completed_count(self) -> int:
        """Number of successfully completed items."""
        return len(self._completed)

    def reset(self) -> None:
        """Clear all checkpoint state."""
        self._completed.clear()
        if self._path.exists():
            self._path.unlink()
