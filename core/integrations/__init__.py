# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Core integration tool discovery and registry."""

from __future__ import annotations

import logging
from pathlib import Path

from core.tooling.policy.registry import TOOL_MODULES, discover_core_tools, load_tool_module  # noqa: F401

logger = logging.getLogger("animaworks.tools")


def discover_common_tools(data_dir: Path | None = None) -> dict[str, str]:
    """Scan the configured ``common_tools`` directory for shared tool modules.

    Returns a mapping of tool name to absolute file path.
    """
    if data_dir is None:
        from core.paths import get_data_dir

        data_dir = get_data_dir()
    tools_dir = data_dir / "common_tools"
    if not tools_dir.is_dir():
        return {}
    common: dict[str, str] = {}
    for file_path in sorted(tools_dir.glob("*.py")):
        if file_path.name.startswith("_"):
            continue
        tool_name = file_path.stem
        if tool_name in TOOL_MODULES:
            logger.warning(
                "Common tool '%s' shadows core tool — skipped",
                tool_name,
            )
            continue
        common[tool_name] = str(file_path)
    if common:
        logger.info("Discovered common tools: %s", list(common.keys()))
    return common


def discover_personal_tools(anima_dir: Path) -> dict[str, str]:
    """Scan ``{anima_dir}/tools/`` for personal tool modules.

    Returns a mapping of tool name to absolute file path. Files whose names
    begin with an underscore (including ``__init__.py``) are ignored.
    """
    tools_dir = anima_dir / "tools"
    if not tools_dir.is_dir():
        return {}
    personal: dict[str, str] = {}
    for file_path in sorted(tools_dir.glob("*.py")):
        if file_path.name.startswith("_"):
            continue
        tool_name = file_path.stem
        if tool_name in TOOL_MODULES:
            logger.warning(
                "Personal tool '%s' shadows core tool — skipped",
                tool_name,
            )
            continue
        personal[tool_name] = str(file_path)
    if personal:
        logger.info("Discovered personal tools: %s", list(personal.keys()))
    return personal
