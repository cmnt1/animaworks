from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared anima administration operations used by the server and CLI."""

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeleteResult:
    """Outcome of deleting an anima's runtime files and config registration."""

    deleted: bool
    archive_path: Path | None = None
    supervisor_references: tuple[str, ...] = ()
    error: str | None = None


def _read_supervisor_references(animas_dir: Path, deleted_name: str) -> tuple[str, ...]:
    references: list[str] = []
    try:
        anima_dirs = animas_dir.iterdir()
    except OSError:
        logger.debug("Cannot enumerate anima directories for supervisor references", exc_info=True)
        return ()

    for other_dir in anima_dirs:
        if not other_dir.is_dir() or other_dir.name == deleted_name:
            continue
        status_file = other_dir / "status.json"
        if not status_file.is_file():
            continue
        try:
            status = json.loads(status_file.read_text(encoding="utf-8"))
            if isinstance(status, dict) and status.get("supervisor") == deleted_name:
                references.append(other_dir.name)
        except (OSError, json.JSONDecodeError):
            logger.debug("Failed to read supervisor from %s", status_file, exc_info=True)
    return tuple(references)


def delete_anima_files(data_dir: Path, name: str, *, archive: bool) -> DeleteResult:
    """Archive (optionally), delete, and unregister one anima from a runtime.

    A filesystem failure stops the sequence. In particular, config registration
    is retained when removing the anima directory fails.
    """
    if not name or name in {".", ".."} or "/" in name or "\\" in name or ".." in name:
        return DeleteResult(deleted=False, error=f"Invalid anima name: {name!r}")

    data_dir = Path(data_dir)
    animas_dir = data_dir / "animas"
    anima_dir = animas_dir / name
    archive_path: Path | None = None

    if archive:
        try:
            from core.time_utils import now_jst

            archive_dir = data_dir / "archive"
            archive_dir.mkdir(parents=True, exist_ok=True)
            timestamp = now_jst().strftime("%Y%m%d_%H%M%S")
            archive_path = archive_dir / f"{name}_{timestamp}.zip"
            shutil.make_archive(str(archive_path.with_suffix("")), "zip", str(anima_dir))
        except Exception as exc:
            logger.warning("Failed to archive anima '%s' before delete: %s", name, exc)
            return DeleteResult(deleted=False, error=str(exc))

    try:
        shutil.rmtree(anima_dir)
    except Exception as exc:
        logger.warning("Failed to delete anima directory '%s': %s", name, exc)
        return DeleteResult(deleted=False, archive_path=archive_path, error=str(exc))

    try:
        from core.config.models import unregister_anima_from_config

        unregister_anima_from_config(data_dir, name)
        supervisor_references = _read_supervisor_references(animas_dir, name)
    except Exception as exc:
        logger.warning("Anima '%s' files were deleted but follow-up administration failed: %s", name, exc)
        return DeleteResult(deleted=True, archive_path=archive_path, error=str(exc))

    return DeleteResult(
        deleted=True,
        archive_path=archive_path,
        supervisor_references=supervisor_references,
    )
