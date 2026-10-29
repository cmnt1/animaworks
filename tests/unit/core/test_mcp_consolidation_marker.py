"""Stale consolidation marker must not hide communication tools (rin 2026-09-30)."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from core.mcp import server


@pytest.fixture
def anima_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "state").mkdir()
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(tmp_path))
    return tmp_path


def test_no_marker_is_not_consolidation(anima_dir: Path) -> None:
    assert server._is_consolidation_mode() is False


def test_fresh_marker_is_consolidation(anima_dir: Path) -> None:
    (anima_dir / "state" / ".consolidation_mode").write_text("1", encoding="utf-8")
    assert server._is_consolidation_mode() is True


def test_stale_marker_is_ignored(anima_dir: Path) -> None:
    marker = anima_dir / "state" / ".consolidation_mode"
    marker.write_text("1", encoding="utf-8")
    old = time.time() - server._CONSOLIDATION_MARKER_MAX_AGE_S - 60
    os.utime(marker, (old, old))
    assert server._is_consolidation_mode() is False
