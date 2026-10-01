# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CLI dispatch for external tools, submit tasks, and command aliases."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from core.integrations import (
    TOOL_MODULES,
    discover_common_tools,
    discover_personal_tools,
    load_tool_module,
)
from core.platform.env import anima_dir_env

logger = logging.getLogger("animaworks.tools")

MAIN_CLI_COMMANDS: frozenset[str] = frozenset(
    {
        "init",
        "start",
        "serve",
        "stop",
        "restart",
        "reset",
        "chat",
        "heartbeat",
        "send",
        "status",
        "logs",
        "board",
        "anima",
        "config",
        "task",
        "internal",
        "supervisor",
        "vault",
        "models",
        "cost",
        "optimize-assets",
        "remake",
        "profile",
    }
)

ANIMA_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "list",
        "info",
        "status",
        "restart",
        "create",
        "delete",
        "enable",
        "disable",
        "set-model",
        "set-background-model",
        "reload",
        "set-role",
        "rename",
        "audit",
    }
)

_SUBMIT_TASK_ID_LENGTH = 12


def _load_cli_profile(
    tool_name: str,
    origin: str,
    tool_file: Path | None,
) -> dict | None:
    """Load EXECUTION_PROFILE for a CLI tool (core, common, or personal)."""
    try:
        if origin == "core":
            if tool_name not in TOOL_MODULES:
                return None
            mod = load_tool_module(tool_name, TOOL_MODULES)
            return getattr(mod, "EXECUTION_PROFILE", None)
        if tool_file is None:
            return None
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            f"animaworks_cli_profile_{tool_name}",
            tool_file,
        )
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return getattr(mod, "EXECUTION_PROFILE", None)
    except Exception:
        logger.debug("Failed to load CLI EXECUTION_PROFILE for %s", tool_name, exc_info=True)
        return None


def _gated_action_candidates(
    origin: str,
    tool_name: str,
    tool_file: Path | None,
    action_candidates: list[str],
) -> list[str]:
    """Return candidate actions that are gated in the tool's EXECUTION_PROFILE."""
    profile = _load_cli_profile(tool_name, origin, tool_file)
    if not isinstance(profile, dict):
        return []
    gated: list[str] = []
    for candidate in action_candidates:
        profile_key = candidate if candidate in profile else candidate.replace("_", "-")
        info = profile.get(profile_key)
        if isinstance(info, dict) and info.get("gated") is True:
            gated.append(candidate)
    return gated


