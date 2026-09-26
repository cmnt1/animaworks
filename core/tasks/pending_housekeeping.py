from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Pending task file cleanup helpers."""

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

from core.time_utils import now_local

logger = logging.getLogger("animaworks.housekeeping.pending")


def cleanup_pending_failed(
    animas_dir: Path,
    retention_days: int,
) -> dict[str, Any]:
    """Delete old failed task files from pending failed directories."""
    if not animas_dir.exists():
        return {"skipped": True}

    cutoff_ts = (now_local() - timedelta(days=retention_days)).timestamp()
    total_deleted = 0

    failed_subdirs = (
        Path("state") / "pending" / "failed",
        Path("state") / "background_tasks" / "pending" / "failed",
    )

    for anima_dir in sorted(animas_dir.iterdir()):
        if not anima_dir.is_dir():
            continue
        for rel in failed_subdirs:
            failed_dir = anima_dir / rel
            if not failed_dir.is_dir():
                continue
            for path in failed_dir.glob("*.json"):
                try:
                    if path.stat().st_mtime < cutoff_ts:
                        path.unlink()
                        total_deleted += 1
                except OSError:
                    logger.warning("Failed to delete failed task: %s", path)

    if total_deleted:
        logger.info("Pending failed cleanup: deleted %d files", total_deleted)
    return {"deleted_files": total_deleted}
