# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""AnimaWorks external tools package."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from core.platform.atomic_io import atomic_write_json

logger = logging.getLogger("animaworks.tools")


def discover_core_tools() -> dict[str, str]:
    """Scan core/integrations/ for tool modules.

    Returns: Mapping of tool_name → module path (e.g., "core.integrations.web_search").
    Skips files starting with _ (private/internal modules, e.g. ``_anima_icon_url.py``).
    """
    tools_dir = Path(__file__).parent
    core: dict[str, str] = {}
    for f in sorted(tools_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        tool_name = f.stem
        core[tool_name] = f"core.integrations.{tool_name}"
    return core


# Backward-compatible module-level variable
TOOL_MODULES = discover_core_tools()


def discover_common_tools(data_dir: Path | None = None) -> dict[str, str]:
    """Scan ~/.animaworks/common_tools/ for shared tool modules.

    Returns: Mapping of tool_name → absolute file path.
    """
    if data_dir is None:
        from core.paths import get_data_dir

        data_dir = get_data_dir()
    tools_dir = data_dir / "common_tools"
    if not tools_dir.is_dir():
        return {}
    common: dict[str, str] = {}
    for f in sorted(tools_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        tool_name = f.stem
        if tool_name in TOOL_MODULES:
            logger.warning(
                "Common tool '%s' shadows core tool — skipped",
                tool_name,
            )
            continue
        common[tool_name] = str(f)
    if common:
        logger.info("Discovered common tools: %s", list(common.keys()))
    return common


def discover_personal_tools(anima_dir: Path) -> dict[str, str]:
    """Scan ``{anima_dir}/tools/`` for personal tool modules.

    Returns:
        Mapping of tool_name → absolute file path.
        Skips files starting with ``_`` (including ``__init__.py``).
    """
    tools_dir = anima_dir / "tools"
    if not tools_dir.is_dir():
        return {}
    personal: dict[str, str] = {}
    for f in sorted(tools_dir.glob("*.py")):
        if f.name.startswith("_"):
            continue
        tool_name = f.stem
        if tool_name in TOOL_MODULES:
            logger.warning(
                "Personal tool '%s' shadows core tool — skipped",
                tool_name,
            )
            continue
        personal[tool_name] = str(f)
    if personal:
        logger.info("Discovered personal tools: %s", list(personal.keys()))
    return personal


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
            import importlib

            mod = importlib.import_module(TOOL_MODULES[tool_name])
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
    for cand in action_candidates:
        pkey = cand if cand in profile else cand.replace("_", "-")
        info = profile.get(pkey)
        if isinstance(info, dict) and info.get("gated") is True:
            gated.append(cand)
    return gated


def _handle_submit(argv: list[str]) -> None:
    """Handle ``animaworks-tool submit <tool> <args...>``.

    Writes a pending task descriptor to ``state/background_tasks/pending/``
    and exits immediately.  The runner's pending watcher will pick it up.
    """
    import json
    import os
    import time
    import uuid

    if len(argv) < 1:
        print("Usage: animaworks-tool submit <tool_name> [args...]")
        print("Submits a long-running tool for background execution.")
        print("Results are delivered to your inbox on completion.")
        sys.exit(1)

    tool_name = argv[0]
    tool_args = argv[1:]

    anima_dir = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
    if not anima_dir:
        print(
            "Error: ANIMAWORKS_ANIMA_DIR not set. Cannot determine pending directory.",
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

    # Permission gate before writing the descriptor (fail early).
    from core.tooling.permissions import check_tool_access

    if tool_name in TOOL_MODULES:
        submit_origin = "core"
        submit_file: Path | None = None
    else:
        from core.integrations import discover_common_tools, discover_personal_tools

        _common = discover_common_tools()
        _personal = discover_personal_tools(anima_dir_path)
        if tool_name in _personal:
            submit_origin = "personal"
            submit_file = Path(_personal[tool_name])
        elif tool_name in _common:
            submit_origin = "common"
            submit_file = Path(_common[tool_name])
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
            import importlib

            mod = importlib.import_module(TOOL_MODULES[tool_name])
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

    # Write pending task descriptor
    pending_dir = anima_dir_path / "state" / "background_tasks" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    task_desc = {
        "task_id": task_id,
        "tool_name": tool_name,
        "subcommand": subcommand,
        "raw_args": tool_args,
        "anima_name": anima_name,
        "anima_dir": str(anima_dir_path),
        "submitted_at": time.time(),
        "status": "pending",
    }

    task_path = pending_dir / f"{task_id}.json"
    atomic_write_json(task_path, task_desc, indent=2, ensure_ascii=False)

    # Output result
    result = {
        "task_id": task_id,
        "status": "submitted",
        "tool": tool_name,
        "subcommand": subcommand,
        "message": (f"バックグラウンドタスクを投入しました。完了時にinboxに通知されます。(task_id: {task_id})"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cli_dispatch():
    """Dispatch a core, common, or personal external-tool CLI command.

    Supports core tools (from ``TOOL_MODULES``), common tools
    (from ``common_tools/``), and personal tools discovered via
    the ``ANIMAWORKS_ANIMA_DIR`` environment variable.
    """
    import os

    # Discover common tools
    common = discover_common_tools()

    # Discover personal tools if anima_dir is set
    anima_dir_str = os.environ.get("ANIMAWORKS_ANIMA_DIR", "")
    personal: dict[str, str] = {}
    if anima_dir_str:
        personal = discover_personal_tools(Path(anima_dir_str))

    all_tools = set(TOOL_MODULES.keys()) | set(common.keys()) | set(personal.keys())

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        tools = ", ".join(sorted(all_tools))
        print("Usage: animaworks-tool <tool_name> [args...]")
        print(f"Available tools: {tools}")
        sys.exit(0 if "--help" in sys.argv else 1)

    tool_name = sys.argv[1]

    # Handle submit subcommand — write pending task and exit immediately
    if tool_name == "submit":
        _handle_submit(sys.argv[2:])
        return

    # Attach relevant ACTION-RULES to stderr (before loading tool modules).
    if anima_dir_str:
        try:
            from core.tooling.action_gate import (
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

        # Gated action check: every non-option argument that matches a gated
        # profile action must be explicitly permitted.
        action_candidates = [a for a in sys.argv[2:] if not a.startswith("-")]
        gated_candidates = _gated_action_candidates(origin, tool_name, tool_file, action_candidates)
        for cand in gated_candidates:
            check = check_tool_access(
                Path(anima_dir_str),
                tool_name,
                cand,
                origin=origin,
                tool_file=tool_file,
            )
            if not check.allowed:
                print(f"Error: {check.message}", file=sys.stderr)
                sys.exit(1)

    # Try core tools first
    if tool_name in TOOL_MODULES:
        import importlib

        mod = importlib.import_module(TOOL_MODULES[tool_name])
        if not hasattr(mod, "cli_main"):
            print(f"Tool '{tool_name}' has no CLI interface")
            sys.exit(1)
        mod.cli_main(sys.argv[2:])
        return

    # Try common or personal tools (loaded from file path)
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
