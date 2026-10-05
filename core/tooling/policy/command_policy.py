from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Pure shell-command permission policy shared by all three execution paths.

Anima's shell command decision used to live in three places (ToolHandler,
Mode S ``_check_a1_bash_command`` and the Codex ``PreToolUse`` hook) with
inconsistent layers and fail behaviours.  ``evaluate_command`` is the single
pure decision function: it applies every layer in the same fixed order and
returns a ``CommandDecision``.  Loading, logging and audit recording live in
the callers, so this module stays a leaf (no config loading at import time).

Layers (applied in this order):
    1. superuser                -> allow
    2. empty                    -> ``empty``
    3. injection                -> record, deny when mode == enforce
    4. global deny              -> ``global_deny``
    5. recursive-search guard   -> ``recursive_search``
    6. per-anima deny           -> ``anima_deny``
    7. allowlist                -> ``allowlist`` (syntax error -> ``syntax``)
    8. path traversal           -> ``traversal``
    9. other-anima write        -> ``other_anima_write``
"""

import json as _json
import logging
import os
import re
import shlex
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

logger = logging.getLogger("animaworks.tooling.command_policy")

# Codex ``PreToolUse`` hook used the broadest segment split (``;``, newlines,
# ``$(``, backticks, ``<(` and ``)`` all separate commands).  We keep that
# everywhere so per-anima deny / allowlist bind inside compound commands.
_SEGMENT_SPLIT = re.compile(r"\|(?!\|)|&&|\|\||;|\n|\$\(|`|<\(|\)")

# ── Recursive-search guard constants (2026-09-01 IO storm mitigation) ──────

_GREP_FAMILY = {"grep", "egrep", "fgrep"}
_ALWAYS_RECURSIVE = {"rg", "ag", "ack", "find", "fd", "fdfind", "du"}
_GREP_RECURSIVE_FLAGS = {"--recursive", "--dereference-recursive"}
# Directories that are always too big to sweep, wherever they sit.
_HEAVY_DIR_NAMES = {"activity_log", "logs", ".codex_home", "task_results"}

# Commands that can write into another anima's directory.
_WRITE_COMMANDS = frozenset(
    {
        "cp",
        "mv",
        "tee",
        "dd",
        "install",
        "rsync",
    }
)


# ── Data types ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CommandPolicyContext:
    """Everything ``evaluate_command`` needs; assembled by ``load_command_policy_context``."""

    anima_dir: Path  # resolve 済み
    data_dir: Path  # anima_dir.parent.parent
    cwd: Path  # base for recursive-search relative paths
    permissions: object  # PermissionsConfig — commands.deny / commands.allow / commands.allow_all
    injection_re: re.Pattern[str] | None
    injection_mode: Literal["off", "log", "enforce"]
    blocked_patterns: tuple[tuple[re.Pattern[str], str], ...]
    injection_pattern_names: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    superuser: bool = False


@dataclass(frozen=True)
class CommandDecision:
    """Result of evaluating one command against the policy."""

    allowed: bool
    layer: str  # "ok" | "empty" | "injection" | "global_deny" | "recursive_search" | ...
    reason: str  # message returned to the Anima
    injection_hit: str | None = None  # matched pattern name (recorded by the caller)


# ── Segment splitting ──────────────────────────────────────────────────────


def _shell_argv(command: str) -> list[str]:
    lexer = shlex.shlex(command, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    if os.name == "nt":
        lexer.escape = ""
    return list(lexer)


def split_segments(command: str) -> list[tuple[list[str] | None, str]]:
    """Split *command* into ``(argv, raw)`` segments (argv None = shlex failure).

    Leading ``VAR=val`` env assignments are skipped from each argv.  ``raw``
    is the unparsed segment text (used by per-anima deny matching).
    shlex-failure segments are *not* treated as commands — callers skip
    them for deny/traversal and reject with ``syntax`` for allowlist.
    """
    segments: list[tuple[list[str] | None, str]] = []
    for seg in (s.strip() for s in _SEGMENT_SPLIT.split(command) if s.strip()):
        argv: list[str] | None
        try:
            argv = _shell_argv(seg)
        except ValueError:
            argv = None
        if argv is not None:
            while argv and "=" in argv[0] and not argv[0].startswith("-"):
                argv = argv[1:]
        segments.append((argv, seg))
    return segments


# ── Recursive-search guard (moved from codex_command_hook) ─────────────────


def _is_broad_data_root(path: Path, data_dir: Path) -> bool:
    """True when *path* is the data dir or one of its wide top-level trees."""
    try:
        rel = path.resolve().relative_to(data_dir.resolve())
    except (ValueError, OSError):
        return False
    parts = rel.parts
    # A heavy dir itself (or any dir beneath one) is too big; a single file inside is fine.
    if parts and (parts[-1] in _HEAVY_DIR_NAMES or (any(p in _HEAVY_DIR_NAMES for p in parts) and path.is_dir())):
        return True
    if len(parts) == 0:
        return True
    head = parts[0]
    if head in {"animas", "companies", "shared"} and len(parts) <= 2:
        return True
    if head == "companies" and len(parts) == 3 and parts[2] == "shared":
        return True
    return head == "animas" and len(parts) == 3 and parts[2] == "state"


def _search_targets(argv: list[str]) -> list[str] | None:
    """Return the path operands of a recursive search command, or None if not one."""
    base = Path(argv[0]).name
    operands = [a for a in argv[1:] if not a.startswith("-")]
    if base in _GREP_FAMILY:
        flags = [a for a in argv[1:] if a.startswith("-")]
        recursive = any(
            f in _GREP_RECURSIVE_FLAGS or (not f.startswith("--") and ("r" in f or "R" in f)) for f in flags
        )
        if not recursive:
            return None
        if "-e" in flags or "-f" in flags or "--regexp" in flags:
            paths = operands
        else:
            paths = operands[1:]  # first operand is the pattern
        return paths or ["."]
    if base in {"rg", "ag", "ack"}:
        paths = operands if "-e" in argv or "--regexp" in argv or "--files" in argv else operands[1:]
        return paths or ["."]
    if base in {"find", "fd", "fdfind", "du"}:
        if base == "find":
            paths: list[str] = []
            for a in argv[1:]:
                if a.startswith("-") or a in {"(", "!", ")"}:
                    break
                paths.append(a)
            return paths or ["."]
        return operands[1:] if base in {"fd", "fdfind"} and len(operands) >= 2 else (operands or ["."])
    return None


def check_recursive_search(command: str, cwd: Path, data_dir: Path) -> str | None:
    """Return a denial reason if *command* sweeps the wide runtime data tree."""
    for segment in (s.strip() for s in _SEGMENT_SPLIT.split(command) if s.strip()):
        try:
            argv = _shell_argv(segment)
        except ValueError:
            continue
        # Skip leading env assignments (FOO=bar cmd …).
        while argv and "=" in argv[0] and not argv[0].startswith("-"):
            argv = argv[1:]
        if not argv:
            continue
        if argv[0] == "cd":  # track cwd for the following segments
            cwd = (cwd / Path(argv[1]).expanduser()) if len(argv) > 1 else cwd
            continue
        targets = _search_targets(argv)
        if not targets:
            continue
        for raw in targets:
            path = Path(raw).expanduser()
            if not path.is_absolute():
                path = cwd / path
            if _is_broad_data_root(path, data_dir):
                return (
                    f"Recursive search over '{raw}' is denied: the runtime data tree is "
                    "multi-GB and sweeping it stalls every running task. Search a specific "
                    "subdirectory or file (e.g. state/current_state.md, knowledge/, shared/task_results/<file>)."
                )
    return None


# ── Pure evaluation ───────────────────────────────────────────────────────


def _matching_injection_pattern(command: str, injection_pattern_names: tuple[tuple[str, str], ...]) -> str:
    """Return the name of the first injection pattern matching *command*."""
    for name, pattern in injection_pattern_names:
        try:
            if re.search(pattern, command):
                return name
        except re.error:
            continue
    return "unknown"


_OTHER_ANIMA_WRITE_MSG = "Command targets other anima's directory: {arg}"
_TRAVERSAL_MSG = "Command argument resolves outside anima directory"
_EMPTY_MSG = "Empty command"


def _evaluate_allowlist(
    ctx: CommandPolicyContext, segments: list[tuple[list[str] | None, str]]
) -> CommandDecision | None:
    """Layer 7: allowlist gate. Returns None when allowed (or allow_all)."""
    if ctx.permissions.commands.allow_all:
        return None
    allowed = ctx.permissions.commands.allow
    if not allowed:
        return CommandDecision(False, "allowlist", "Command execution not enabled in permissions")
    for argv, _raw in segments:
        if argv is None:
            return CommandDecision(False, "syntax", "Invalid command syntax")
        if not argv:
            continue
        cmd_base = argv[0]
        if cmd_base not in allowed:
            return CommandDecision(False, "allowlist", f"Command '{cmd_base}' not in allowed list")
    return None


def _evaluate_traversal(
    ctx: CommandPolicyContext, segments: list[tuple[list[str] | None, str]]
) -> CommandDecision | None:
    """Layer 8: reject ``..`` arguments that resolve outside the anima dir."""
    for argv, _raw in segments:
        if argv is None:
            continue
        for arg in argv[1:]:
            if ".." not in arg:
                continue
            try:
                resolved = (ctx.anima_dir / arg).resolve()
                if not resolved.is_relative_to(ctx.anima_dir):
                    return CommandDecision(False, "traversal", _TRAVERSAL_MSG)
            except (ValueError, OSError):
                pass
    return None


def _evaluate_other_anima_write(
    ctx: CommandPolicyContext, segments: list[tuple[list[str] | None, str]]
) -> CommandDecision | None:
    """Layer 9: block writes into another anima's directory."""
    animas_root = ctx.anima_dir.parent
    for argv, _raw in segments:
        if not argv:
            continue
        if Path(argv[0]).name not in _WRITE_COMMANDS:
            continue
        for arg in argv[1:]:
            if arg.startswith("-"):
                continue
            try:
                resolved = Path(arg).resolve()
                if resolved.is_relative_to(animas_root) and not resolved.is_relative_to(ctx.anima_dir):
                    return CommandDecision(False, "other_anima_write", _OTHER_ANIMA_WRITE_MSG.format(arg=arg))
            except (ValueError, OSError):
                pass
    return None


