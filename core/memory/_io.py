from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Crash-safe I/O utilities for the memory subsystem.

Provides atomic file writes (temp + rename) and fsync-backed appends
to protect against data loss on process crash or power failure.
"""

import logging
import shutil
from pathlib import Path
from typing import Any

from core.platform.atomic_io import atomic_write_json as _platform_atomic_write_json
from core.platform.atomic_io import atomic_write_text as _platform_atomic_write_text
from core.time_utils import now_local

logger = logging.getLogger("animaworks.memory._io")


def archive_episode_before_write(anima_dir: Path, episode_path: Path) -> Path | None:
    """Copy an existing episode to archive/episodes before overwriting it."""
    if not episode_path.exists():
        return None

    archive_dir = anima_dir / "archive" / "episodes"
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now_local().strftime("%Y%m%dT%H%M%S%z")
    archive_path = archive_dir / f"{episode_path.stem}_{timestamp}{episode_path.suffix}"
    counter = 1
    while archive_path.exists():
        archive_path = archive_dir / f"{episode_path.stem}_{timestamp}_{counter}{episode_path.suffix}"
        counter += 1
    shutil.copy2(episode_path, archive_path)
    return archive_path


def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write content atomically, wrapping I/O failures as MemoryWriteError."""
    from core.exceptions import MemoryWriteError

    try:
        _platform_atomic_write_text(path, content, encoding=encoding)
    except OSError as exc:
        raise MemoryWriteError(f"Atomic write failed for {path}: {exc}") from exc


def atomic_write_json(path: Path, obj: Any, **kwargs: Any) -> None:
    """Atomically write JSON, wrapping I/O failures as MemoryWriteError."""
    from core.exceptions import MemoryWriteError

    try:
        _platform_atomic_write_json(path, obj, **kwargs)
    except OSError as exc:
        raise MemoryWriteError(f"Atomic write failed for {path}: {exc}") from exc


def cleanup_tmp_files(directory: Path, prefix: str = ".") -> int:
    """Remove stale .tmp files from directory. Returns count removed."""
    removed = 0
    if not directory.exists():
        return removed
    for tmp in directory.glob(f"{prefix}*.tmp"):
        try:
            tmp.unlink()
            removed += 1
        except OSError:
            logger.debug("Failed to remove stale tmp file %s", tmp, exc_info=True)
    return removed
