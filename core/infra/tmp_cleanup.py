from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Scan and clean AnimaWorks runtime tmp directories."""

import logging
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.paths import PROJECT_DIR, get_data_dir

logger = logging.getLogger(__name__)

_SIZE_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)([KMGTP]?)$", re.IGNORECASE)
_SIZE_UNITS = {
    "": 1,
    "K": 1024,
    "M": 1024**2,
    "G": 1024**3,
    "T": 1024**4,
    "P": 1024**5,
}
_PRESERVED_SUBDIRS = frozenset({"attachments", "skill_hub"})


@dataclass(frozen=True)
class TmpEntry:
    """Summary of one top-level item under a tmp root."""

    path: Path
    size_bytes: int
    mtime: float
    is_dir: bool


@dataclass(frozen=True)
class TmpScanResult:
    """Aggregated scan result for one tmp root."""

    root: Path
    total_bytes: int
    entry_count: int
    entries: tuple[TmpEntry, ...]


@dataclass
class TmpCleanResult:
    """Result of a cleanup run for one tmp root."""

    root: Path
    removed_count: int = 0
    removed_bytes: int = 0
    skipped_count: int = 0
    errors: list[str] = field(default_factory=list)


def resolve_tmp_roots(*, include_project: bool = False) -> list[Path]:
    """Return tmp directories to inspect or clean."""
    roots = [(get_data_dir() / "tmp").resolve()]
    if include_project:
        project_tmp = (PROJECT_DIR / "tmp").resolve()
        if project_tmp not in roots:
            roots.append(project_tmp)
    return roots


def parse_size(value: str) -> int:
    """Parse human-readable size strings such as ``100M`` or ``1.5G``."""
    match = _SIZE_PATTERN.match(value.strip())
    if not match:
        raise ValueError(value)
    amount = float(match.group(1))
    unit = match.group(2).upper()
    if unit not in _SIZE_UNITS:
        raise ValueError(value)
    return int(amount * _SIZE_UNITS[unit])


def format_size(num_bytes: int) -> str:
    """Render a byte count in a compact human-readable form."""
    size = float(max(num_bytes, 0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)}{unit}"
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}PB"


def _entry_size(path: Path) -> int:
    if path.is_symlink() or not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            total += child.stat().st_size
    return total


def _validate_tmp_root(root: Path) -> None:
    resolved = root.resolve()
    if root.is_symlink():
        raise ValueError(f"Refusing to operate on symlink tmp root: {root}")
    if resolved in {Path("/"), Path.home()}:
        raise ValueError(f"Refusing to operate on unsafe tmp root: {resolved}")
    data_root = get_data_dir().resolve()
    project_tmp = (PROJECT_DIR / "tmp").resolve()
    if resolved != data_root / "tmp" and resolved != project_tmp:
        raise ValueError(f"Refusing to operate on unexpected tmp root: {resolved}")


def scan_tmp_dir(root: Path) -> TmpScanResult:
    """Scan a tmp root and return top-level entries sorted by size."""
    _validate_tmp_root(root)
    if not root.exists():
        return TmpScanResult(root=root, total_bytes=0, entry_count=0, entries=())

    entries: list[TmpEntry] = []
    total_bytes = 0
    for child in root.iterdir():
        if child.name.startswith("."):
            continue
        size_bytes = _entry_size(child)
        stat = child.stat()
        entries.append(
            TmpEntry(
                path=child,
                size_bytes=size_bytes,
                mtime=stat.st_mtime,
                is_dir=child.is_dir(),
            )
        )
        total_bytes += size_bytes

    entries.sort(key=lambda item: item.size_bytes, reverse=True)
    return TmpScanResult(
        root=root,
        total_bytes=total_bytes,
        entry_count=len(entries),
        entries=tuple(entries),
    )


def _is_candidate(
    entry: TmpEntry,
    *,
    now: float,
    older_than_days: int | None,
    min_size_bytes: int | None,
    clean_all: bool,
) -> bool:
    if clean_all:
        return True
    if min_size_bytes is not None and entry.size_bytes >= min_size_bytes:
        return True
    if older_than_days is None:
        return False
    age_seconds = now - entry.mtime
    return age_seconds >= older_than_days * 86400


def select_clean_candidates(
    root: Path,
    *,
    older_than_days: int | None = 7,
    min_size_bytes: int | None = None,
    clean_all: bool = False,
) -> list[TmpEntry]:
    """Select top-level tmp entries eligible for deletion."""
    scan = scan_tmp_dir(root)
    now = time.time()
    return [
        entry
        for entry in scan.entries
        if _is_candidate(
            entry,
            now=now,
            older_than_days=older_than_days,
            min_size_bytes=min_size_bytes,
            clean_all=clean_all,
        )
    ]


def _remove_entry(entry: TmpEntry) -> None:
    if entry.is_dir:
        shutil.rmtree(entry.path)
        return
    entry.path.unlink(missing_ok=True)


def clean_tmp_dir(
    root: Path,
    *,
    older_than_days: int | None = 7,
    min_size_bytes: int | None = None,
    clean_all: bool = False,
    dry_run: bool = False,
) -> TmpCleanResult:
    """Delete eligible entries under a tmp root."""
    _validate_tmp_root(root)
    result = TmpCleanResult(root=root)
    if not root.exists():
        return result

    candidates = select_clean_candidates(
        root,
        older_than_days=older_than_days,
        min_size_bytes=min_size_bytes,
        clean_all=clean_all,
    )
    for entry in candidates:
        if entry.path.name in _PRESERVED_SUBDIRS and entry.is_dir and not clean_all:
            nested = clean_tmp_dir(
                entry.path,
                older_than_days=older_than_days,
                min_size_bytes=min_size_bytes,
                clean_all=False,
                dry_run=dry_run,
            )
            result.removed_count += nested.removed_count
            result.removed_bytes += nested.removed_bytes
            result.skipped_count += nested.skipped_count
            result.errors.extend(nested.errors)
            continue

        if dry_run:
            result.removed_count += 1
            result.removed_bytes += entry.size_bytes
            continue

        try:
            _remove_entry(entry)
            result.removed_count += 1
            result.removed_bytes += entry.size_bytes
        except OSError as exc:
            logger.warning("Failed to remove tmp entry %s", entry.path, exc_info=True)
            result.errors.append(f"{entry.path}: {exc}")
            result.skipped_count += 1

    if not dry_run:
        for name in _PRESERVED_SUBDIRS:
            (root / name).mkdir(parents=True, exist_ok=True)

    return result
