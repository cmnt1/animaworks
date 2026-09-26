from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Schema loading from external and personal tool modules."""

import importlib
import importlib.util
import logging
from typing import Any

logger = logging.getLogger("animaworks.tool_schemas")


def _normalise_schema(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalise a single tool schema to canonical format."""
    return {
        "name": raw["name"],
        "description": raw.get("description", ""),
        "parameters": raw.get("input_schema", raw.get("parameters", {})),
    }


def load_external_schemas(tool_registry: list[str]) -> list[dict[str, Any]]:
    """Load schemas from external tool modules, normalised to canonical format."""
    if not tool_registry:
        return []

    from core.integrations import TOOL_MODULES

    schemas: list[dict[str, Any]] = []
    for tool_name in tool_registry:
        if tool_name not in TOOL_MODULES:
            continue
        try:
            mod = importlib.import_module(TOOL_MODULES[tool_name])
            if not hasattr(mod, "get_tool_schemas"):
                continue
            for s in mod.get_tool_schemas():
                schemas.append(_normalise_schema(s))
        except Exception:
            logger.debug("Failed to load schemas for %s", tool_name, exc_info=True)
    return schemas


def load_personal_tool_schemas(
    personal_tools: dict[str, str],
) -> list[dict[str, Any]]:
    """Load schemas from personal tool modules, normalised to canonical format."""
    schemas: list[dict[str, Any]] = []
    for tool_name, file_path in personal_tools.items():
        try:
            spec = importlib.util.spec_from_file_location(
                f"animaworks_personal_tool_{tool_name}",
                file_path,
            )
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            if not hasattr(mod, "get_tool_schemas"):
                continue
            for s in mod.get_tool_schemas():
                schemas.append(_normalise_schema(s))
        except Exception:
            logger.debug(
                "Failed to load personal tool schemas: %s",
                tool_name,
                exc_info=True,
            )
    return schemas


def load_external_schemas_by_category(
    categories: set[str],
) -> list[dict[str, Any]]:
    """Load external tool schemas filtered by permitted categories.

    *categories* is a set of tool module names (e.g. ``{"chatwork", "slack"}``).
    Only schemas belonging to those modules are returned.
    """
    from core.integrations import TOOL_MODULES

    filtered_registry = [name for name in TOOL_MODULES if name in categories]
    return load_external_schemas(filtered_registry)


def load_all_tool_schemas(
    tool_registry: list[str] | None = None,
    personal_tools: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Load and normalise tool schemas from all enabled modules."""
    schemas = load_external_schemas(tool_registry or [])
    if personal_tools:
        schemas.extend(load_personal_tool_schemas(personal_tools))
    return schemas
