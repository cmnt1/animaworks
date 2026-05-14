"""E2E coverage for memory backend stability policy CLI behavior."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run_cli(data_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["ANIMAWORKS_DATA_DIR"] = str(data_dir)
    env["PYTHONPATH"] = f"{ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}"
    return subprocess.run(
        [sys.executable, "-m", "cli", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def test_memory_status_reports_policy_and_per_anima_override(tmp_path: Path) -> None:
    data_dir = tmp_path / ".animaworks"
    sakura_dir = data_dir / "animas" / "sakura"
    sakura_dir.mkdir(parents=True)
    (sakura_dir / "status.json").write_text(
        json.dumps({"enabled": True, "memory_backend": "neo4j"}),
        encoding="utf-8",
    )

    result = _run_cli(data_dir, "memory", "status")

    assert result.returncode == 0, result.stderr
    assert "Memory Backend: legacy (stable/default)" in result.stdout
    assert "Policy: legacy is stable/default; neo4j is experimental opt-in." in result.stdout
    assert "sakura: neo4j (experimental/opt-in)" in result.stdout


def test_anima_set_memory_backend_legacy_updates_status(tmp_path: Path) -> None:
    data_dir = tmp_path / ".animaworks"
    sakura_dir = data_dir / "animas" / "sakura"
    sakura_dir.mkdir(parents=True)
    (sakura_dir / "status.json").write_text(
        json.dumps({"enabled": True, "memory_backend": "neo4j"}),
        encoding="utf-8",
    )

    result = _run_cli(data_dir, "anima", "set-memory-backend", "sakura", "legacy")

    assert result.returncode == 0, result.stderr
    assert "Memory backend set to 'legacy' for 'sakura'" in result.stdout
    assert "experimental/opt-in" not in result.stdout
    status = json.loads((sakura_dir / "status.json").read_text(encoding="utf-8"))
    assert status["memory_backend"] == "legacy"
