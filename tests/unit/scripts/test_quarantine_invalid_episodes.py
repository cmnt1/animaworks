from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_script() -> ModuleType:
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "quarantine_invalid_episodes.py"
    spec = importlib.util.spec_from_file_location("quarantine_invalid_episodes", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_episode(data_dir: Path, anima: str, filename: str) -> Path:
    path = data_dir / "animas" / anima / "episodes" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Episode\n\ncontent", encoding="utf-8")
    return path


def test_dry_run_detects_pre_launch_kotoha_episodes(tmp_path: Path, capsys) -> None:
    script = _load_script()
    for filename in (
        "2025-01-16.md",
        "2025-01-16_first_day.md.bak",
        "2025-01-16_heartbeat_api_keys.md.bak",
        "2025-01-16_heartbeat_check.md.bak",
        "2025-01-16_heartbeat_followup.md.bak",
        "2025-01-17.md",
        "2025-01-17_heartbeat_notification_update.md.bak",
    ):
        _write_episode(tmp_path, "kotoha", filename)
    valid = _write_episode(tmp_path, "kotoha", "2026-02-01.md")

    exit_code = script.main(["--data-dir", str(tmp_path), "--anima", "kotoha"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert output.count("DRY-RUN kotoha:") == 7
    assert "candidates=7 moved=0 dry_run=True" in output
    assert "2025-01-16.md" in output
    assert valid.exists()
    assert not (tmp_path / "animas" / "kotoha" / "archive" / "invalid-dates").exists()


def test_execute_moves_invalid_episode(tmp_path: Path, capsys) -> None:
    script = _load_script()
    invalid = _write_episode(tmp_path, "kotoha", "2025-01-16.md")

    exit_code = script.main(["--data-dir", str(tmp_path), "--anima", "kotoha", "--execute"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "MOVE kotoha:" in output
    assert "candidates=1 moved=1 dry_run=False" in output
    assert not invalid.exists()
    assert (tmp_path / "animas" / "kotoha" / "archive" / "invalid-dates" / "2025-01-16.md").exists()
