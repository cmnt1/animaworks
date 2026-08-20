"""Unit tests for Mode S (Agent SDK) native skill suppression.

Verifies that ``_build_sdk_options()`` passes ``skills=[]`` to the
``ClaudeAgentOptions`` so the engine does not load its own native skills
from ``~/.claude/skills`` — skill presentation stays unified under
animaworks' own skill catalog.
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import inspect
from pathlib import Path

from core.execution.agent_sdk import AgentSDKExecutor
from core.schemas import ModelConfig


def _make_executor(anima_dir: Path) -> AgentSDKExecutor:
    """Create an AgentSDKExecutor with minimal config."""
    mc = ModelConfig(model="claude-sonnet-4-6", api_key="test-key")
    return AgentSDKExecutor(model_config=mc, anima_dir=anima_dir)


class TestSDKSkillsDisabled:
    """Verify the Agent SDK options suppress native skill loading."""

    def test_build_sdk_options_sets_empty_skills(self, tmp_path: Path) -> None:
        """_build_sdk_options() must include skills=[] to turn engine skills off."""
        executor = _make_executor(tmp_path / "animas" / "test-anima")
        options, _temp_files = executor._build_sdk_options("system", 64000, {})
        assert options.skills == [], (
            "options.skills must be an empty list so the engine does not load "
            "host ~/.claude/skills as its own native skills"
        )

    def test_skills_guard_is_version_aware(self) -> None:
        """The skills kwarg must be guarded so older SDKs without the field still work."""
        from core.execution.agent_sdk import AgentSDKExecutor

        source = inspect.getsource(AgentSDKExecutor._build_sdk_options)
        assert "hasattr(ClaudeAgentOptions, \"skills\")" in source, (
            "skills must be assigned conditionally (hasattr) for SDK compatibility"
        )
        assert "kwargs[\"skills\"]" in source, (
            "_build_sdk_options must set kwargs properly has guard"
        )
