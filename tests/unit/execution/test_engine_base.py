from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from core.config.model_config import _guard_key_for_model_config
from core.config.schemas import AnimaWorksConfig
from core.execution.engine_base import engine_error_metadata, engine_guard_key
from core.schemas import ModelConfig


@pytest.mark.parametrize(
    ("mode", "model", "mode_s_auth", "expected"),
    [
        ("S", "claude-sonnet-4-6", "bedrock", "anthropic:bedrock"),
        ("C", "gpt-5.1", None, "openai:codex"),
        ("D", "cursor/claude-4-sonnet", None, "anthropic:cursor"),
        ("G", "gemini/2.5-pro", None, "google:gemini"),
        ("X", "grok/grok-4.5", None, "grok:grok"),
        ("A", "vertex_ai/gemini-2.5-pro", None, "google:vertex"),
    ],
)
def test_engine_guard_key_matches_model_config_resolution(mode, model, mode_s_auth, expected):
    model_config = ModelConfig(
        model=model,
        execution_mode=mode,
        resolved_mode=mode,
        mode_s_auth=mode_s_auth,
    )

    assert engine_guard_key(mode, model, mode_s_auth=mode_s_auth) == expected
    assert _guard_key_for_model_config(model_config, AnimaWorksConfig()) == expected


def test_engine_error_metadata_reports_rate_limit_once_with_mode_guard_key():
    config = SimpleNamespace(default_block_seconds=120, quota_block_seconds=1800)
    guard = SimpleNamespace(config=config, report_block=Mock())

    with patch("core.execution.engine_base.get_rate_guard", return_value=guard):
        metadata = engine_error_metadata(
            "rate limit exceeded",
            mode="G",
            model="gemini/2.5-pro",
            always_terminal=True,
        )

    assert metadata == {"terminal": True, "reason": "rate_limit"}
    guard.report_block.assert_called_once_with("google:gemini", 120, "rate_limit", reset_in_s=None)


def test_engine_error_metadata_uses_quota_block_duration():
    config = SimpleNamespace(default_block_seconds=120, quota_block_seconds=1800)
    guard = SimpleNamespace(config=config, report_block=Mock())

    with patch("core.execution.engine_base.get_rate_guard", return_value=guard):
        metadata = engine_error_metadata(
            "quota exceeded",
            mode="X",
            model="grok/grok-4.5",
            always_terminal=True,
        )

    assert metadata == {"terminal": True, "reason": "quota_exhausted"}
    guard.report_block.assert_called_once_with("grok:grok", 1800, "quota_exhausted", reset_in_s=None)


def test_retryable_codex_error_has_no_terminal_metadata():
    with patch("core.execution.engine_base.get_rate_guard"):
        metadata = engine_error_metadata(
            "rate limit exceeded",
            mode="C",
            model="gpt-5.1",
            always_terminal=False,
        )

    assert metadata == {}


def test_error_metadata_fails_open_if_rate_guard_raises():
    with patch("core.execution.engine_base.get_rate_guard", side_effect=RuntimeError("guard unavailable")):
        metadata = engine_error_metadata(
            "quota exceeded",
            mode="D",
            model="cursor/claude-4-sonnet",
            always_terminal=True,
        )

    assert metadata == {"terminal": True, "reason": "quota_exhausted"}
