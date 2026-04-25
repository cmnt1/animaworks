from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Cross-platform helpers for Codex CLI discovery and login state."""

import json
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
_DEVICE_URL_RE = re.compile(r"https://auth\.openai\.com/codex/device", re.IGNORECASE)
_DEVICE_CODE_RE = re.compile(r"\b([A-Z0-9]{4}-[A-Z0-9]{5})\b")


def default_home_dir() -> str:
    """Return the most reliable home directory across platforms."""
    return os.environ.get("HOME") or os.environ.get("USERPROFILE") or str(Path.home())


def codex_auth_path() -> Path:
    """Return the default Codex auth.json path."""
    return Path(default_home_dir()) / ".codex" / "auth.json"


def _iter_embedded_codex_candidates() -> list[Path]:
    """Return plausible embedded Codex CLI locations."""
    candidates: list[Path] = []
    user_home = Path(default_home_dir())

    # Prefer the OpenAI Codex app cache over editor/agent extension bundles.
    # The WindowsApps alias itself is often not directly executable from
    # subprocesses, while this LocalCache binary is.
    packages = user_home / "AppData" / "Local" / "Packages"
    if packages.is_dir():
        candidates.extend(
            sorted(
                packages.glob("OpenAI.Codex_*/LocalCache/**/codex.exe"),
                reverse=True,
            )
        )

    # Legacy fallback: older desktop integrations bundled Codex under
    # Antigravity.  Keep it available, but do not prefer it for new setups.
    antigravity = user_home / ".antigravity" / "extensions"
    if antigravity.is_dir():
        candidates.extend(
            sorted(
                antigravity.glob("openai.chatgpt-*/bin/windows-x86_64/codex.exe"),
                reverse=True,
            )
        )

    return [path for path in candidates if path.is_file()]


def _iter_codex_candidates() -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []

    explicit = os.environ.get("ANIMAWORKS_CODEX_PATH") or os.environ.get("CODEX_PATH")
    if explicit:
        value = str(Path(explicit).expanduser())
        if value not in seen:
            seen.add(value)
            candidates.append(value)

    direct = shutil.which("codex")
    if direct and direct not in seen:
        seen.add(direct)
        candidates.append(direct)

    for path in _iter_embedded_codex_candidates():
        value = str(path)
        if value not in seen:
            seen.add(value)
            candidates.append(value)

    return candidates


def _is_usable_codex_executable(candidate: str) -> bool:
    try:
        result = subprocess.run(
            [candidate, "--help"],
            capture_output=True,
            text=True,
            timeout=5.0,
            env=_status_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


@lru_cache(maxsize=1)
def get_codex_executable() -> str | None:
    """Return the best available Codex executable path."""
    for candidate in _iter_codex_candidates():
        if _is_usable_codex_executable(candidate):
            return candidate
    return None


def _status_env() -> dict[str, str]:
    """Build a conservative environment for Codex status checks."""
    env = os.environ.copy()
    home_dir = default_home_dir()
    env.setdefault("HOME", home_dir)
    return env


def _run_codex_command(args: list[str], timeout: float = 10.0) -> subprocess.CompletedProcess[str] | None:
    executable = get_codex_executable()
    if not executable:
        return None
    try:
        return subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_status_env(),
        )
    except (OSError, subprocess.SubprocessError):
        return None


def is_codex_cli_available() -> bool:
    """Return True when a Codex CLI executable is available."""
    return get_codex_executable() is not None


def _auth_file_looks_valid() -> bool:
    auth_path = codex_auth_path()
    if not auth_path.is_file():
        return False
    try:
        data = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return bool(data)


def is_codex_login_available() -> bool:
    """Return True when Codex login is available via auth.json or CLI status."""
    if _auth_file_looks_valid():
        return True

    result = _run_codex_command(["login", "status"])
    if result is None:
        return False
    combined = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0 and "Logged in" in combined


def _launch_codex_login_terminal(executable: str) -> bool:
    """Open a new CMD window running ``codex login``."""
    try:
        creationflags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        subprocess.Popen(
            ["cmd.exe", "/k", f"{executable} login"],
            creationflags=creationflags,
            cwd=str(Path(default_home_dir())),
            env=_status_env(),
        )
        return True
    except Exception:
        return False


def get_codex_device_login(*, force: bool = False) -> dict[str, str | bool]:
    """Open a new CMD window running ``codex login`` so the user can
    complete the interactive device-auth flow.

    When *force* is True the "already logged in" short-circuit is skipped.
    """
    executable = get_codex_executable()
    if not executable:
        return {"ok": False, "message": "Codex CLI is not installed"}

    if not force:
        status = _run_codex_command(["login", "status"])
        if status is not None:
            combined = (status.stdout or "") + (status.stderr or "")
            if status.returncode == 0 and "Logged in" in combined:
                return {"ok": True, "already_logged_in": True, "message": combined.strip() or "Logged in"}

    launched = _launch_codex_login_terminal(executable)
    if launched:
        return {
            "ok": True,
            "already_logged_in": False,
            "message": "Codex ログインウィンドウを開きました。ウィンドウ内の指示に従ってください。",
            "terminal_launched": True,
            "manual_command": "codex login",
        }
    return {
        "ok": False,
        "already_logged_in": False,
        "message": "ログインウィンドウを開けませんでした。ターミナルで 'codex login' を実行してください。",
        "manual_command": "codex login",
    }


__all__ = [
    "codex_auth_path",
    "default_home_dir",
    "get_codex_device_login",
    "get_codex_executable",
    "is_codex_cli_available",
    "is_codex_login_available",
]