def _handle_submit(argv: list[str]) -> None:
    """Handle ``animaworks-tool submit <tool> <args...>``.

    Stores a command task in TaskStore and exits immediately. The task watcher
    claims it and executes the tool in the background lane.
    """
    import json
    import shlex
    import time
    import uuid

    if len(argv) < 1:
        print("Usage: animaworks-tool submit <tool_name> [args...]")
        print("Submits a long-running tool for background execution.")
        print("Results are delivered to your inbox on completion.")
        sys.exit(1)

    tool_name = argv[0]
    tool_args = argv[1:]

    anima_dir = anima_dir_env() or ""
    if not anima_dir:
        print(
            "Error: ANIMAWORKS_ANIMA_DIR not set. Cannot determine the task owner.",
        )
        sys.exit(1)

    anima_dir_path = Path(anima_dir)
    anima_name = anima_dir_path.name

    # Generate task ID
    task_id = uuid.uuid4().hex[:_SUBMIT_TASK_ID_LENGTH]

    # Determine subcommand (first non-flag argument after tool_name)
    subcommand = ""
    for arg in tool_args:
        if not arg.startswith("-"):
            subcommand = arg
            break

    # Permission gate before submitting the task (fail early).
    from core.tooling.permissions import check_tool_access

    if tool_name in TOOL_MODULES:
        submit_origin = "core"
        submit_file: Path | None = None
    else:
        common_tools = discover_common_tools()
        personal_tools = discover_personal_tools(anima_dir_path)
        if tool_name in personal_tools:
            submit_origin = "personal"
            submit_file = Path(personal_tools[tool_name])
        elif tool_name in common_tools:
            submit_origin = "common"
            submit_file = Path(common_tools[tool_name])
        else:
            submit_origin = "core"
            submit_file = None
    if submit_origin != "core" or tool_name in TOOL_MODULES:
        submit_decision = check_tool_access(
            anima_dir_path,
            tool_name,
            subcommand or None,
            origin=submit_origin,  # type: ignore[arg-type]
            tool_file=submit_file,
        )
        if not submit_decision.allowed:
            print(f"Error: {submit_decision.message}", file=sys.stderr)
            sys.exit(1)

    # Optional: check EXECUTION_PROFILE for warning
    try:
        if tool_name in TOOL_MODULES:
            mod = load_tool_module(tool_name, TOOL_MODULES)
            profile = getattr(mod, "EXECUTION_PROFILE", None)
            if profile and subcommand and subcommand in profile:
                info = profile[subcommand]
                if not info.get("background_eligible"):
                    print(
                        f"Warning: {tool_name} {subcommand} is not marked "
                        f"as long-running "
                        f"(expected ~{info.get('expected_seconds', '?')}s). "
                        f"Consider running directly instead.",
                        file=sys.stderr,
                    )
    except Exception:
        logger.debug("Profile check failed for %s %s", tool_name, subcommand, exc_info=True)

    submitted_at = time.time()
    title = f"{tool_name}:{subcommand}" if subcommand else tool_name
    task_desc = {
        "task_type": "command",
        "task_id": task_id,
        "tool_name": tool_name,
        "subcommand": subcommand,
        "raw_args": tool_args,
        "anima_name": anima_name,
        "anima_dir": str(anima_dir_path),
        "submitted_at": submitted_at,
        "submitted_by": anima_name,
        "status": "pending",
        "title": title,
        "description": shlex.join(["animaworks-tool", tool_name, *tool_args]),
    }
    from core.tasks.queue import TaskQueueManager

    TaskQueueManager(anima_dir_path).submit(task_desc, source="anima", meta={"executor": "command"})

    # Output result
    result = {
        "task_id": task_id,
        "status": "submitted",
        "tool": tool_name,
        "subcommand": subcommand,
        "message": (f"バックグラウンドタスクを投入しました。完了時にinboxに通知されます。(task_id: {task_id})"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cli_dispatch() -> None:
    """Dispatch external tools and main CLI aliases from the CLI layer."""
    common = discover_common_tools()
    anima_dir_str = anima_dir_env() or ""
    personal = discover_personal_tools(Path(anima_dir_str)) if anima_dir_str else {}
    all_tools = set(TOOL_MODULES) | set(common) | set(personal)

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        tools = ", ".join(sorted(all_tools))
        print("Usage: animaworks-tool <tool_name> [args...]")
        print(f"Available tools: {tools}")
        sys.exit(0 if "--help" in sys.argv else 1)

    tool_name = sys.argv[1]

    # Handle submit subcommand — write pending task and exit immediately.
    if tool_name == "submit":
        _handle_submit(sys.argv[2:])
        return

    # The previous CLI adapter routed tool names before command aliases.
    # Preserve that priority while keeping main-CLI commands out of the tool
    # policy/output path.
    if tool_name not in all_tools:
        if tool_name in MAIN_CLI_COMMANDS:
            sys.argv = ["animaworks", *sys.argv[1:]]
            from cli import cli_main

            cli_main()
            return
        if tool_name in ANIMA_SUBCOMMANDS:
            sys.argv = ["animaworks", "anima", *sys.argv[1:]]
            from cli import cli_main

            cli_main()
            return

    # Attach relevant ACTION-RULES to stderr (before loading tool modules).
    if anima_dir_str:
        try:
            from core.tooling.policy.action_gate import (
                action_tool_name_from_cli_argv,
                find_action_rules,
                format_action_rules,
            )

            action_tool_name = action_tool_name_from_cli_argv(sys.argv[1:])
            if action_tool_name:
                rules = find_action_rules(Path(anima_dir_str), action_tool_name, {"argv": sys.argv[1:]})
                rendered = format_action_rules(rules)
                if rendered:
                    print(rendered, file=sys.stderr)
        except Exception:
            logger.debug("CLI action rule attach failed for %s", tool_name, exc_info=True)

    # Permission gate (tool-level + gated action). Only for real external tools;
    # main-CLI forwarding commands (internal, task, ...) are not gated here.
    if anima_dir_str and tool_name in all_tools:
        from core.tooling.permissions import check_tool_access

        if tool_name in TOOL_MODULES:
            origin = "core"
            tool_file: Path | None = None
        elif tool_name in personal:
            origin = "personal"
            tool_file = Path(personal[tool_name])
        else:
            origin = "common"
            tool_file = Path(common[tool_name])

        # Tool-level check always.
        decision = check_tool_access(Path(anima_dir_str), tool_name, None, origin=origin, tool_file=tool_file)
        if not decision.allowed:
            print(f"Error: {decision.message}", file=sys.stderr)
            sys.exit(1)

        # Gated action check: every non-option argument matching a gated
        # profile action must be explicitly permitted.
        action_candidates = [arg for arg in sys.argv[2:] if not arg.startswith("-")]
        gated_candidates = _gated_action_candidates(origin, tool_name, tool_file, action_candidates)
        for candidate in gated_candidates:
            check = check_tool_access(
                Path(anima_dir_str),
                tool_name,
                candidate,
                origin=origin,
                tool_file=tool_file,
            )
            if not check.allowed:
                print(f"Error: {check.message}", file=sys.stderr)
                sys.exit(1)

    # Try core tools first.
    if tool_name in TOOL_MODULES:
        mod = load_tool_module(tool_name, TOOL_MODULES)
        if not hasattr(mod, "cli_main"):
            print(f"Tool '{tool_name}' has no CLI interface")
            sys.exit(1)
        mod.cli_main(sys.argv[2:])
        return

    # Try common or personal tools (loaded from file path).
    file_tool = personal.get(tool_name) or common.get(tool_name)
    if file_tool:
        import importlib.util

        origin = "personal" if tool_name in personal else "common"
        spec = importlib.util.spec_from_file_location(
            f"animaworks_{origin}_tool_{tool_name}",
            file_tool,
        )
        if spec is None or spec.loader is None:
            print(f"Cannot load {origin} tool: {tool_name}")
            sys.exit(1)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        if not hasattr(mod, "cli_main"):
            print(f"{origin.capitalize()} tool '{tool_name}' has no CLI interface")
            sys.exit(1)
        mod.cli_main(sys.argv[2:])
        return

    print(f"Unknown command: {tool_name}")
    print(f"Available tools: {', '.join(sorted(all_tools))}")
    sys.exit(1)
