from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.supervisor.runner import AnimaRunner


def test_runner_exports_anima_dir_for_child_processes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ANIMAWORKS_ANIMA_DIR", raising=False)

    runner = AnimaRunner(
        anima_name="mei",
        socket_path=tmp_path / "mei.sock",
        animas_dir=tmp_path / "animas",
        shared_dir=tmp_path / "shared",
    )

    assert os.environ["ANIMAWORKS_ANIMA_DIR"] == str(runner._anima_dir)
