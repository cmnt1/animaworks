"""Regression tests for retired execution-mode normalization at agent routing."""

from __future__ import annotations

from unittest.mock import patch

from core.config.schemas import AnimaWorksConfig
from tests.unit.core.test_agent import _make_agent


def test_agent_resolves_retired_b_execution_mode_to_a(tmp_path) -> None:
    agent = _make_agent(tmp_path, execution_mode="B")

    with patch("core.config.io.load_config", return_value=AnimaWorksConfig()):
        assert agent._resolve_execution_mode() == "a"
