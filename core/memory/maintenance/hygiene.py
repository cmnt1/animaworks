from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic checks for memory files that need semantic cleanup."""

import json
from pathlib import Path
from typing import Any

from core.memory.io import atomic_write_text

_REPORT_CATEGORIES = (
    "merged_leftovers",
    "inherited_dirs",
    "mdc_files",
    "oversized_knowledge",
    "noncanonical_archive_dirs",
)
_NONCANONICAL_ARCHIVE_NAMES = ("archived", "_archived", ".archive")
_OVERSIZED_KNOWLEDGE_BYTES = 32 * 1024


def scan_memory_hygiene(anima_dir: Path) -> dict[str, list[dict[str, Any]]]:
    """Scan one Anima's active knowledge tree and persist its hygiene report.

    The scan never changes memory files. The only write is the report at
    ``state/memory_hygiene.json`` for operator review.
    """
    anima_dir = Path(anima_dir)
    knowledge_dir = anima_dir / "knowledge"
    report_path = anima_dir / "state" / "memory_hygiene.json"

    report: dict[str, list[dict[str, Any]]] = {category: [] for category in _REPORT_CATEGORIES}
    if knowledge_dir.is_dir():
        active_files = sorted(
            path for path in knowledge_dir.rglob("*") if path.is_file() and not _is_in_archive(path, knowledge_dir)
        )

        for path in active_files:
            relative = path.relative_to(anima_dir).as_posix()
            if path.name.startswith("_merged_"):
                report["merged_leftovers"].append(_entry(relative))
            if path.suffix == ".mdc":
                report["mdc_files"].append(_entry(relative))
            if path.suffix == ".md" and path.stat().st_size > _OVERSIZED_KNOWLEDGE_BYTES:
                report["oversized_knowledge"].append(_entry(relative, size_bytes=path.stat().st_size))

        for path in sorted(knowledge_dir.glob("inherited-*")):
            if path.is_dir():
                relative = path.relative_to(anima_dir).as_posix()
                report["inherited_dirs"].append(_entry(relative))

        for name in _NONCANONICAL_ARCHIVE_NAMES:
            path = knowledge_dir / name
            if path.is_dir():
                relative = path.relative_to(anima_dir).as_posix()
                report["noncanonical_archive_dirs"].append(_entry(relative))

    atomic_write_text(report_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def _is_in_archive(path: Path, knowledge_dir: Path) -> bool:
    """Return whether *path* is below a canonical ``archive/`` directory."""
    return "archive" in path.relative_to(knowledge_dir).parts[:-1]


def _entry(path: str, **extra: Any) -> dict[str, Any]:
    return {"path": path, **extra}


__all__ = ["scan_memory_hygiene"]
