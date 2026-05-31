#!/usr/bin/env python3
"""Bridge script: Claude Code CLI Native Hook -> rtk rewrite.

Translates between Claude Code's hook protocol and RTK's rewrite CLI.
Called by the CLI as a shell command (not via SDK control protocol).

stdin:  JSON with tool_input.command
stdout: JSON with hookSpecificOutput (rewritten command + permission)

Exit code protocol for ``rtk rewrite``:
  0 + stdout  -> Rewrite found, auto-allow
  1           -> No RTK equivalent, passthrough
  2           -> Deny rule matched, passthrough
  3 + stdout  -> Ask rule matched, rewrite but prompt user
"""

from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.
import json
import os
import re
import subprocess
import sys

_WIN_ABS_PATH_RE = re.compile(r"(?P<drive>[A-Za-z]):\\(?P<rest>[^\s\"'`|&;]*)")


def _resolve_rtk_bin() -> str:
    """Return the rtk binary path from argv[1], env, or PATH."""
    if len(sys.argv) > 1 and sys.argv[1]:
        return sys.argv[1]
    env_bin = os.environ.get("RTK_BIN")
    if env_bin:
        return env_bin
    return "rtk"


def _normalise_windows_paths_for_bash(command: str) -> str:
    """Convert Windows absolute paths to a bash-safe spelling."""

    def _replace(match: re.Match[str]) -> str:
        rest = match.group("rest").replace("\\", "/")
        return f"{match.group('drive')}:/{rest}"

    return _WIN_ABS_PATH_RE.sub(_replace, command)


def _emit_updated_command(input_data: dict, command: str, *, permission_decision: bool = False) -> None:
    updated_input = {**(input_data.get("tool_input") or {}), "command": command}
    hook_output: dict = {
        "hookEventName": "PreToolUse",
        "updatedInput": updated_input,
    }
    if permission_decision:
        hook_output["permissionDecision"] = "allow"
        hook_output["permissionDecisionReason"] = "RTK auto-rewrite"
    json.dump({"hookSpecificOutput": hook_output}, sys.stdout)


def main() -> None:
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        sys.exit(0)

    cmd = (input_data.get("tool_input") or {}).get("command", "")
    if not cmd:
        sys.exit(0)

    normalized_cmd = _normalise_windows_paths_for_bash(cmd)
    rtk_bin = _resolve_rtk_bin()
    try:
        result = subprocess.run(
            [rtk_bin, "rewrite", normalized_cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        if normalized_cmd != cmd:
            _emit_updated_command(input_data, normalized_cmd)
        sys.exit(0)

    rewritten = result.stdout.strip()
    exit_code = result.returncode

    # No rewrite, deny, or identical -> passthrough unless path normalization
    # is still needed to keep Windows paths intact under Bash.
    if exit_code in (1, 2) or not rewritten or rewritten == cmd:
        if normalized_cmd != cmd:
            _emit_updated_command(input_data, normalized_cmd)
        sys.exit(0)

    _emit_updated_command(input_data, rewritten, permission_decision=exit_code == 0)
    # exit_code == 3: rewrite but let Claude Code prompt user (no permissionDecision)


if __name__ == "__main__":
    main()
