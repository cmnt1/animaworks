"""Tests for core.tooling.standalone — build_standalone_tool_handler."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest

from core.tooling.standalone import build_standalone_tool_handler


@pytest.fixture
def anima_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a minimal anima runtime under an isolated data dir."""
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path / "data"))
    anima_dir = tmp_path / "data" / "animas" / "boss"
    anima_dir.mkdir(parents=True)
    (anima_dir / "status.json").write_text('{"enabled": true}', encoding="utf-8")
    (anima_dir / "identity.md").write_text("# Boss", encoding="utf-8")
    (anima_dir / "notes.md").write_text("standalone-note", encoding="utf-8")
    return anima_dir


def test_build_standalone_handler_reads_memory_file(
    anima_dir: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Passing an anima_dir yields a handler whose read_memory_file works."""
    handler = build_standalone_tool_handler(anima_dir, for_mcp=False)
    result = handler.handle("read_memory_file", {"path": "notes.md"})
    assert "standalone-note" in result


def test_build_standalone_handler_supports_supervisor_tools(
    anima_dir: Path,
) -> None:
    """The standalone handler can run an org_dashboard (empty org) call."""
    handler = build_standalone_tool_handler(anima_dir, for_mcp=False)
    result = handler.handle("org_dashboard", {})
    assert isinstance(result, str)
