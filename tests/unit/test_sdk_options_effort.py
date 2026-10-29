"""Unit tests for Mode S (Agent SDK) thinking / effort options."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest

from core.execution.engines.claude.executor import AgentSDKExecutor
from core.schemas import ModelConfig


def _options(tmp_path: Path, **overrides):
    mc = ModelConfig(api_key="test-key", **overrides)
    executor = AgentSDKExecutor(model_config=mc, anima_dir=tmp_path / "animas" / "test-anima")
    options, _temp_files = executor._build_sdk_options("system", 64000, {})
    return options


class TestSDKEffort:
    def test_effort_sent_when_thinking_unset(self, tmp_path: Path) -> None:
        """Opus 5.5 animas leave ``thinking`` unset; their thinking_effort must still apply."""
        options = _options(tmp_path, model="claude-opus-5-5", thinking_effort="high")
        assert options.effort == "high"
        assert options.thinking is None

    def test_max_effort_kept_on_opus_5_5(self, tmp_path: Path) -> None:
        options = _options(tmp_path, model="claude-opus-5-5", thinking_effort="max")
        assert options.effort == "max"

    def test_no_effort_when_unconfigured(self, tmp_path: Path) -> None:
        options = _options(tmp_path, model="claude-opus-5-5")
        assert options.effort is None

    def test_thinking_true_sets_adaptive(self, tmp_path: Path) -> None:
        options = _options(tmp_path, model="claude-sonnet-5-5", thinking=True, thinking_effort="medium")
        assert options.thinking == {"type": "adaptive"}
        assert options.effort == "medium"

    @pytest.mark.parametrize("model", ["claude-opus-5-5", "claude-haiku-4-5"])
    def test_thinking_false_sends_nothing(self, tmp_path: Path, model: str) -> None:
        options = _options(tmp_path, model=model, thinking=False, thinking_effort="high")
        assert options.effort is None
        assert options.thinking is None

    def test_non_adaptive_model_ignores_effort(self, tmp_path: Path) -> None:
        options = _options(tmp_path, model="claude-haiku-4-5", thinking_effort="high")
        assert options.effort is None
