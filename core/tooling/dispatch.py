from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""External tool dispatcher — unified dispatch convention.

All tool modules (core, common, personal) follow the same dispatch
convention: either a ``dispatch(name, args)`` function or individual
functions matching schema names.  The old ``_DISPATCH_TABLE`` has been
removed in favour of module-level ``dispatch()`` functions.
"""

import json
import logging
from pathlib import Path
from typing import Any

from core.exceptions import ToolExecutionError  # noqa: F401

logger = logging.getLogger("animaworks.external_tools")


# ── ExternalToolDispatcher ───────────────────────────────────


class ExternalToolDispatcher:
    """Dispatch tool calls to external tool modules.

    Uses a unified dispatch convention for all tool sources:
    core (importable modules), common and personal (file-based modules).
    """

    def __init__(
        self,
        tool_registry: list[str],
        personal_tools: dict[str, str] | None = None,
    ) -> None:
        self._registry = tool_registry
        self._personal_tools = personal_tools or {}

    @property
    def registry(self) -> list[str]:
        """Currently registered core tool names."""
        return self._registry

    def update_personal_tools(self, personal_tools: dict[str, str]) -> None:
        """Hot-reload: replace the personal/common tools mapping."""
        self._personal_tools = personal_tools

    def _check_access(self, name: str, args: dict[str, Any]) -> str | None:
        """Evaluate whether a schema name may be executed for this anima.

        Parses tool_name and action from the schema name (e.g. ``gmail_send``)
        and delegates the decision to :func:`core.tooling.permissions.check_tool_access`.
        Non-decomposable names return ``None`` (they become Unknown tool in dispatch).

        Returns:
            A JSON error string if blocked, ``None`` if allowed.
        """
        from core.tooling.permissions import check_tool_access

        anima_dir = args.get("anima_dir")

        tool_name, action = self._split_schema_name(name)
        if tool_name is None:
            return None

        if tool_name in self._personal_tools:
            origin = "personal"
            tool_file = Path(self._personal_tools[tool_name])
        else:
            origin = "core"
            tool_file = None

        decision = check_tool_access(
            Path(anima_dir) if anima_dir else None,
            tool_name,
            action,
            origin=origin,
            tool_file=tool_file,
        )
        if decision.allowed:
            return None
        return json.dumps(
            {
                "status": "error",
                "error_type": "PermissionDenied",
                "message": decision.message,
            },
            ensure_ascii=False,
        )

    def _split_schema_name(self, name: str) -> tuple[str | None, str | None]:
        """Split schema name into tool_name and action.

        Convention: name is {tool}_{action}. Matches against registry
        and personal tools, preferring longest match (e.g. image_gen over image).
        """
        from core.tooling.policy.registry import TOOL_MODULES

        all_tools = set(self._registry) | set(self._personal_tools.keys()) | set(TOOL_MODULES.keys())
        best_tool: str | None = None
        best_len = 0
        for tool in all_tools:
            prefix = f"{tool}_"
            if name.startswith(prefix) and len(tool) > best_len:
                best_tool = tool
                best_len = len(tool)
        if best_tool is None:
            return None, None
        action = name[len(best_tool) + 1 :]
        return best_tool, action if action else None

    def dispatch(self, name: str, args: dict[str, Any]) -> str | None:
        """Execute a tool by schema name.

        Tries core tools first (from TOOL_MODULES), then file-based tools
        (common + personal).  Returns None if no matching tool found.
        """
        err = self._check_access(name, args)
        if err is not None:
            return err

        result = self._dispatch_from_registry(name, args)
        if result is not None:
            return result
        result = self._dispatch_from_files(name, args)
        if result is not None:
            return result
        return None

    # ── Core tools (importable modules) ──────────────────────

    def _dispatch_from_registry(self, name: str, args: dict[str, Any]) -> str | None:
        """Dispatch to core tool modules registered in TOOL_MODULES."""
        if not self._registry:
            return None

        from core.tooling.policy.registry import TOOL_MODULES, load_tool_module

        tool_names = self._candidate_tool_names(name, TOOL_MODULES, set(self._registry))
        if not tool_names:
            return None

        for tool_name in tool_names:
            try:
                mod = load_tool_module(tool_name)
                schemas = mod.get_tool_schemas() if hasattr(mod, "get_tool_schemas") else []
                if name not in [s["name"] for s in schemas]:
                    continue
                return self._call_module(mod, name, args)
            except Exception as e:
                logger.warning("External tool %s failed: %s", name, e)
                return f"Error executing {name}: {e}"

        return None

    # ── File-based tools (common + personal) ─────────────────

    def _dispatch_from_files(self, name: str, args: dict[str, Any]) -> str | None:
        """Dispatch to file-based tool modules (common and personal)."""
        if not self._personal_tools:
            return None

        import importlib.util

        tool_names = self._candidate_tool_names(name, self._personal_tools, set(self._personal_tools))
        if not tool_names:
            return None

        for tool_name in tool_names:
            file_path = self._personal_tools[tool_name]
            try:
                spec = importlib.util.spec_from_file_location(
                    f"animaworks_tool_{tool_name}",
                    file_path,
                )
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore[union-attr]

                schemas = mod.get_tool_schemas() if hasattr(mod, "get_tool_schemas") else []
                if name not in [s["name"] for s in schemas]:
                    continue
                return self._call_module(mod, name, args)
            except Exception as e:
                logger.warning("Tool %s (%s) failed: %s", tool_name, name, e)
                return f"Error executing {name}: {e}"

        return None

    def _candidate_tool_names(
        self,
        schema_name: str,
        mapping: dict[str, str],
        allowed_tools: set[str],
    ) -> list[str]:
        """Return likely tool names for a schema without importing every module.

        Most schemas follow one of these conventions:
        - exact tool name (e.g. ``web_search``)
        - ``{tool}_{action}`` (e.g. ``slack_channel_post``)
        """
        if schema_name in mapping and schema_name in allowed_tools:
            return [schema_name]

        tool_name, _ = self._split_schema_name(schema_name)
        if tool_name and tool_name in mapping and tool_name in allowed_tools:
            return [tool_name]

        return [tool_name for tool_name in mapping if tool_name in allowed_tools]

    # ── Unified module call ──────────────────────────────────

    @staticmethod
    def _call_module(mod: Any, name: str, args: dict[str, Any]) -> str:
        """Call a tool module using the unified dispatch convention.

        Tries, in order:
        1. ``mod.dispatch(name, args)`` — recommended for multi-schema modules
        2. ``getattr(mod, name)(**args)`` — for single-schema modules
        """
        try:
            if hasattr(mod, "dispatch"):
                result = mod.dispatch(name, args)
            elif hasattr(mod, name):
                result = getattr(mod, name)(**args)
            else:
                logger.warning(
                    "Module has schema '%s' but no dispatch or matching function",
                    name,
                )
                return f"Error: no handler for '{name}'"

            if isinstance(result, (dict, list)):
                return json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            return str(result) if result is not None else "(no output)"
        except Exception as e:
            logger.warning("Tool %s failed: %s", name, e)
            return f"Error executing {name}: {e}"
