# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

"""Design fixes — layer violation removal."""

import ast
from pathlib import Path

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
