"""Unit tests for LiteLLM one-shot compaction (Mode A context overflow)."""

from __future__ import annotations

import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ── Fixtures ──────────────────────────────────────────────────


def _make_mixin():
    """Create a ContextMixin instance with required attributes."""
    from core.execution.engines.litellm._litellm_context import ContextMixin

    mixin = ContextMixin()
    mixin._model_config = types.SimpleNamespace(model="openai/gpt-4o")
    return mixin


# ── _try_compact_messages ──────────────────────────────────────


class TestTryCompactMessages:
    """Tests for _try_compact_messages."""

    async def test_returns_false_when_leq_3_messages(self) -> None:
        """_try_compact_messages returns False when <= 3 messages."""
        mixin = _make_mixin()
        mixin._resolve_cw = lambda: 32_000

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        litellm = MagicMock()

        result = await mixin._try_compact_messages(messages, {}, litellm)
        assert result is False
        litellm.acompletion.assert_not_called()

    async def test_returns_false_when_cw_lt_16k(self) -> None:
        """_try_compact_messages returns False when context window < 16K."""
        mixin = _make_mixin()
        mixin._resolve_cw = lambda: 8_000

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "more"},
        ]
        litellm = MagicMock()

        result = await mixin._try_compact_messages(messages, {}, litellm)
        assert result is False
        litellm.acompletion.assert_not_called()

    async def test_compacts_messages_when_gt_3_and_cw_ge_16k(self) -> None:
        """_try_compact_messages compacts when > 3 messages and CW >= 16K."""
        mixin = _make_mixin()
        mixin._resolve_cw = lambda: 32_000

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "original"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "follow-up"},
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary of the conversation."

        litellm = MagicMock()
        litellm.acompletion = AsyncMock(return_value=mock_response)

        result = await mixin._try_compact_messages(messages, {"max_tokens": 4096}, litellm)

        assert result is True
        litellm.acompletion.assert_called_once()
        # messages[2:] replaced with summary
        assert len(messages) == 3
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "original"
        assert messages[2]["role"] == "user"
        assert "[Previous work summary]" in messages[2]["content"] or "[前回の作業要約]" in messages[2]["content"]
        assert "Summary of the conversation." in messages[2]["content"]

    async def test_handles_llm_call_failure_gracefully(self) -> None:
        """_try_compact_messages returns False when LLM call fails."""
        mixin = _make_mixin()
        mixin._resolve_cw = lambda: 32_000

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "original"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "more"},
        ]

        litellm = MagicMock()
        litellm.acompletion = AsyncMock(side_effect=RuntimeError("API error"))

        result = await mixin._try_compact_messages(messages, {}, litellm)

        assert result is False
        # messages unchanged
        assert len(messages) == 4

    async def test_returns_false_when_summary_empty(self) -> None:
        """_try_compact_messages returns False when LLM returns empty summary."""
        mixin = _make_mixin()
        mixin._resolve_cw = lambda: 32_000

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "original"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "more"},
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = ""

        litellm = MagicMock()
        litellm.acompletion = AsyncMock(return_value=mock_response)

        result = await mixin._try_compact_messages(messages, {}, litellm)

        assert result is False
        assert len(messages) == 4


# ── _preflight_clamp_with_compaction ──────────────────────────


class TestPreflightClampWithCompaction:
    """Tests for _preflight_clamp_with_compaction."""

    async def test_returns_result_when_preflight_succeeds(self) -> None:
        """_preflight_clamp_with_compaction returns result when preflight succeeds."""
        mixin = _make_mixin()
        mixin._resolve_cw = lambda: 128_000

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        tools = []
        llm_kwargs = {"max_tokens": 4096}
        litellm = MagicMock()
        litellm.token_counter = lambda **kw: 1000

        with patch.object(mixin, "_preflight_clamp", return_value={"max_tokens": 4096}):
            result = await mixin._preflight_clamp_with_compaction(llm_kwargs, messages, tools, litellm)

        assert result == {"max_tokens": 4096}

    async def test_retries_after_successful_compaction(self) -> None:
        """_preflight_clamp_with_compaction retries preflight after compaction."""
        mixin = _make_mixin()
        mixin._resolve_cw = lambda: 32_000

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "original"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "more"},
        ]
        tools = []
        llm_kwargs = {"max_tokens": 4096}
        litellm = MagicMock()
        litellm.token_counter = lambda **kw: 50_000  # over limit
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Compacted summary."
        litellm.acompletion = AsyncMock(return_value=mock_response)

        preflight_calls = []

        def track_preflight(*args, **kwargs):
            preflight_calls.append(1)
            if len(preflight_calls) == 1:
                return None  # first call: too large
            return {"max_tokens": 2048}  # second call: success after compaction

        with patch.object(mixin, "_preflight_clamp", side_effect=track_preflight):
            result = await mixin._preflight_clamp_with_compaction(llm_kwargs, messages, tools, litellm)

        assert result == {"max_tokens": 2048}
        assert len(preflight_calls) == 2
        assert len(messages) == 3

    async def test_returns_none_when_compaction_fails(self) -> None:
        """_preflight_clamp_with_compaction returns None when compaction fails."""
        mixin = _make_mixin()
        mixin._resolve_cw = lambda: 32_000

        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "original"},
            {"role": "assistant", "content": "reply"},
            {"role": "user", "content": "more"},
        ]
        tools = []
        llm_kwargs = {"max_tokens": 4096}
        litellm = MagicMock()
        litellm.token_counter = lambda **kw: 50_000
        litellm.acompletion = AsyncMock(side_effect=RuntimeError("API error"))

        with patch.object(mixin, "_preflight_clamp", return_value=None):
            result = await mixin._preflight_clamp_with_compaction(llm_kwargs, messages, tools, litellm)

        assert result is None

    async def test_messages_correctly_reset_after_compaction(self) -> None:
        """Messages are correctly reset: system + original user + summary."""
        mixin = _make_mixin()
        mixin._resolve_cw = lambda: 32_000

        messages = [
            {"role": "system", "content": "System prompt here"},
            {"role": "user", "content": "Original user message"},
            {"role": "assistant", "content": "A1", "tool_calls": []},
            {"role": "tool", "content": "Tool result"},
            {"role": "user", "content": "Follow-up"},
        ]

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Key findings: X. Pending: Y."

        litellm = MagicMock()
        litellm.acompletion = AsyncMock(return_value=mock_response)

        result = await mixin._try_compact_messages(messages, {}, litellm)

        assert result is True
        assert len(messages) == 3
        assert messages[0] == {"role": "system", "content": "System prompt here"}
        assert messages[1] == {"role": "user", "content": "Original user message"}
        assert messages[2]["role"] == "user"
        assert "Key findings: X. Pending: Y." in messages[2]["content"]
