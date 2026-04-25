from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Cross-platform helpers for Claude Code CLI discovery."""

import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _iter_claude_candidates(*, include_bundled: bool = True) -> list[str]:
    """Return plausible Claude Code CLI locations.

    Order of preference:
    1. npm global bin (most reliable on Windows – wrapper script)
    2. shutil.which fallback
    3. SDK bundled binary (can intermittently fail to launch)
    """
    seen: set[str] = set()
    candidates: list[str] = []

    def _add(p: str) -> None:
        if p and p not in seen:
            seen.add(p)
            candidates.append(p)

    # Explicit override for pinned/known-good Claude Code builds.
    for env_name in ("ANIMAWORKS_CLAUDE_CODE_PATH", "CLAUDE_CODE_PATH"):
        override = os.environ.get(env_name)
        if override and Path(override).is_file():
            _add(str(Path(override)))

    # npm global bin (Windows: %APPDATA%/npm, Unix: varies)
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            npm_bin = Path(appdata) / "npm"
            for name in ("claude.cmd", "claude.exe", "claude"):
                candidate = npm_bin / name
                if candidate.is_file():
                    _add(str(candidate))
    else:
        # Common Unix npm global locations
        home = Path.home()
        for d in (
            home / ".npm-global" / "bin",
            Path("/usr/local/bin"),
            home / ".local" / "bin",
        ):
            candidate = d / "claude"
            if candidate.is_file():
                _add(str(candidate))

    # shutil.which as fallback
    direct = shutil.which("claude")
    if direct:
        _add(direct)

    # SDK bundled binary (lowest priority – can intermittently fail to launch)
    if include_bundled:
        bundled = _find_sdk_bundled_cli()
        if bundled:
            _add(bundled)

    return candidates


def _find_sdk_bundled_cli() -> str | None:
    """Return the SDK-bundled Claude Code binary if it exists."""
    try:
        import claude_agent_sdk  # noqa: F811

        cli_name = "claude.exe" if platform.system() == "Windows" else "claude"
        bundled_path = Path(claude_agent_sdk.__file__).parent / "_bundled" / cli_name
        if bundled_path.is_file() and bundled_path.stat().st_size > 0:
            return str(bundled_path)
    except Exception:
        logger.debug("claude_code check failed", exc_info=True)
    return None


def _is_usable_claude_executable(candidate: str) -> bool:
    """Return True if the candidate responds to --version."""
    try:
        result = subprocess.run(
            [candidate, "--version"],
            capture_output=True,
            text=True,
            timeout=10.0,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def get_claude_executable(*, include_bundled: bool = True) -> str | None:
    """Return the best available Claude Code CLI executable path."""
    for candidate in _iter_claude_candidates(include_bundled=include_bundled):
        if _is_usable_claude_executable(candidate):
            return candidate
    return None


def is_claude_code_available() -> bool:
    """Return True when a Claude Code CLI executable is available."""
    return get_claude_executable() is not None


def _find_git_bash() -> str | None:
    """Return the Windows-native path to Git Bash's bash.exe, or None.

    Claude Code on Windows requires ``CLAUDE_CODE_GIT_BASH_PATH`` to be
    set when Git Bash is not at the default ``C:\\Program Files\\Git`` location.
    """
    if sys.platform != "win32":
        return None

    # Honour existing env var
    existing = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH")
    if existing and Path(existing).is_file():
        return existing

    # Common installation paths (Windows-native)
    candidates: list[Path] = []
    for drive in ("C:", "D:", "E:"):
        for sub in (
            f"{drive}\\Program Files\\Git\\usr\\bin\\bash.exe",
            f"{drive}\\Program Files (x86)\\Git\\usr\\bin\\bash.exe",
        ):
            candidates.append(Path(sub))

    # Scoop / user-local
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        candidates.append(Path(user_profile) / "scoop" / "apps" / "git" / "current" / "usr" / "bin" / "bash.exe")

    # Derive from `git.exe` on PATH
    git_exe = shutil.which("git")
    if git_exe:
        git_dir = Path(git_exe).resolve().parent.parent  # .../Git/cmd -> .../Git
        candidates.append(git_dir / "usr" / "bin" / "bash.exe")

    for p in candidates:
        if p.is_file():
            return str(p)

    return None


__all__ = [
    "get_claude_executable",
    "is_claude_code_available",
    "_find_sdk_bundled_cli",
    "_find_git_bash",
]
