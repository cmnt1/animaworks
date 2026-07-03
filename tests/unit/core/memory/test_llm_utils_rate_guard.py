# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Integration tests for the rate-guard wiring in one_shot_completion()."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import core.memory._llm_utils as llm_utils
from core.config.schemas import LlmRateGuardConfig
from core.execution.rate_guard import LlmRateGuard

pytestmark = pytest.mark.asyncio


class _ApiError(Exception):
    def __init__(self, message: str = "", *, status_code: int | None = None) -> None:
        super().__init__(message)
        if status_code is not None:
            self.status_code = status_code


def _make_guard(tmp_path: Path, **cfg) -> LlmRateGuard:
    return LlmRateGuard(config=LlmRateGuardConfig(**cfg), path=tmp_path / "guard.json")


@pytest.fixture(autouse=True)
def _no_backoff_sleep():
    """Skip the real backoff sleep so rate-limit retries run instantly."""
    with patch("core.memory._llm_utils.asyncio.sleep", new=AsyncMock()):
        yield


async def test_content_policy_returns_none_without_fallback(tmp_path: Path) -> None:
    guard = _make_guard(tmp_path)
    with (
        patch("core.memory._llm_utils.get_llm_kwargs_for_model", return_value={"model": "anthropic/claude-sonnet-4-6"}),
        patch("core.memory._llm_utils._try_litellm", side_effect=_ApiError("violates our usage policies", status_code=400)),
        patch("core.memory._llm_utils._try_agent_sdk", new=AsyncMock(return_value="sdk")) as mock_sdk,
        patch("core.execution.rate_guard.get_rate_guard", return_value=guard),
    ):
        result = await llm_utils.one_shot_completion("hi", model="anthropic/claude-sonnet-4-6")

    assert result is None
    mock_sdk.assert_not_called()


async def test_rate_limit_reports_guard_and_continues_to_fallback(tmp_path: Path) -> None:
    guard = _make_guard(tmp_path)
    mock_litellm = AsyncMock(side_effect=_ApiError("Too Many Requests", status_code=429))
    with (
        patch("core.memory._llm_utils.get_llm_kwargs_for_model", return_value={"model": "anthropic/claude-sonnet-4-6"}),
        patch("core.memory._llm_utils._try_litellm", new=mock_litellm),
        patch("core.memory._llm_utils._try_agent_sdk", new=AsyncMock(return_value="sdk")) as mock_sdk,
        patch("core.execution.rate_guard.get_rate_guard", return_value=guard),
    ):
        result = await llm_utils.one_shot_completion("hi", model="anthropic/claude-sonnet-4-6")

    assert result == "sdk"
    mock_sdk.assert_called_once()
    # Initial attempt + one backoff retry.
    assert mock_litellm.await_count == 2
    # The 429 was reported to the guard.
    assert guard.blocked_remaining("anthropic") > 0


async def test_second_process_skips_litellm_when_guarded(tmp_path: Path) -> None:
    guard = _make_guard(tmp_path)
    guard.report_block("anthropic", 300, "rate_limit")  # a peer process already recorded it
    mock_litellm = AsyncMock(return_value="should-not-run")
    with (
        patch("core.memory._llm_utils.get_llm_kwargs_for_model", return_value={"model": "anthropic/claude-sonnet-4-6"}),
        patch("core.memory._llm_utils._try_litellm", new=mock_litellm),
        patch("core.memory._llm_utils._try_agent_sdk", new=AsyncMock(return_value="sdk")) as mock_sdk,
        patch("core.execution.rate_guard.get_rate_guard", return_value=guard),
    ):
        result = await llm_utils.one_shot_completion("hi", model="anthropic/claude-sonnet-4-6")

    assert result == "sdk"
    mock_litellm.assert_not_called()
    mock_sdk.assert_called_once()


async def test_disabled_guard_does_not_record_block(tmp_path: Path) -> None:
    guard = _make_guard(tmp_path, enabled=False)
    with (
        patch("core.memory._llm_utils.get_llm_kwargs_for_model", return_value={"model": "anthropic/claude-sonnet-4-6"}),
        patch("core.memory._llm_utils._try_litellm", new=AsyncMock(side_effect=_ApiError("rate limit", status_code=429))),
        patch("core.memory._llm_utils._try_agent_sdk", new=AsyncMock(return_value="sdk")) as mock_sdk,
        patch("core.execution.rate_guard.get_rate_guard", return_value=guard),
    ):
        result = await llm_utils.one_shot_completion("hi", model="anthropic/claude-sonnet-4-6")

    assert result == "sdk"
    mock_sdk.assert_called_once()
    assert guard.blocked_remaining("anthropic") == 0.0
    assert not (tmp_path / "guard.json").exists()


async def test_unknown_error_degrades_to_current_fallback(tmp_path: Path) -> None:
    guard = _make_guard(tmp_path)
    mock_litellm = AsyncMock(side_effect=RuntimeError("weird"))
    with (
        patch("core.memory._llm_utils.get_llm_kwargs_for_model", return_value={"model": "anthropic/claude-sonnet-4-6"}),
        patch("core.memory._llm_utils._try_litellm", new=mock_litellm),
        patch("core.memory._llm_utils._try_agent_sdk", new=AsyncMock(return_value="sdk")) as mock_sdk,
        patch("core.execution.rate_guard.get_rate_guard", return_value=guard),
    ):
        result = await llm_utils.one_shot_completion("hi", model="anthropic/claude-sonnet-4-6")

    assert result == "sdk"
    # No same-backend retry for unknown; single attempt then fallback.
    assert mock_litellm.await_count == 1
    mock_sdk.assert_called_once()
    assert guard.blocked_remaining("anthropic") == 0.0
