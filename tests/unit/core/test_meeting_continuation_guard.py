# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for the meeting continuation guard in run_cycle_streaming.

A meeting turn can end on a bare acknowledgement ("I'll check") because the
Agent SDK closes a turn on any text-only message. The guard re-invokes the model
in the same resumable session, with a nudge, until it signals completion by
emitting MEETING_DONE_SENTINEL or a small retry cap is hit. The sentinel must be
stripped from the visible/saved reply.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.prompt.builder import MEETING_DONE_SENTINEL, PROMPT_PROFILE_MEETING
from core.schemas import ModelConfig


def _make_agent(anima_dir: Path, model: str = "claude-sonnet-4-6"):
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


def _build_result_mock():
    from core.prompt.builder import BuildResult

    result = MagicMock(spec=BuildResult)
    result.system_prompt = "mocked system prompt"
    result.priming_section = ""
    return result


def _done_chunk(full_text: str) -> dict:
    return {
        "type": "done",
        "full_text": full_text,
        "result_message": None,
        "replied_to_from_transcript": set(),
        "tool_call_records": [],
        "force_chain": False,
    }


async def _run(agent, *, trigger: str, prompt_tier_override: str | None):
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
            trigger=trigger,
            prompt_tier_override=prompt_tier_override,
        ):
            events.append(event)
    return events


def _summary(events) -> str:
    done = [e for e in events if e.get("type") == "cycle_done"][0]
    return done["cycle_result"]["summary"]


class TestMeetingContinuationGuard:
    @pytest.mark.asyncio
    async def test_ack_then_stop_triggers_continuation(self, tmp_path: Path) -> None:
        """A bare acknowledgement re-invokes the model until it delivers findings."""
        agent = _make_agent(tmp_path)
        calls = [0]

        async def _stream(*args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                yield _done_chunk("承知しました。確認します。")
            else:
                yield _done_chunk(f"調査結果: ファイルAを確認しました。\n{MEETING_DONE_SENTINEL}")

        agent._executor.execute_streaming = _stream
        agent._executor.supports_streaming = True

        events = await _run(agent, trigger="chat", prompt_tier_override=PROMPT_PROFILE_MEETING)

        assert calls[0] == 2, "expected one continuation re-invocation"
        cont_events = [e for e in events if e.get("type") == "meeting_continue"]
        assert len(cont_events) == 1
        assert cont_events[0]["attempt"] == 1
        summary = _summary(events)
        assert "調査結果" in summary
        assert MEETING_DONE_SENTINEL not in summary

    @pytest.mark.asyncio
    async def test_sentinel_first_turn_no_continuation(self, tmp_path: Path) -> None:
        """If the first turn already has the sentinel, no continuation happens."""
        agent = _make_agent(tmp_path)
        calls = [0]

        async def _stream(*args, **kwargs):
            calls[0] += 1
            yield _done_chunk(f"答えはBです。\n{MEETING_DONE_SENTINEL}")

        agent._executor.execute_streaming = _stream
        agent._executor.supports_streaming = True

        events = await _run(agent, trigger="chat", prompt_tier_override=PROMPT_PROFILE_MEETING)

        assert calls[0] == 1
        assert not [e for e in events if e.get("type") == "meeting_continue"]
        summary = _summary(events)
        assert "答えはB" in summary
        assert MEETING_DONE_SENTINEL not in summary

    @pytest.mark.asyncio
    async def test_continuation_bounded_by_cap(self, tmp_path: Path) -> None:
        """If the model never emits the sentinel, the guard stops at the cap."""
        from core._agent_cycle import _MEETING_CONT_MAX_RETRIES

        agent = _make_agent(tmp_path)
        calls = [0]

        async def _stream(*args, **kwargs):
            calls[0] += 1
            yield _done_chunk("確認します。")

        agent._executor.execute_streaming = _stream
        agent._executor.supports_streaming = True

        events = await _run(agent, trigger="chat", prompt_tier_override=PROMPT_PROFILE_MEETING)

        assert calls[0] == 1 + _MEETING_CONT_MAX_RETRIES
        cont_events = [e for e in events if e.get("type") == "meeting_continue"]
        assert len(cont_events) == _MEETING_CONT_MAX_RETRIES
        # Still produces a final cycle_done (no hang, no crash).
        assert len([e for e in events if e.get("type") == "cycle_done"]) == 1

    @pytest.mark.asyncio
    async def test_non_meeting_turn_no_continuation(self, tmp_path: Path) -> None:
        """Non-meeting turns never trigger the guard, even without a sentinel."""
        agent = _make_agent(tmp_path)
        calls = [0]

        async def _stream(*args, **kwargs):
            calls[0] += 1
            yield _done_chunk("普通の返信です。")

        agent._executor.execute_streaming = _stream
        agent._executor.supports_streaming = True

        events = await _run(agent, trigger="chat", prompt_tier_override=None)

        assert calls[0] == 1
        assert not [e for e in events if e.get("type") == "meeting_continue"]

    @pytest.mark.asyncio
    async def test_no_continuation_past_wall_deadline(self, tmp_path: Path) -> None:
        """If elapsed wall time exceeds the deadline, no continuation is started.

        Guards against blowing the server's fixed per-speaker meeting wall budget.
        """
        agent = _make_agent(tmp_path)
        calls = [0]

        async def _stream(*args, **kwargs):
            calls[0] += 1
            yield _done_chunk("確認します。")

        agent._executor.execute_streaming = _stream
        agent._executor.supports_streaming = True

        # First time.monotonic() call is `start`; everything after reports a time
        # well past the continuation deadline so the guard must not re-invoke.
        ticks = iter([0.0] + [10_000.0] * 50)

        with patch("core._agent_cycle.time.monotonic", side_effect=lambda: next(ticks)):
            events = await _run(agent, trigger="chat", prompt_tier_override=PROMPT_PROFILE_MEETING)

        assert calls[0] == 1, "continuation must not start once past the wall deadline"
        assert not [e for e in events if e.get("type") == "meeting_continue"]

    @pytest.mark.asyncio
    async def test_sentinel_stripped_from_streamed_text_delta(self, tmp_path: Path) -> None:
        """The sentinel is hidden from the live stream even when split across deltas."""
        agent = _make_agent(tmp_path)

        async def _stream(*args, **kwargs):
            yield {"type": "text_delta", "text": "答えはBです。"}
            # Sentinel split across deltas to exercise the carry buffer.
            yield {"type": "text_delta", "text": "[[MTG"}
            yield {"type": "text_delta", "text": "_DONE]]"}
            yield _done_chunk(f"答えはBです。{MEETING_DONE_SENTINEL}")

        agent._executor.execute_streaming = _stream
        agent._executor.supports_streaming = True

        events = await _run(agent, trigger="chat", prompt_tier_override=PROMPT_PROFILE_MEETING)

        streamed = "".join(e.get("text", "") for e in events if e.get("type") == "text_delta")
        assert MEETING_DONE_SENTINEL not in streamed
        assert "答えはB" in streamed
