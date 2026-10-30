from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Antigravity CLI (``agy``) detection and authentication status helpers."""

import os
import shutil
from pathlib import Path


def agy_config_dir() -> Path:
    """Return the default Antigravity CLI configuration directory."""
    home = os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home())
    return Path(home) / ".gemini" / "antigravity-cli"


def find_agy_binary() -> str | None:
    """Return the path to the ``agy`` CLI executable, if available."""
    return shutil.which("agy")


def is_agy_cli_available() -> bool:
    """Return True when the ``agy`` CLI is available on PATH."""
    return find_agy_binary() is not None


def is_agy_authenticated() -> bool:
    """Return True when the Antigravity OAuth token file exists."""
    return (agy_config_dir() / "antigravity-oauth-token").is_file()
