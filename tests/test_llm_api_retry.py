# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for LLM API retry — async_retry_with_backoff and num_retries
propagation to LiteLLM kwargs.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.integrations._retry import async_retry_with_backoff

# ── async_retry_with_backoff ──────────────────────────────────


class _TransientError(Exception):
    pass


class _PermanentError(Exception):
    pass


@pytest.mark.asyncio
async def test_async_retry_succeeds_first_attempt():
    fn = AsyncMock(return_value="ok")
    result = await async_retry_with_backoff(
        fn,
        max_retries=3,
        retry_on=(_TransientError,),
    )
    assert result == "ok"
    assert fn.await_count == 1


@pytest.mark.asyncio
async def test_async_retry_succeeds_after_transient_failures():
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise _TransientError("boom")
        return "recovered"

    result = await async_retry_with_backoff(
        flaky,
        max_retries=3,
        base_delay=0.01,
        retry_on=(_TransientError,),
    )
    assert result == "recovered"
    assert call_count == 3


@pytest.mark.asyncio
async def test_async_retry_raises_after_exhaustion():
    fn = AsyncMock(side_effect=_TransientError("always fails"))
    with pytest.raises(_TransientError, match="always fails"):
        await async_retry_with_backoff(
            fn,
            max_retries=2,
            base_delay=0.01,
            retry_on=(_TransientError,),
        )
    assert fn.await_count == 3  # 1 initial + 2 retries


@pytest.mark.asyncio
async def test_async_retry_does_not_catch_unrelated_exceptions():
    fn = AsyncMock(side_effect=_PermanentError("fatal"))
    with pytest.raises(_PermanentError, match="fatal"):
        await async_retry_with_backoff(
            fn,
            max_retries=3,
            base_delay=0.01,
            retry_on=(_TransientError,),
        )
    assert fn.await_count == 1


@pytest.mark.asyncio
async def test_async_retry_zero_retries():
    fn = AsyncMock(side_effect=_TransientError("once"))
    with pytest.raises(_TransientError):
        await async_retry_with_backoff(
            fn,
            max_retries=0,
            retry_on=(_TransientError,),
        )
    assert fn.await_count == 1


@pytest.mark.asyncio
async def test_async_retry_strips_retry_params_from_fn_kwargs():
    """Retry-control kwargs must not leak into the wrapped function."""
    received_kwargs: dict = {}

    async def capture(**kwargs):
        received_kwargs.update(kwargs)
        return "ok"

    result = await async_retry_with_backoff(
        capture,
        max_retries=2,
        base_delay=0.01,
        max_delay=5.0,
        retry_on=(_TransientError,),
        model="test-model",
        temperature=0.7,
    )
    assert result == "ok"
    assert "model" in received_kwargs
    assert "temperature" in received_kwargs
    assert "max_retries" not in received_kwargs
    assert "base_delay" not in received_kwargs
    assert "retry_on" not in received_kwargs


@pytest.mark.asyncio
async def test_async_retry_respects_max_delay():
    delays: list[float] = []
    _orig_sleep = asyncio.sleep

    async def _capture_sleep(t):
        delays.append(t)

    fn = AsyncMock(side_effect=_TransientError("fail"))

    with patch("core.integrations._retry.asyncio.sleep", side_effect=_capture_sleep), pytest.raises(_TransientError):
        await async_retry_with_backoff(
            fn,
            max_retries=5,
            base_delay=1.0,
            max_delay=4.0,
            retry_on=(_TransientError,),
        )

    assert all(d <= 4.0 for d in delays)
    assert len(delays) == 5


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
            self._model_config.llm_timeout = 60
            self._model_config.credential = None
            self._model_config.thinking_effort = None

        def _resolve_api_key(self):
            return None

        def _resolve_llm_timeout(self):
            return 60

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
