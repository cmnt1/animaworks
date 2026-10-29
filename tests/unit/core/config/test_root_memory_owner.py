"""The process model is fixed to phase3 and root memory ownership."""

from __future__ import annotations

import json
from pathlib import Path

from core.config.resolver import is_root_memory_owner as _is_root_memory_owner


def test_root_memory_owner_is_true_without_status_json(tmp_path: Path) -> None:
    assert _is_root_memory_owner(tmp_path / "anima") is True


def test_root_memory_owner_is_true_for_legacy_status(tmp_path: Path) -> None:
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()
    (anima_dir / "status.json").write_text(json.dumps({"process_model": "legacy"}), encoding="utf-8")

    assert _is_root_memory_owner(anima_dir) is True


def test_root_memory_owner_is_true_for_corrupt_status(tmp_path: Path) -> None:
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()
    (anima_dir / "status.json").write_text("{broken", encoding="utf-8")

    assert _is_root_memory_owner(anima_dir) is True
