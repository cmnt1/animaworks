from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Process-safe storage for per-Anima shared-index metadata."""

import json
import logging
import os
import tempfile
import time
from pathlib import Path

from core.platform.locks import file_lock

logger = logging.getLogger("animaworks.memory")

SHARED_INDEX_META_FILE = "shared_index_meta.json"
SHARED_INDEX_META_LOCK_FILE = f"{SHARED_INDEX_META_FILE}.lock"
SHARED_INDEX_META_KEYS = frozenset(
    {
        "shared_company_name",
        "shared_common_knowledge_hash",
        "shared_common_skills_hash",
        "shared_company_knowledge_hash",
        "shared_company_skills_hash",
    }
)


class SharedIndexMetaError(RuntimeError):
    """Raised when shared-index metadata exists but cannot be read safely."""


def shared_index_meta_path(anima_dir: Path) -> Path:
    return Path(anima_dir) / SHARED_INDEX_META_FILE


def _load_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SharedIndexMetaError(f"failed to read shared index metadata from {path}") from exc
    if not isinstance(value, dict):
        raise SharedIndexMetaError(f"shared index metadata must be a JSON object: {path}")
    return value


def _shared_values(value: dict[str, object], path: Path) -> dict[str, str]:
    meta: dict[str, str] = {}
    for key in SHARED_INDEX_META_KEYS:
        item = value.get(key)
        if item is None:
            continue
        if not isinstance(item, str):
            raise SharedIndexMetaError(f"shared index metadata value must be a string: {path} ({key})")
        meta[key] = item
    return meta


def _atomic_write(path: Path, meta: dict[str, str]) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            json.dump(meta, temp_file, indent=2, ensure_ascii=False)
            temp_file.write("\n")
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def _load_or_migrate_locked(anima_dir: Path) -> dict[str, str]:
    path = shared_index_meta_path(anima_dir)
    if path.exists():
        return _shared_values(_load_json(path), path)

    legacy_path = anima_dir / "index_meta.json"
    if not legacy_path.exists():
        return {}
    for attempt in range(3):
        try:
            legacy = _shared_values(_load_json(legacy_path), legacy_path)
            break
        except SharedIndexMetaError:
            if attempt == 2:
                raise
            time.sleep(0.001)
    if legacy:
        _atomic_write(path, legacy)
    return legacy


def read_shared_meta(anima_dir: Path) -> dict[str, str]:
    """Read shared metadata, migrating legacy keys on first access.

    Reads take the same sidecar flock as writes because a missing new file may
    require a one-time atomic copy from ``index_meta.json``.
    """
    anima_dir = Path(anima_dir)
    lock_path = anima_dir / SHARED_INDEX_META_LOCK_FILE
    with lock_path.open("a+", encoding="utf-8") as lock_file, file_lock(lock_file, exclusive=True):
        return _load_or_migrate_locked(anima_dir)


def read_shared_hash(anima_dir: Path, key: str) -> str | None:
    if key not in SHARED_INDEX_META_KEYS:
        raise ValueError(f"unsupported shared index metadata key: {key}")
    return read_shared_meta(anima_dir).get(key)


def write_shared_hashes(anima_dir: Path, updates: dict[str, str]) -> None:
    """Atomically merge shared metadata updates under a process-wide flock."""
    invalid = updates.keys() - SHARED_INDEX_META_KEYS
    if invalid:
        raise ValueError(f"unsupported shared index metadata keys: {sorted(invalid)}")
    if any(not isinstance(value, str) for value in updates.values()):
        raise TypeError("shared index metadata values must be strings")

    anima_dir = Path(anima_dir)
    lock_path = anima_dir / SHARED_INDEX_META_LOCK_FILE
    with lock_path.open("a+", encoding="utf-8") as lock_file, file_lock(lock_file, exclusive=True):
        meta = _load_or_migrate_locked(anima_dir)
        meta.update(updates)
        _atomic_write(shared_index_meta_path(anima_dir), meta)


def write_shared_hash(anima_dir: Path, key: str, value: str) -> None:
    write_shared_hashes(anima_dir, {key: value})


def reset_shared_for_company_change(anima_dir: Path, vector_store, current_company: str) -> bool:
    """Reset shared collections and metadata as one successful-delete commit."""
    stored_company = read_shared_hash(anima_dir, "shared_company_name")
    if stored_company == current_company or (stored_company is None and not current_company):
        return True

    deleted = True
    for collection in ("shared_common_knowledge", "shared_common_skills"):
        try:
            if vector_store.delete_collection(collection) is not True:
                deleted = False
                logger.warning("Failed to reset %s after company assignment change", collection)
        except Exception:
            deleted = False
            logger.warning("Failed to reset %s after company assignment change", collection, exc_info=True)
    if not deleted:
        return False

    write_shared_hashes(
        anima_dir,
        {
            "shared_company_name": current_company,
            "shared_common_knowledge_hash": "",
            "shared_common_skills_hash": "",
            "shared_company_knowledge_hash": "",
            "shared_company_skills_hash": "",
        },
    )
    from core.memory.rag.shared_check_registry import invalidate_shared_checks

    invalidate_shared_checks(anima_dir.name)
    return True


def clear_shared_meta(anima_dir: Path) -> None:
    """Clear existing shared metadata after an Anima rename."""
    anima_dir = Path(anima_dir)
    path = shared_index_meta_path(anima_dir)
    lock_path = anima_dir / SHARED_INDEX_META_LOCK_FILE
    with lock_path.open("a+", encoding="utf-8") as lock_file, file_lock(lock_file, exclusive=True):
        if path.exists():
            _atomic_write(path, {})
