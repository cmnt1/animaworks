"""Tests for guide.py — build_tools_guide is deprecated (returns empty)."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from core.tooling.guide import build_tools_guide


class TestBuildToolsGuideDeprecated:
    """build_tools_guide is deprecated and always returns empty string."""

    def test_empty_registry(self):
        assert build_tools_guide([]) == ""

    def test_with_registry(self):
        assert build_tools_guide(["chatwork", "slack"]) == ""

    def test_with_personal_tools(self):
        assert build_tools_guide([], {"my_tool": "/path/to/tool.py"}) == ""

    def test_with_both(self):
        assert build_tools_guide(["chatwork"], {"my_tool": "/path/to/tool.py"}) == ""
