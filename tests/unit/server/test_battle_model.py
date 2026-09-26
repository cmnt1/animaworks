"""Execute the battle's real JavaScript reducer, without a second implementation."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_battle_model_behaviors():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required for frontend model tests")
    result = subprocess.run(
        [
            node,
            "--experimental-default-type=module",
            "--test",
            "tests/unit/server/battle_model.test.mjs",
            "tests/unit/server/battle_combat.test.mjs",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
