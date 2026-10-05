"""Core command-policy decision for Codex's PreToolUse hook."""

from __future__ import annotations

from pathlib import Path

from core.tooling.policy.command_policy import (
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
