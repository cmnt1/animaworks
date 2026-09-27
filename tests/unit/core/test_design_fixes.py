# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Design fixes — layer violation removal and local LLM preset guard.

Tests:
1. core/anima/heartbeat.py has no server.* imports
2. apply_local_llm_presets_to_animas is guarded by auto_apply_presets
"""

import ast
import json
from pathlib import Path
from unittest.mock import MagicMock

from core.config.schemas import LocalLLMConfig

# ── Phase 1: Layer violation check ──────────────────────────────


class TestNoServerImportInHeartbeat:
    """core/anima/heartbeat.py must not import from server.*."""

    def test_no_server_import(self):
        src_path = Path(__file__).resolve().parents[3] / "core" / "anima" / "heartbeat.py"
        source = src_path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        violations = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("server"):
                violations.append(f"line {node.lineno}: from {node.module} import ...")

        assert violations == [], "server.* imports found in _anima_heartbeat.py:\n" + "\n".join(violations)


# ── Phase 3: Ollama preset guard ────────────────────────────────


class TestAutoApplyPresetsGuard:
    """apply_local_llm_presets_to_animas respects auto_apply_presets."""

    def test_default_false(self):
        cfg = LocalLLMConfig()
        assert cfg.auto_apply_presets is False

    def test_skips_when_disabled(self, tmp_path):
        from core.config.local_llm import apply_local_llm_presets_to_animas

        animas_dir = tmp_path / "animas"
        animas_dir.mkdir()
        (animas_dir / "test-anima").mkdir()
        (animas_dir / "test-anima" / "status.json").write_text(
            json.dumps({"role": "engineer", "model": "old-model", "credential": "ollama"}),
            encoding="utf-8",
        )

        config = MagicMock()
        config.local_llm = LocalLLMConfig(auto_apply_presets=False)

        result = apply_local_llm_presets_to_animas(animas_dir, config)
        assert result == []

        status = json.loads((animas_dir / "test-anima" / "status.json").read_text())
        assert status["model"] == "old-model"

    def test_applies_when_enabled(self, tmp_path):
        from core.config.local_llm import apply_local_llm_presets_to_animas

        animas_dir = tmp_path / "animas"
        animas_dir.mkdir()
        (animas_dir / "test-anima").mkdir()
        (animas_dir / "test-anima" / "status.json").write_text(
            json.dumps({"role": "engineer", "credential": "ollama"}),
            encoding="utf-8",
        )

        config = MagicMock()
        config.local_llm = LocalLLMConfig(auto_apply_presets=True)
        config.anima_defaults.credential = "ollama"

        result = apply_local_llm_presets_to_animas(animas_dir, config)
        assert len(result) >= 1

        status = json.loads((animas_dir / "test-anima" / "status.json").read_text())
        assert status["credential"] == "ollama"
