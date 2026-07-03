"""Tests for core.execution.loop_guards — in-loop guard mechanisms (Mode A/B)."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.execution.loop_guards import (
    EmptyResponseTracker,
    LlmCallInterrupted,
    RunawayGuard,
    call_llm_with_retry,
    tool_call_signature,
)

pytestmark = pytest.mark.asyncio


def _hint(retryable: bool, backoff_s: float | None = None) -> SimpleNamespace:
    return SimpleNamespace(retryable=retryable, backoff_s=backoff_s)


def _classifier(retryable: bool, backoff_s: float | None = None):
    reason = SimpleNamespace(value="rate_limit" if retryable else "auth")
    return MagicMock(return_value=(reason, _hint(retryable, backoff_s)))


# ── call_llm_with_retry ──────────────────────────────────────


class TestCallLlmWithRetry:
    async def test_success_first_try(self):
        call = AsyncMock(return_value="ok")
        classify = _classifier(retryable=True)
        result = await call_llm_with_retry(
            call,
            classify=classify,
            next_backoff=lambda prev: 0.0,
        )
        assert result == "ok"
        assert call.call_count == 1
        classify.assert_not_called()

    async def test_retryable_error_then_success(self):
        call = AsyncMock(side_effect=[RuntimeError("429"), "ok"])
        sleep = AsyncMock()
        result = await call_llm_with_retry(
            call,
            classify=_classifier(retryable=True),
            next_backoff=lambda prev: 1.5,
            sleep=sleep,
        )
        assert result == "ok"
        assert call.call_count == 2
        # Backoff is slept in 1s chunks (interruptibility) — total must match
        assert sum(c.args[0] for c in sleep.await_args_list) == pytest.approx(1.5)

    async def test_provider_backoff_takes_precedence(self):
        call = AsyncMock(side_effect=[RuntimeError("429"), "ok"])
        sleep = AsyncMock()
        await call_llm_with_retry(
            call,
            classify=_classifier(retryable=True, backoff_s=7.0),
            next_backoff=lambda prev: 1.5,
            sleep=sleep,
        )
        assert sum(c.args[0] for c in sleep.await_args_list) == pytest.approx(7.0)

    async def test_terminal_error_raises_immediately(self):
        err = RuntimeError("401")
        call = AsyncMock(side_effect=err)
        sleep = AsyncMock()
        with pytest.raises(RuntimeError):
            await call_llm_with_retry(
                call,
                classify=_classifier(retryable=False),
                next_backoff=lambda prev: 0.0,
                sleep=sleep,
            )
        assert call.call_count == 1
        sleep.assert_not_awaited()

    async def test_retry_budget_exhausted_raises_original(self):
        err = RuntimeError("529")
        call = AsyncMock(side_effect=err)
        with pytest.raises(RuntimeError):
            await call_llm_with_retry(
                call,
                classify=_classifier(retryable=True),
                next_backoff=lambda prev: 0.0,
                max_retries=3,
                sleep=AsyncMock(),
            )
        # 1 initial + 3 retries
        assert call.call_count == 4

    async def test_interrupt_before_sleep_raises(self):
        call = AsyncMock(side_effect=RuntimeError("429"))
        sleep = AsyncMock()
        with pytest.raises(LlmCallInterrupted):
            await call_llm_with_retry(
                call,
                classify=_classifier(retryable=True),
                next_backoff=lambda prev: 0.0,
                interrupt_check=lambda: True,
                sleep=sleep,
            )
        assert call.call_count == 1
        sleep.assert_not_awaited()

    async def test_interrupt_during_chunked_backoff_raises(self):
        """A long backoff is aborted at the next 1s chunk boundary."""
        call = AsyncMock(side_effect=RuntimeError("429"))
        checks = iter([False, True])
        sleep = AsyncMock()
        with pytest.raises(LlmCallInterrupted):
            await call_llm_with_retry(
                call,
                classify=_classifier(retryable=True),
                next_backoff=lambda prev: 60.0,
                interrupt_check=lambda: next(checks),
                sleep=sleep,
            )
        assert call.call_count == 1
        # Only the first 1s chunk was slept — not the full 60s
        assert sum(c.args[0] for c in sleep.await_args_list) == pytest.approx(1.0)

    async def test_on_classified_error_called_per_attempt(self):
        call = AsyncMock(side_effect=[RuntimeError("a"), RuntimeError("b"), "ok"])
        on_error = MagicMock()
        await call_llm_with_retry(
            call,
            classify=_classifier(retryable=True),
            next_backoff=lambda prev: 0.0,
            on_classified_error=on_error,
            sleep=AsyncMock(),
        )
        assert on_error.call_count == 2

    async def test_on_classified_error_exception_swallowed(self):
        call = AsyncMock(side_effect=[RuntimeError("a"), "ok"])
        on_error = MagicMock(side_effect=ValueError("callback boom"))
        result = await call_llm_with_retry(
            call,
            classify=_classifier(retryable=True),
            next_backoff=lambda prev: 0.0,
            on_classified_error=on_error,
            sleep=AsyncMock(),
        )
        assert result == "ok"

    async def test_classifier_hint_without_retryable_attr_is_terminal(self):
        call = AsyncMock(side_effect=RuntimeError("boom"))
        classify = MagicMock(return_value=("unknown", object()))
        with pytest.raises(RuntimeError):
            await call_llm_with_retry(
                call,
                classify=classify,
                next_backoff=lambda prev: 0.0,
                sleep=AsyncMock(),
            )
        assert call.call_count == 1


# ── EmptyResponseTracker ─────────────────────────────────────


class TestEmptyResponseTracker:
    def test_is_empty_variants(self):
        assert EmptyResponseTracker.is_empty(None, has_tool_calls=False)
        assert EmptyResponseTracker.is_empty("", has_tool_calls=False)
        assert EmptyResponseTracker.is_empty("   \n ", has_tool_calls=False)
        assert not EmptyResponseTracker.is_empty("hello", has_tool_calls=False)
        assert not EmptyResponseTracker.is_empty("", has_tool_calls=True)

    def test_reprompt_budget(self):
        tracker = EmptyResponseTracker(limit=2)
        assert tracker.should_reprompt() is True
        assert tracker.should_reprompt() is True
        assert tracker.should_reprompt() is False
        assert tracker.reprompts_used == 2


# ── tool_call_signature ──────────────────────────────────────


class TestToolCallSignature:
    def test_deterministic(self):
        a = tool_call_signature("Read", {"path": "x", "limit": 5})
        b = tool_call_signature("Read", {"path": "x", "limit": 5})
        assert a == b

    def test_key_order_insensitive(self):
        a = tool_call_signature("Read", {"path": "x", "limit": 5})
        b = tool_call_signature("Read", {"limit": 5, "path": "x"})
        assert a == b

    def test_name_and_args_distinguish(self):
        base = tool_call_signature("Read", {"path": "x"})
        assert tool_call_signature("Write", {"path": "x"}) != base
        assert tool_call_signature("Read", {"path": "y"}) != base

    def test_none_args(self):
        assert tool_call_signature("Bash", None) == tool_call_signature("Bash", {})

    def test_unserializable_args_do_not_raise(self):
        sig = tool_call_signature("Bash", {"obj": object()})
        assert sig.startswith("Bash:")


# ── RunawayGuard ─────────────────────────────────────────────


class TestRunawayGuard:
    def test_streak_progression_warn_then_halt(self):
        guard = RunawayGuard()
        sig = ("Read:abc",)
        assert guard.observe(sig) == RunawayGuard.OK    # streak 1
        assert guard.observe(sig) == RunawayGuard.OK    # streak 2
        assert guard.observe(sig) == RunawayGuard.WARN  # streak 3
        assert guard.observe(sig) == RunawayGuard.OK    # streak 4 (warn fires once)
        assert guard.observe(sig) == RunawayGuard.HALT  # streak 5

    def test_different_turn_resets_streak(self):
        guard = RunawayGuard()
        sig = ("Read:abc",)
        guard.observe(sig)
        guard.observe(sig)
        assert guard.observe(("Write:def",)) == RunawayGuard.OK
        assert guard.streak == 1
        assert guard.observe(sig) == RunawayGuard.OK
        assert guard.streak == 1

    def test_empty_signature_is_ok(self):
        guard = RunawayGuard()
        assert guard.observe(()) == RunawayGuard.OK
        assert guard.streak == 0

    def test_multi_call_turn_signature(self):
        guard = RunawayGuard(warn_threshold=2, halt_threshold=3)
        sig = ("Read:abc", "Grep:def")
        assert guard.observe(sig) == RunawayGuard.OK
        assert guard.observe(sig) == RunawayGuard.WARN
        # Different order = different turn
        assert guard.observe(("Grep:def", "Read:abc")) == RunawayGuard.OK
        assert guard.streak == 1
