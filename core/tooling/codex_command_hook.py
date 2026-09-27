"""Codex ``PreToolUse`` hook: deny shell commands by the shared command policy.

Codex's native shell tool runs inside ``codex-linux-sandbox`` and never passes
through ``execute_command`` permission checks, so ``permissions.global.json``
and per-anima ``commands.deny`` were unenforced for codex animas.
``codex_sdk`` writes ``$CODEX_HOME/hooks.json`` pointing here; Codex feeds the
tool call on stdin and honours ``permissionDecision: deny``.

All policy layers (injection, global deny, recursive-search guard, per-anima
deny, allowlist, traversal, other-anima write) are applied by the shared
``core.tooling.command_policy`` module — the same function the ToolHandler
and Mode S use.  On any error the hook denies (fail-closed) rather than
freezing the fleet with an un-translated Bash call.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from core.i18n import t
from core.tooling.command_policy import (
    check_recursive_search,  # noqa: F401  (re-exported for imports)
    evaluate_command,
    load_command_policy_context,
    record_injection_hit,
)


def decide(command: str, *, cwd: Path, anima_dir: Path, global_permissions: Path | None) -> str | None:
    """Return a denial reason, or None to allow (thin wrapper over evaluate)."""
    try:
        ctx = load_command_policy_context(
            anima_dir,
            cwd=cwd,
            global_permissions_path=global_permissions,
        )
    except Exception:
        # fail-closed: a broken loader denies rather than letting the command through.
        return "Command policy check failed: command could not be evaluated"
    decision = evaluate_command(command, ctx)
    if decision.injection_hit:
        record_injection_hit(command, ctx, pattern_name=decision.injection_hit, trigger="codex")
    if decision.allowed:
        return None
    return decision.reason


def main(argv: list[str] | None = None) -> int:
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
