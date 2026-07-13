from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared canonical-path policy helpers for per-Anima file read denies."""

from collections.abc import Iterable
from pathlib import Path

_ANIMA_MEMORY_ROOTS = frozenset(
    {
        "activity_log",
        "archive",
        "episodes",
        "facts",
        "knowledge",
        "procedures",
        "skills",
        "state",
    }
)


def resolve_denied_roots(roots: Iterable[str | Path]) -> tuple[Path, ...]:
    """Canonicalize configured deny roots once for repeated comparisons."""
    return tuple(Path(root).resolve() for root in roots)


def load_denied_roots(anima_dir: Path) -> tuple[Path, ...]:
    """Load and canonicalize an Anima's configured file deny roots."""
    from core.config.models import load_permissions

    return resolve_denied_roots(load_permissions(anima_dir).file_roots_denied)


def find_denied_root(path: str | Path, denied_roots: tuple[Path, ...]) -> Path | None:
    """Return the canonical deny root containing *path*, following symlinks."""
    resolved = Path(path).resolve()
    return next((root for root in denied_roots if resolved.is_relative_to(root)), None)


def resolve_memory_source_path(anima_dir: Path, source: str) -> Path | None:
    """Resolve a trusted memory ``source_file``/derived doc path to a real path.

    Relative values must start with a known memory namespace.  Opaque vector
    IDs are deliberately not guessed: when deny is active their callers can
    fail closed instead of accidentally releasing cached content.
    """
    source = str(source or "").strip().split("#", 1)[0]
    if not source or source == "unknown":
        return None
    path = Path(source)
    if path.is_absolute():
        return path.resolve()
    if not path.parts or ".." in path.parts:
        return None

    from core.paths import get_common_knowledge_dir, get_common_skills_dir, get_data_dir, get_reference_dir

    shared_roots = {
        "common_knowledge": get_common_knowledge_dir(),
        "common_skills": get_common_skills_dir(),
        "reference": get_reference_dir(),
    }
    namespace = path.parts[0]
    shared_root = shared_roots.get(namespace)
    if shared_root is not None:
        return shared_root.joinpath(*path.parts[1:]).resolve()
    if namespace == "shared":
        return (get_data_dir() / path).resolve()
    if namespace in _ANIMA_MEMORY_ROOTS:
        return (anima_dir / path).resolve()
    return None


def memory_source_is_allowed(
    anima_dir: Path,
    source: str,
    denied_roots: tuple[Path, ...],
) -> bool:
    """Check a cached memory source, failing closed on ambiguity when deny is active."""
    if not denied_roots:
        return True
    source_path = resolve_memory_source_path(anima_dir, source)
    if source_path is None:
        return False
    return find_denied_root(source_path, denied_roots) is None