def evaluate_command(command: str, ctx: CommandPolicyContext) -> CommandDecision:
    """Evaluate *command* against *ctx* and return the decision.

    Pure: no file reads, logging or config loading.
    """
    # 1. superuser -> allow
    if ctx.superuser:
        return CommandDecision(True, "ok", "")

    # 2. empty -> empty
    if not command or not command.strip():
        return CommandDecision(False, "empty", _EMPTY_MSG)

    # 3. injection detection (record; deny only on enforce)
    injection_hit: str | None = None
    if ctx.injection_mode != "off" and ctx.injection_re is not None and ctx.injection_re.search(command):
        injection_hit = _matching_injection_pattern(command, ctx.injection_pattern_names)
        if ctx.injection_mode == "enforce":
            return CommandDecision(
                False,
                "injection",
                f"Command contains injection pattern: {injection_hit}",
                injection_hit=injection_hit,
            )

    # 4. global deny
    for pattern, reason in ctx.blocked_patterns:
        if pattern.search(command):
            return CommandDecision(False, "global_deny", reason, injection_hit=injection_hit)

    # 5. recursive-search guard
    search_reason = check_recursive_search(command, ctx.cwd, ctx.data_dir)
    if search_reason:
        return CommandDecision(False, "recursive_search", search_reason, injection_hit=injection_hit)

    segments = split_segments(command)

    # 6. per-anima deny
    from core.config.schemas import command_deny_matches

    if ctx.permissions.commands.deny:
        for argv, raw in segments:
            if argv is None or not argv:
                continue
            cmd_base = argv[0]
            for denied in ctx.permissions.commands.deny:
                if command_deny_matches(denied, raw, cmd_base):
                    return CommandDecision(
                        False,
                        "anima_deny",
                        f"Command '{cmd_base}' is in denied list ('{denied}')",
                        injection_hit=injection_hit,
                    )

    # 7. allowlist
    if not ctx.permissions.commands.allow_all:
        allow_decision = _evaluate_allowlist(ctx, segments)
        if allow_decision is not None:
            if allow_decision.layer == "allowlist":
                return CommandDecision(False, "allowlist", allow_decision.reason, injection_hit=injection_hit)
            return CommandDecision(False, "syntax", allow_decision.reason, injection_hit=injection_hit)

    # 8. traversal
    trav_decision = _evaluate_traversal(ctx, segments)
    if trav_decision is not None:
        return replace(trav_decision, injection_hit=trav_decision.injection_hit or injection_hit)

    # 9. other-anima write
    write_decision = _evaluate_other_anima_write(ctx, segments)
    if write_decision is not None:
        return replace(write_decision, injection_hit=write_decision.injection_hit or injection_hit)

    return CommandDecision(True, "ok", "", injection_hit=injection_hit)


