# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for num_retries propagation to LiteLLM kwargs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

# ── _build_llm_kwargs num_retries propagation ─────────────────


def _make_context_mixin():
    """Create a minimal ContextMixin instance for testing."""
    from core.execution.engines.litellm._litellm_context import ContextMixin

    class FakeExecutor(ContextMixin):
        def __init__(self):
            self._model_config = MagicMock()
            self._model_config.model = "openai/gpt-4o"
            self._model_config.max_tokens = 4096
            self._model_config.thinking = None
            self._model_config.api_base_url = None
            self._model_config.credential = None
            self._model_config.thinking_effort = None

        def _resolve_api_key(self):
            return None

        def _resolve_num_retries(self):
            return 5

        def _apply_provider_kwargs(self, kwargs):
            pass

    return FakeExecutor()


def test_build_llm_kwargs_includes_num_retries():
    """_build_llm_kwargs() should include the num_retries key."""
    executor = _make_context_mixin()
    kwargs = executor._build_llm_kwargs()
    assert "num_retries" in kwargs
    assert kwargs["num_retries"] == 5


# ── _resolve_num_retries on BaseExecutor ──────────────────────


def test_resolve_num_retries_from_config():
    """_resolve_num_retries reads from config.server.llm_num_retries."""
    from core.execution.base import BaseExecutor

    mock_config = MagicMock()
    mock_config.server.llm_num_retries = 7

    model_config = MagicMock()
    model_config.model = "claude-sonnet-4-6"

    with (
        patch("core.config.load_config", return_value=mock_config),
        patch.multiple(BaseExecutor, __abstractmethods__=frozenset()),
    ):
        executor = BaseExecutor.__new__(BaseExecutor)
        executor._model_config = model_config
        executor._anima_dir = Path("/tmp/test")
        assert executor._resolve_num_retries() == 7


def test_resolve_num_retries_default_on_error():
    """_resolve_num_retries falls back to 3 when config loading fails."""
    from core.execution.base import BaseExecutor

    model_config = MagicMock()
    model_config.model = "claude-sonnet-4-6"

    with (
        patch("core.config.load_config", side_effect=RuntimeError("no config")),
        patch.multiple(BaseExecutor, __abstractmethods__=frozenset()),
    ):
        executor = BaseExecutor.__new__(BaseExecutor)
        executor._model_config = model_config
        executor._anima_dir = Path("/tmp/test")
        assert executor._resolve_num_retries() == 3


# ── ServerConfig.llm_num_retries ──────────────────────────────


def test_server_config_llm_num_retries_default():
    from core.config.models import ServerConfig

    cfg = ServerConfig()
    assert cfg.llm_num_retries == 3


def test_server_config_llm_num_retries_custom():
    from core.config.models import ServerConfig

    cfg = ServerConfig(llm_num_retries=10)
    assert cfg.llm_num_retries == 10
