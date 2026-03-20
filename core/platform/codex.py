from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Cross-platform helpers for Codex CLI discovery and login state."""

import json
import os
import shutil
from pathlib import Path


def default_home_dir() -> str:
    """Return the most reliable home directory across platforms."""
    return os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home())


def codex_auth_path() -> Path:
    """Return the default Codex auth.json path."""
    return Path(default_home_dir()) / ".codex" / "auth.json"


def is_codex_cli_available() -> bool:
    """Return True when the ``codex`` CLI is available on PATH."""
    return shutil.which("codex") is not None


def is_codex_login_available() -> bool:
    """Return True when a readable Codex auth.json exists."""
    auth_path = codex_auth_path()
    if not auth_path.is_file():
        return False
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(data)