# ── Loader ─────────────────────────────────────────────────────────────────


def load_command_policy_context(
    anima_dir: Path,
    *,
    cwd: Path | None = None,
    superuser: bool = False,
    global_permissions_path: Path | None = None,
    permissions: object | None = None,
) -> CommandPolicyContext:
    """Assemble a :class:`CommandPolicyContext` from config sources.

    Uses the process-level ``GlobalPermissionsCache`` when loaded (server
    paths); otherwise reads the global permissions file directly (Codex
    hook, which runs in a separate process where the cache's interactive
    startup-hash check must not run).  ``permissions`` lets a caller supply
    an already-loaded per-Anima config (e.g. the ToolHandler, which keeps
    its legacy patching seam through ``_load_permissions_config``).
    """
    from core.config.global_permissions import GlobalPermissionsCache, _build_injection_re, _compile_patterns
    from core.config.schemas import GlobalPermissionsConfig, load_permissions

    resolved_anima = anima_dir.resolve()
    data_dir = resolved_anima.parent.parent

    cache = GlobalPermissionsCache.get()
    if cache.loaded and cache.config is not None:
        config: GlobalPermissionsConfig | None = cache.config
        injection_re = cache.injection_re
        blocked = tuple(cache.blocked_patterns)
        mode = cache.config.sdk_bash_injection.mode
        injection_names = tuple((p.name or p.pattern, p.pattern) for p in cache.config.injection_patterns)
    else:
        # Codex hook (separate process) — validate against the file directly.
        path = global_permissions_path
        if path is None:
            from core.paths import get_global_permissions_path

            path = get_global_permissions_path()
        if path is not None and path.is_file():
            config = GlobalPermissionsConfig.model_validate(_json.loads(path.read_text(encoding="utf-8")))
            injection_re = _build_injection_re(config.injection_patterns)
            blocked = tuple(_compile_patterns(config.commands.deny))
            mode = config.sdk_bash_injection.mode
            injection_names = tuple((p.name or p.pattern, p.pattern) for p in config.injection_patterns)
        else:
            config = None
            injection_re = None
            blocked = ()
            mode = "log"
            injection_names = ()

    permissions = permissions if permissions is not None else load_permissions(resolved_anima)
    return CommandPolicyContext(
        anima_dir=resolved_anima,
        data_dir=data_dir,
        cwd=cwd.resolve() if cwd is not None else resolved_anima,
        permissions=permissions,
        injection_re=injection_re,
        injection_mode=mode,
        blocked_patterns=blocked,
        injection_pattern_names=injection_names,
        superuser=superuser,
    )


# ── Audit recording ────────────────────────────────────────────────────────


def record_injection_hit(
    command: str,
    ctx: CommandPolicyContext,
    *,
    pattern_name: str,
    trigger: str,
) -> None:
    """Append a structured Mode S injection hit to its dedicated JSONL log."""
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "pattern_name": pattern_name,
        "command": command[:500],
        "anima": ctx.anima_dir.name,
        "trigger": trigger,
        "mode": ctx.injection_mode,
    }
    line = _json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    logger.warning("sdk_bash_injection_hit %s", line)
    try:
        log_path = ctx.data_dir / "logs" / "sdk_bash_injection.jsonl"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        logger.warning("Failed to write Bash injection audit log", exc_info=True)
