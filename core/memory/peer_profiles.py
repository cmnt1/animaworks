from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Safe path helpers for per-Anima peer profiles."""

from pathlib import Path

from core.memory.facts.entity_index import normalize_entity_key


def normalize_peer_name(name: str) -> str:
    """Map a person/Anima name to a stable, filesystem-safe profile stem."""
    raw = str(name or "").strip()
    if not raw or "/" in raw or "\\" in raw or ".." in raw:
        return ""
    normalized = normalize_entity_key(raw).replace(" ", "_")
    if not normalized or normalized in {".", ".."}:
        return ""
    return normalized


def peer_profile_path(anima_dir: Path, name: str) -> Path | None:
    """Return a peer profile path constrained to ``anima_dir/peers``."""
    stem = normalize_peer_name(name)
    if not stem:
        return None
    anima_root = Path(anima_dir).resolve()
    peers_dir = (anima_root / "peers").resolve()
    if not peers_dir.is_relative_to(anima_root):
        return None
    profile_path = (peers_dir / f"{stem}.md").resolve()
    if not profile_path.is_relative_to(peers_dir):
        return None
    return profile_path
