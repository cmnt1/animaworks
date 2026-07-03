"""Fault-injection tests for Mode B loop guards (retry / empty / runaway)."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio

from core.execution.reminder import (
    msg_empty_response,
    msg_tool_loop_halt,
    msg_tool_loop_warning,
)
from core.schemas import ModelConfig
from core.tooling.handler import ToolHandler
from tests.helpers.mocks import make_litellm_response, patch_litellm


class _RateLimitError(Exception):
    status_code = 429


_TOOL_CALL_TEXT = '```json\n{"tool": "search_memory", "arguments": {"query": "same"}}\n```'


def _tool_resp():
    return make_litellm_response(content=_TOOL_CALL_TEXT, tool_calls=None)


@pytest.fixture(autouse=True)
def _fast_backoff():
    with patch("core.execution.assisted.decorrelated_jitter", return_value=0.0):
        yield


@pytest.fixture(autouse=True)
def _mock_rate_guard():
    guard = MagicMock()
    guard.config.default_block_seconds = 60
    with patch("core.execution.assisted.get_rate_guard", return_value=guard):
        yield guard


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "animas" / "test-b"
    for sub in ("state", "episodes", "knowledge", "procedures", "skills", "shortterm"):
        (d / sub).mkdir(parents=True)
    (d / "identity.md").write_text("# Test", encoding="utf-8")
    (d / "permissions.md").write_text("", encoding="utf-8")
    return d


@pytest.fixture
def executor(anima_dir: Path):
    from core.execution.assisted import AssistedExecutor
    from core.memory import MemoryManager

    memory = MagicMock(spec=MemoryManager)
    memory.read_permissions.return_value = ""
    memory.search_memory_text.return_value = []
    memory.anima_dir = anima_dir
    tool_handler = ToolHandler(anima_dir=anima_dir, memory=memory, tool_registry=[])
    model_config = ModelConfig(
        model="openai/gpt-4o",
        api_key="sk-test",
        max_tokens=1024,
        max_turns=8,
        context_threshold=0.50,
        max_chains=2,
    )
    ex = AssistedExecutor(
        model_config=model_config,
        anima_dir=anima_dir,
        tool_handler=tool_handler,
        memory=memory,
    )
    # Deterministic tool results without touching real memory search
    ex._tool_handler = MagicMock()
    ex._tool_handler.handle.return_value = "tool result"
    return ex


def _messages_of_call(mock: AsyncMock, index: int) -> list[dict]:
    return mock.call_args_list[index].kwargs["messages"]


# ── In-loop retry ────────────────────────────────────────────


class TestModeBRetry:
    async def test_transient_error_retried_and_work_preserved(self, executor):
        final = make_litellm_response(content="Final answer", tool_calls=None)
        with patch_litellm() as mock:
            mock.side_effect = [
                _tool_resp(),
                _RateLimitError("too many requests"),
                final,
            ]
            result = await executor.execute("test prompt", system_prompt="sys")
        assert mock.call_count == 3
        assert "Final answer" in result.text
        assert len(result.tool_call_records) == 1

    async def test_rate_error_reports_to_guard(self, executor, _mock_rate_guard):
        final = make_litellm_response(content="ok", tool_calls=None)
        with patch_litellm() as mock:
            mock.side_effect = [_RateLimitError("too many requests"), final]
            result = await executor.execute("test", system_prompt="sys")
        assert "ok" in result.text
        _mock_rate_guard.report_block.assert_called_once()

    async def test_inner_litellm_retries_disabled(self, executor):
        """num_retries=0 on wrapped calls — in-loop retry is the single authority."""
        final = make_litellm_response(content="ok", tool_calls=None)
        with patch_litellm() as mock:
            mock.side_effect = [final]
            await executor.execute("test", system_prompt="sys")
        assert mock.call_args_list[0].kwargs.get("num_retries") == 0


# ── Empty-response recovery (shared with intent reprompts) ───


class TestModeBEmptyResponse:
    async def test_reprompts_then_gives_up(self, executor):
        empty = make_litellm_response(content="", tool_calls=None)
        with patch_litellm() as mock:
            mock.side_effect = [empty, empty, empty]
            result = await executor.execute("test", system_prompt="sys")
        assert mock.call_count == 3
        assert result.text == "(empty response)"
        assert result.truncated is True

    async def test_recovers_after_reprompt(self, executor):
        empty = make_litellm_response(content="", tool_calls=None)
        final = make_litellm_response(content="Recovered", tool_calls=None)
        with patch_litellm() as mock:
            mock.side_effect = [empty, final]
            result = await executor.execute("test", system_prompt="sys")
        assert mock.call_count == 2
        assert "Recovered" in result.text
        reprompt = msg_empty_response()
        assert any(
            m.get("role") == "user" and reprompt in str(m.get("content"))
            for m in _messages_of_call(mock, 1)
        )

    async def test_empty_and_intent_share_budget(self, executor):
        """One empty + one intent reprompt exhaust the shared budget of 2."""
        empty = make_litellm_response(content="", tool_calls=None)
        intent = make_litellm_response(content="では、記憶を調べてみます。", tool_calls=None)
        with patch_litellm() as mock:
            mock.side_effect = [empty, intent, empty]
            result = await executor.execute("test", system_prompt="sys")
        assert mock.call_count == 3
        assert result.truncated is True

    async def test_intent_only_behavior_unchanged(self, executor):
        """Pre-existing intent reprompt still works for non-empty intent text."""
        intent = make_litellm_response(content="では、記憶を調べてみます。", tool_calls=None)
        final = make_litellm_response(content="調査結果はこちらです。", tool_calls=None)
        with patch_litellm() as mock:
            mock.side_effect = [intent, final]
            result = await executor.execute("test", system_prompt="sys")
        assert mock.call_count == 2
        assert "調査結果" in result.text
        assert result.truncated is False


# ── Runaway guard ────────────────────────────────────────────


class TestModeBRunawayGuard:
    async def test_warn_reminder_at_three_consecutive(self, executor):
        final = make_litellm_response(content="Done", tool_calls=None)
        with patch_litellm() as mock:
            mock.side_effect = [_tool_resp(), _tool_resp(), _tool_resp(), final]
            result = await executor.execute("test", system_prompt="sys")
        assert "Done" in result.text
        warning = msg_tool_loop_warning(tool_names="search_memory", count=3)
        assert any(
            warning in str(m.get("content"))
            for m in _messages_of_call(mock, 3)
        )

    async def test_halt_at_five_consecutive(self, executor):
        final = make_litellm_response(content="Summary of work", tool_calls=None)
        with patch_litellm() as mock:
            mock.side_effect = [_tool_resp() for _ in range(5)] + [final]
            result = await executor.execute("test", system_prompt="sys")
        assert mock.call_count == 6
        assert "Summary of work" in result.text
        halt_msg = msg_tool_loop_halt(count=5)
        assert any(
            halt_msg in str(m.get("content"))
            for m in _messages_of_call(mock, 5)
        )
        # 5th identical call was blocked — only 4 executions
        assert executor._tool_handler.handle.call_count == 4

    async def test_tool_call_after_halt_finalizes_truncated(self, executor):
        with patch_litellm() as mock:
            mock.side_effect = [_tool_resp() for _ in range(6)]
            result = await executor.execute("test", system_prompt="sys")
        assert mock.call_count == 6
        assert result.truncated is True
        assert executor._tool_handler.handle.call_count == 4

    async def test_varied_calls_do_not_trigger_guard(self, executor):
        def _varied(i: int):
            text = f'```json\n{{"tool": "search_memory", "arguments": {{"query": "q{i}"}}}}\n```'
            return make_litellm_response(content=text, tool_calls=None)

        final = make_litellm_response(content="Done", tool_calls=None)
        with patch_litellm() as mock:
            mock.side_effect = [_varied(i) for i in range(5)] + [final]
            result = await executor.execute("test", system_prompt="sys")
        assert "Done" in result.text
        assert executor._tool_handler.handle.call_count == 5
