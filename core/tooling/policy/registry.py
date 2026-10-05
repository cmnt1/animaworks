from __future__ import annotations

"""Canonical registry and loader for built-in external tool modules."""

import importlib
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType


def discover_core_tools() -> dict[str, str]:
    """Scan ``core/integrations`` for public tool modules."""
    tools_dir = Path(__file__).resolve().parents[2] / "integrations"
    return {
        path.stem: f"core.integrations.{path.stem}"
        for path in sorted(tools_dir.glob("*.py"))
        if not path.name.startswith("_")
    }


TOOL_MODULES = discover_core_tools()


def load_tool_module(
    tool_name: str,
    registry: Mapping[str, str] | None = None,
) -> ModuleType:
    """Import a built-in tool module from its registry entry."""
    modules = TOOL_MODULES if registry is None else registry
    return importlib.import_module(modules[tool_name])
