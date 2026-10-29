"""Tests for MCP per-tool timeout overrides."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from core.mcp.server import _TOOL_TIMEOUT_OVERRIDES
from core.tooling.policy.surface import MCP_TOOL_NAMES


def test_timeout_override_keys_are_exposed_tools() -> None:
    """Every timeout override must reference a tool exposed by the MCP server.

    If a key is not in ``MCP_TOOL_NAMES`` the override is dead and
    will never be reached.
    """
    assert set(_TOOL_TIMEOUT_OVERRIDES).issubset(MCP_TOOL_NAMES)
