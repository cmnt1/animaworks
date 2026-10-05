"""Codex app-server socket dir must be 0700 or every Codex thread fails."""

from __future__ import annotations

import os
import stat

import pytest

from core.execution.engines.codex import setup as codex_setup


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_resets_loose_mode_to_0700(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(codex_setup.tempfile, "gettempdir", lambda: str(tmp_path))
    daemon_dir = tmp_path / f"codex-daemon-{os.getuid()}"
    daemon_dir.mkdir(mode=0o755)
    daemon_dir.chmod(0o755)

    codex_setup._repair_codex_daemon_dir()

    assert stat.S_IMODE(daemon_dir.stat().st_mode) == 0o700


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")
def test_missing_dir_is_left_alone(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(codex_setup.tempfile, "gettempdir", lambda: str(tmp_path))

    codex_setup._repair_codex_daemon_dir()

    assert not (tmp_path / f"codex-daemon-{os.getuid()}").exists()
