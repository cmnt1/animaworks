# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI adapter for Codex's ``PreToolUse`` command-policy hook."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.i18n import t
from core.tooling.codex_command_hook import decide


def main(argv: list[str] | None = None) -> int:
    """Read Codex's hook request on stdin and emit a deny response if needed."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--anima-dir", required=True, type=Path)
    parser.add_argument("--global-permissions", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
        command = str((payload.get("tool_input") or {}).get("command") or "")
        if not command:
            return 0
        cwd = Path(str(payload.get("cwd") or args.anima_dir))
        reason = decide(command, cwd=cwd, anima_dir=args.anima_dir, global_permissions=args.global_permissions)
        if reason is None:
            return 0
    except Exception as exc:  # fail-closed: a broken hook must not let commands through
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": t("tooling.command_policy_check_failed", error=type(exc).__name__),
                    }
                }
            )
        )
        return 0
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
