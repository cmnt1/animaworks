#!/usr/bin/env python3
"""Bridge script: Claude Code CLI Native Hook → rtk rewrite.

Translates between Claude Code's hook protocol and RTK's rewrite CLI.
Called by the CLI as a shell command (not via SDK control protocol).

stdin:  JSON with tool_input.command
stdout: JSON with hookSpecificOutput (rewritten command + permission)

Exit code protocol for ``rtk rewrite``:
  0 + stdout  → Rewrite found, auto-allow
  1           → No RTK equivalent, passthrough
  2           → Deny rule matched, passthrough
  3 + stdout  → Ask rule matched, rewrite but prompt user
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
import subprocess
import sys


def _resolve_rtk_bin() -> str:
    """Return the rtk binary path from argv[1], env, or PATH."""
    # 1. CLI argument (passed by _sdk_options.py)
    if len(sys.argv) > 1 and sys.argv[1]:
        return sys.argv[1]
    # 2. Environment variable
    env_bin = os.environ.get("RTK_BIN")
    if env_bin:
        return env_bin
    # 3. Fall back to bare name (requires PATH)
    return "rtk"


def main() -> None:
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        sys.exit(0)

    cmd = (input_data.get("tool_input") or {}).get("command", "")
    if not cmd:
        sys.exit(0)

    rtk_bin = _resolve_rtk_bin()
    try:
        result = subprocess.run(
            [rtk_bin, "rewrite", cmd],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        sys.exit(0)

    rewritten = result.stdout.strip()
    exit_code = result.returncode

    # No rewrite, deny, or identical → passthrough
    if exit_code in (1, 2) or not rewritten or rewritten == cmd:
        sys.exit(0)

    updated_input = {**(input_data.get("tool_input") or {}), "command": rewritten}
    hook_output: dict = {
        "hookEventName": "PreToolUse",
        "updatedInput": updated_input,
    }

    if exit_code == 0:
        hook_output["permissionDecision"] = "allow"
        hook_output["permissionDecisionReason"] = "RTK auto-rewrite"
    # exit_code == 3: rewrite but let Claude Code prompt user (no permissionDecision)

    json.dump({"hookSpecificOutput": hook_output}, sys.stdout)


if __name__ == "__main__":
    main()
