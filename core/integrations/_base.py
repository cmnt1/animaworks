from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Base infrastructure for AnimaWorks tools."""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("animaworks.tools")

# Previously generated runtime common_tools may still import these helpers here.
# In-repository callers use core.credentials directly; keep this light shim only
# for data copied from the old tool-creator template.
from core.credentials import get_credential, get_env_or_fail, resolve_env_style_credential  # noqa: F401
from core.exceptions import ToolConfigError  # noqa: F401 – re-export


@dataclass
class ToolResult:
    """Standardized return value from tool execution."""

    success: bool
    data: Any = None
    text: str = ""
    error: str | None = None


def dispatch_by_table(
    handlers: Mapping[str, Callable[[dict[str, Any]], Any]],
    name: str,
    args: dict[str, Any],
    *,
    unknown_result: Callable[[str], Any] | None = None,
    unknown_error: Callable[[str], Exception] | None = None,
) -> Any:
    """Call the handler registered for *name*, preserving each tool's fallback."""
    handler = handlers.get(name)
    if handler is not None:
        return handler(args)
    if unknown_result is not None:
        return unknown_result(name)
    if unknown_error is not None:
        raise unknown_error(name)
    raise ValueError(f"Unknown tool: {name}")


def without_anima_dir(args: Mapping[str, Any]) -> dict[str, Any]:
    """Copy Google tool arguments without the dispatcher-only ``anima_dir``."""
    return {key: value for key, value in args.items() if key != "anima_dir"}


def auto_cli_guide(tool_name: str, schemas: list[dict[str, Any]]) -> str:
    """Auto-generate a CLI usage guide from tool schemas.

    Produces a markdown snippet showing ``animaworks-tool`` CLI usage for
    each schema, deriving argument flags from JSON Schema properties.

    Args:
        tool_name: The TOOL_MODULES key (e.g. ``"web_search"``).
        schemas: The list returned by ``get_tool_schemas()``.

    Returns:
        Markdown string with CLI examples.
    """
    lines = [f"### {tool_name}", "```bash"]
    for schema in schemas:
        params = schema.get("input_schema", schema.get("parameters", {}))
        props = params.get("properties", {})
        required = set(params.get("required", []))

        parts = [f"animaworks-tool {tool_name}"]
        # Positional: first required string parameter
        for pname in required:
            prop = props.get(pname, {})
            if prop.get("type") == "string":
                parts.append(f'"<{pname}>"')
                break
        # Optional flags
        for pname, prop in props.items():
            if pname in required:
                continue
            flag = f"--{pname.replace('_', '-')}"
            ptype = prop.get("type", "string")
            if ptype == "boolean":
                parts.append(f"[{flag}]")
            else:
                parts.append(f"[{flag} <{ptype}>]")
        parts.append("-j")
        lines.append(" ".join(parts))
    lines.append("```")
    return "\n".join(lines)


def load_execution_profiles(
    tool_modules: dict[str, str],
    personal_tools: dict[str, str] | None = None,
) -> dict[str, dict[str, dict[str, object]]]:
    """Load EXECUTION_PROFILE from all tool modules.

    Returns:
        Nested dict: {tool_name: {subcommand: {expected_seconds, background_eligible}}}.
        Tools without EXECUTION_PROFILE are omitted.
    """
    import importlib
    import importlib.util

    profiles: dict[str, dict[str, dict[str, object]]] = {}

    for tool_name, module_path in tool_modules.items():
        try:
            mod = importlib.import_module(module_path)
            if hasattr(mod, "EXECUTION_PROFILE"):
                profiles[tool_name] = mod.EXECUTION_PROFILE
        except Exception:
            logger.debug("Failed to load EXECUTION_PROFILE for %s", tool_name, exc_info=True)

    if personal_tools:
        for tool_name, file_path in personal_tools.items():
            try:
                spec = importlib.util.spec_from_file_location(
                    f"animaworks_profile_{tool_name}",
                    file_path,
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "EXECUTION_PROFILE"):
                        profiles[tool_name] = mod.EXECUTION_PROFILE
            except Exception:
                logger.debug("Failed to load EXECUTION_PROFILE for personal tool %s", tool_name, exc_info=True)

    return profiles


def get_eligible_tools_from_profiles(
    profiles: dict[str, dict[str, dict[str, object]]],
) -> dict[str, int]:
    """Extract eligible tools map from loaded profiles.

    Returns:
        Dict of {tool_subcommand_key: expected_seconds} for background_eligible=True entries.
        The key format matches BackgroundTaskManager expectations.
    """
    eligible: dict[str, int] = {}
    for tool_name, subcommands in profiles.items():
        for subcmd, info in subcommands.items():
            if info.get("background_eligible"):
                raw = info.get("expected_seconds", 60)
                eligible[f"{tool_name}:{subcmd}"] = int(str(raw)) if raw is not None else 60
    return eligible
