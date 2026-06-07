"""Tests for agent.py retry logic: fresh session forced on retry_count == 1.

Verifies that:
  - retry_count == 1: _clear_session_id("chat") is called
  - retry_count == 2: _clear_session_id is NOT called again (only first retry)
  - The retry emits a retry_start event
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.execution.base import StreamDisconnectedError
from core.prompt.builder import BuildResult
from core.provider_cooldown import get_provider_cooldown, record_provider_rate_limit
from core.schemas import ModelConfig

# ── Helpers ───────────────────────────────────────────────────


def _make_agent(anima_dir: Path, model: str = "claude-sonnet-4-6"):
    """Create AgentCore with all external dependencies mocked."""
    mc = ModelConfig(
        model=model,
        api_key="test-key",
        max_turns=5,
        max_chains=2,
        context_threshold=0.50,
    )
    memory = MagicMock()
    memory.read_permissions.return_value = ""
    memory.anima_dir = anima_dir
    messenger = MagicMock()

    with (
        patch("core.agent.ToolHandler"),
        patch("core.agent.AgentCore._check_sdk", return_value=False),
        patch("core.agent.AgentCore._init_tool_registry", return_value=[]),
        patch("core.agent.AgentCore._discover_personal_tools", return_value={}),
        patch("core.agent.AgentCore._create_executor") as mock_create,
    ):
        mock_executor = MagicMock()
        mock_create.return_value = mock_executor
        from core.agent import AgentCore

        agent = AgentCore(anima_dir, memory, mc, messenger)
        agent._executor = mock_executor
    return agent


def _build_result_mock() -> MagicMock:
    """Build a mock BuildResult for build_system_prompt."""
    result = MagicMock(spec=BuildResult)
    result.system_prompt = "mocked system prompt"
    result.priming_section = ""
    return result


def _common_patches(*, spy_clear=None, retry_max=2):
    """Return the common patch context manager args for run_cycle_streaming tests."""
    clear_side_effect = spy_clear if spy_clear is not None else MagicMock()
    return [
        patch("core._agent_cycle.build_system_prompt", return_value=_build_result_mock()),
        patch("core._agent_cycle.inject_shortterm", side_effect=lambda sp, _stm: sp),
        patch("core.agent.AgentCore._resolve_execution_mode", return_value="s"),
        patch("core.agent.AgentCore._preflight_size_check"),
        patch("core.agent.AgentCore._load_stream_retry_config"),
        patch("core._agent_cycle._save_prompt_log"),
        patch("core.execution._sdk_session._clear_session_id", side_effect=clear_side_effect),
        patch("core.agent.AgentCore._run_priming", new_callable=AsyncMock, return_value=("", "")),
    ]


# ── retry_count == 1 clears session ID ───────────────────────


class TestRetryFreshSession:
    """On retry_count == 1, _clear_session_id('chat') is called exactly once."""

    @pytest.mark.asyncio
    async def test_clear_session_id_called_on_first_retry(self, tmp_path: Path) -> None:
        """retry_count == 1: _clear_session_id('chat') is called."""
        agent = _make_agent(tmp_path)

        # Track _clear_session_id calls
        clear_calls: list[tuple[Path, str]] = []

        def _spy_clear(anima_dir_arg, session_type, thread_id="default"):
            clear_calls.append((anima_dir_arg, session_type))

        # The executor will: first call → StreamDisconnectedError,
        # second call (retry) → yield a "done" event.
        call_count = [0]

        async def _executor_stream(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise StreamDisconnectedError("first attempt failed", partial_text="")
            # Second call succeeds
            yield {
                "type": "done",
                "full_text": "retry response",
                "result_message": None,
                "replied_to_from_transcript": set(),
                "tool_call_records": [],
                "force_chain": False,
            }

        agent._executor.execute_streaming = _executor_stream
        agent._executor.supports_streaming = True

        with (
            patch("core._agent_cycle.build_system_prompt", return_value=_build_result_mock()),
            patch("core._agent_cycle.inject_shortterm", side_effect=lambda sp, _stm: sp),
            patch("core.agent.AgentCore._resolve_execution_mode", return_value="s"),
            patch("core.agent.AgentCore._preflight_size_check") as mock_preflight,
            patch("core.agent.AgentCore._load_stream_retry_config") as mock_retry_cfg,
            patch("core._agent_cycle._save_prompt_log"),
            patch("core.execution._sdk_session._clear_session_id", side_effect=_spy_clear),
            patch("core.agent.AgentCore._run_priming", new_callable=AsyncMock) as mock_priming,
        ):
            mock_preflight.return_value = ("mocked system prompt", "test prompt", False)
            mock_retry_cfg.return_value = {
                "checkpoint_enabled": False,
                "retry_max": 2,
                "retry_delay_s": 0.0,
            }
            mock_priming.return_value = ("", "")

            events = []
            async for event in agent.run_cycle_streaming(
                "test prompt",
                trigger="chat",
            ):
                events.append(event)

        # _clear_session_id should have been called with "chat"
        chat_clears = [st for _, st in clear_calls if st == "chat"]
        assert len(chat_clears) >= 1, (
            f"Expected _clear_session_id('chat') to be called on retry_count==1, but clear_calls = {clear_calls}"
        )

    @pytest.mark.asyncio
    async def test_retry_start_event_emitted(self, tmp_path: Path) -> None:
        """retry_start event is emitted with correct retry count."""
        agent = _make_agent(tmp_path)

        call_count = [0]

        async def _executor_stream(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise StreamDisconnectedError("first failure")
            yield {
                "type": "done",
                "full_text": "retry ok",
                "result_message": None,
                "replied_to_from_transcript": set(),
                "tool_call_records": [],
                "force_chain": False,
            }

        agent._executor.execute_streaming = _executor_stream
        agent._executor.supports_streaming = True

        with (
            patch("core._agent_cycle.build_system_prompt", return_value=_build_result_mock()),
            patch("core._agent_cycle.inject_shortterm", side_effect=lambda sp, _stm: sp),
            patch("core.agent.AgentCore._resolve_execution_mode", return_value="s"),
            patch("core.agent.AgentCore._preflight_size_check") as mock_preflight,
            patch("core.agent.AgentCore._load_stream_retry_config") as mock_retry_cfg,
            patch("core._agent_cycle._save_prompt_log"),
            patch("core.execution._sdk_session._clear_session_id"),
            patch("core.agent.AgentCore._run_priming", new_callable=AsyncMock) as mock_priming,
        ):
            mock_preflight.return_value = ("mocked system prompt", "test prompt", False)
            mock_retry_cfg.return_value = {
                "checkpoint_enabled": False,
                "retry_max": 2,
                "retry_delay_s": 0.0,
            }
            mock_priming.return_value = ("", "")

            events = []
            async for event in agent.run_cycle_streaming(
                "test prompt",
                trigger="chat",
            ):
                events.append(event)

        retry_events = [e for e in events if e.get("type") == "retry_start"]
        assert len(retry_events) >= 1, f"Expected retry_start event, got event types: {[e.get('type') for e in events]}"
        assert retry_events[0]["retry"] == 1

    @pytest.mark.asyncio
    async def test_retry_uses_provider_retry_after_delay(self, tmp_path: Path) -> None:
        """Provider-advised retry_after_s overrides the fixed retry delay."""
        agent = _make_agent(tmp_path)

        call_count = [0]

        async def _executor_stream(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise StreamDisconnectedError("rate limited", retry_after_s=52.0)
            yield {
                "type": "done",
                "full_text": "retry ok",
                "result_message": None,
                "replied_to_from_transcript": set(),
                "tool_call_records": [],
                "force_chain": False,
            }

        agent._executor.execute_streaming = _executor_stream
        agent._executor.supports_streaming = True

        with (
            patch("core._agent_cycle.build_system_prompt", return_value=_build_result_mock()),
            patch("core._agent_cycle.inject_shortterm", side_effect=lambda sp, _stm: sp),
            patch("core.agent.AgentCore._resolve_execution_mode", return_value="s"),
            patch("core.agent.AgentCore._preflight_size_check") as mock_preflight,
            patch("core.agent.AgentCore._load_stream_retry_config") as mock_retry_cfg,
            patch("core._agent_cycle._save_prompt_log"),
            patch("core.execution._sdk_session._clear_session_id"),
            patch("core.agent.AgentCore._run_priming", new_callable=AsyncMock) as mock_priming,
            patch("core.agent.AgentCore._compute_overflow_files", return_value=[]),
            patch("core._agent_cycle.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_preflight.return_value = ("mocked system prompt", "test prompt", False)
            mock_retry_cfg.return_value = {
                "checkpoint_enabled": False,
                "retry_max": 2,
                "retry_delay_s": 5.0,
            }
            mock_priming.return_value = ("", "")

            events = []
            async for event in agent.run_cycle_streaming(
                "test prompt",
                trigger="chat",
            ):
                events.append(event)

        mock_sleep.assert_awaited_once_with(53.0)
        retry_events = [e for e in events if e.get("type") == "retry_start"]
        assert retry_events[0]["delay_s"] == 53.0
        assert retry_events[0]["retry_after_s"] == 52.0

    @pytest.mark.asyncio
    async def test_rate_limit_sets_provider_cooldown_without_retry_loop(self, tmp_path: Path, monkeypatch) -> None:
        """HTTP 429 should defer the provider instead of burning all stream retries."""
        monkeypatch.setenv("ANIMAWORKS_PROVIDER_COOLDOWN_FILE", str(tmp_path / "provider_cooldowns.json"))
        agent = _make_agent(tmp_path, model="antigravity/gemini-2.5-flash")

        async def _executor_stream(*args, **kwargs):
            raise StreamDisconnectedError(
                "Antigravity provider rate limit (HTTP 429/RATE_LIMIT_EXCEEDED)",
                retry_after_s=52.0,
                category="rate_limit",
            )
            yield  # pragma: no cover

        agent._executor.execute_streaming = _executor_stream
        agent._executor.supports_streaming = True

        with (
            patch("core._agent_cycle.build_system_prompt", return_value=_build_result_mock()),
            patch("core._agent_cycle.inject_shortterm", side_effect=lambda sp, _stm: sp),
            patch("core.agent.AgentCore._resolve_execution_mode", return_value="a"),
            patch("core.agent.AgentCore._preflight_size_check") as mock_preflight,
            patch("core.agent.AgentCore._load_stream_retry_config") as mock_retry_cfg,
            patch("core._agent_cycle._save_prompt_log"),
            patch("core.agent.AgentCore._run_priming", new_callable=AsyncMock) as mock_priming,
            patch("core.agent.AgentCore._compute_overflow_files", return_value=[]),
            patch("core._agent_cycle.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
        ):
            mock_preflight.return_value = ("mocked system prompt", "test prompt", False)
            mock_retry_cfg.return_value = {
                "checkpoint_enabled": False,
                "retry_max": 5,
                "retry_delay_s": 5.0,
            }
            mock_priming.return_value = ("", "")

            events = []
            async for event in agent.run_cycle_streaming("test prompt", trigger="heartbeat"):
                events.append(event)

        assert not [e for e in events if e.get("type") == "retry_start"]
        mock_sleep.assert_not_awaited()
        error_msg = [e["message"] for e in events if e.get("type") == "error"][0]
        assert error_msg.startswith("RATE_LIMIT_DEFERRED:")
        assert get_provider_cooldown("gemini") is not None

    @pytest.mark.asyncio
    async def test_provider_cooldown_preflight_skips_executor(self, tmp_path: Path, monkeypatch) -> None:
        """A live provider cooldown should stop before any executor stream call."""
        monkeypatch.setenv("ANIMAWORKS_PROVIDER_COOLDOWN_FILE", str(tmp_path / "provider_cooldowns.json"))
        record_provider_rate_limit(
            "gemini",
            retry_after_s=52.0,
            trigger="heartbeat",
            model="antigravity/gemini-2.5-flash",
        )
        agent = _make_agent(tmp_path, model="antigravity/gemini-2.5-flash")
        agent._executor.execute_streaming = AsyncMock()
        agent._executor.supports_streaming = True

        events = []
        async for event in agent.run_cycle_streaming("test prompt", trigger="heartbeat"):
            events.append(event)

        agent._executor.execute_streaming.assert_not_called()
        error_msg = [e["message"] for e in events if e.get("type") == "error"][0]
        assert error_msg.startswith("RATE_LIMIT_DEFERRED:")
        done = [e for e in events if e.get("type") == "cycle_done"][0]
        assert done["cycle_result"]["action"] == "error"

    @pytest.mark.asyncio
    async def test_provider_cooldown_preflight_skips_blocking_executor(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A live provider cooldown should also stop blocking run_cycle calls."""
        monkeypatch.setenv("ANIMAWORKS_PROVIDER_COOLDOWN_FILE", str(tmp_path / "provider_cooldowns.json"))
        record_provider_rate_limit(
            "gemini",
            retry_after_s=52.0,
            trigger="heartbeat",
            model="antigravity/gemini-2.5-flash",
        )
        agent = _make_agent(tmp_path, model="antigravity/gemini-2.5-flash")
        agent._executor.execute = AsyncMock()

        with patch("core.agent.AgentCore._run_priming", new_callable=AsyncMock) as mock_priming:
            result = await agent.run_cycle("test prompt", trigger="bootstrap")

        agent._executor.execute.assert_not_called()
        mock_priming.assert_not_awaited()
        assert result.action == "error"
        assert result.summary.startswith("RATE_LIMIT_DEFERRED:")

    @pytest.mark.asyncio
    async def test_no_clear_session_id_on_second_retry(self, tmp_path: Path) -> None:
        """retry_count == 2 does NOT call _clear_session_id again."""
        agent = _make_agent(tmp_path)

        clear_calls: list[tuple[Path, str]] = []

        def _spy_clear(anima_dir_arg, session_type, thread_id="default"):
            clear_calls.append((anima_dir_arg, session_type))

        call_count = [0]

        async def _executor_stream(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 2:
                raise StreamDisconnectedError(f"failure #{call_count[0]}", partial_text="")
            # Third call (retry 2) succeeds
            yield {
                "type": "done",
                "full_text": "finally succeeded",
                "result_message": None,
                "replied_to_from_transcript": set(),
                "tool_call_records": [],
                "force_chain": False,
            }

        agent._executor.execute_streaming = _executor_stream
        agent._executor.supports_streaming = True

        with (
            patch("core._agent_cycle.build_system_prompt", return_value=_build_result_mock()),
            patch("core._agent_cycle.inject_shortterm", side_effect=lambda sp, _stm: sp),
            patch("core.agent.AgentCore._resolve_execution_mode", return_value="s"),
            patch("core.agent.AgentCore._preflight_size_check") as mock_preflight,
            patch("core.agent.AgentCore._load_stream_retry_config") as mock_retry_cfg,
            patch("core._agent_cycle._save_prompt_log"),
            patch("core.execution._sdk_session._clear_session_id", side_effect=_spy_clear),
            patch("core.agent.AgentCore._run_priming", new_callable=AsyncMock) as mock_priming,
        ):
            mock_preflight.return_value = ("mocked system prompt", "test prompt", False)
            mock_retry_cfg.return_value = {
                "checkpoint_enabled": False,
                "retry_max": 3,
                "retry_delay_s": 0.0,
            }
            mock_priming.return_value = ("", "")

            events = []
            async for event in agent.run_cycle_streaming(
                "test prompt",
                trigger="chat",
            ):
                events.append(event)

        # _clear_session_id should be called exactly once (only at retry_count == 1)
        chat_clears = [st for _, st in clear_calls if st == "chat"]
        assert len(chat_clears) == 1, (
            "Expected _clear_session_id('chat') to be called exactly once "
            f"(retry_count==1 only), but got {len(chat_clears)} calls"
        )


# ── retry exhausted path ──────────────────────────────────────


class TestRetryExhausted:
    """When retry_count reaches max_retries, an error event is emitted."""

    @pytest.mark.asyncio
    async def test_error_event_on_retry_exhausted(self, tmp_path: Path) -> None:
        """After max_retries failures, an error event with the retry count is emitted."""
        agent = _make_agent(tmp_path)

        async def _always_fail(*args, **kwargs):
            raise StreamDisconnectedError("always fails", partial_text="")
            yield  # pragma: no cover

        agent._executor.execute_streaming = _always_fail
        agent._executor.supports_streaming = True

        with (
            patch("core._agent_cycle.build_system_prompt", return_value=_build_result_mock()),
            patch("core._agent_cycle.inject_shortterm", side_effect=lambda sp, _stm: sp),
            patch("core.agent.AgentCore._resolve_execution_mode", return_value="s"),
            patch("core.agent.AgentCore._preflight_size_check") as mock_preflight,
            patch("core.agent.AgentCore._load_stream_retry_config") as mock_retry_cfg,
            patch("core._agent_cycle._save_prompt_log"),
            patch("core.execution._sdk_session._clear_session_id"),
            patch("core.agent.AgentCore._run_priming", new_callable=AsyncMock) as mock_priming,
        ):
            mock_preflight.return_value = ("mocked system prompt", "test prompt", False)
            mock_retry_cfg.return_value = {
                "checkpoint_enabled": False,
                "retry_max": 1,
                "retry_delay_s": 0.0,
            }
            mock_priming.return_value = ("", "")

            events = []
            async for event in agent.run_cycle_streaming(
                "test prompt",
                trigger="chat",
            ):
                events.append(event)

        error_events = [e for e in events if e.get("type") == "error"]
        assert len(error_events) >= 1, (
            f"Expected error event on retry exhaustion, got: {[e.get('type') for e in events]}"
        )
        # The error message should mention retry count
        error_msg = error_events[0].get("message", "")
        assert "1" in error_msg, f"Expected retry count in error message: {error_msg}"

        done_events = [e for e in events if e.get("type") == "cycle_done"]
        assert len(done_events) == 1
        cycle_result = done_events[0]["cycle_result"]
        assert cycle_result["action"] == "error"
        assert cycle_result["summary"] == error_msg
