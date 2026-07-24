"""Chat-path integration tests for model fallback and one-shot retry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core._anima_messaging import (
    _resolve_chat_model_config,
    _run_chat_cycle_with_fallback,
    _run_chat_stream_with_fallback,
)
from core.exceptions import LLMAPIError
from core.schemas import CycleResult, ModelConfig


def _configs() -> tuple[ModelConfig, ModelConfig]:
    primary = ModelConfig(model="codex/gpt-5.4", execution_mode="c", resolved_mode="C")
    fallback = primary.model_copy(
        update={
            "model": "grok/grok-4.5",
            "execution_mode": "x",
            "resolved_mode": "X",
        }
    )
    return primary, fallback


def _fallback_meta() -> dict[str, object]:
    return {
        "primary": "codex/gpt-5.4",
        "fallback": "x:grok/grok-4.5",
        "reason": "quota_exhausted",
        "remaining": 1799,
    }


@pytest.mark.asyncio
async def test_blocking_terminal_error_retries_once_with_fallback() -> None:
    primary, fallback = _configs()
    owner = MagicMock()
    owner.agent.run_cycle = AsyncMock(
        side_effect=[
            CycleResult(
                trigger="message:human",
                action="error",
                summary="[Codex turn failed: usageLimitExceeded]",
            ),
            CycleResult(
                trigger="message:human",
                action="responded",
                summary="fallback succeeded",
            ),
        ]
    )

    with (
        patch(
            "core._anima_messaging.resolve_effective_model_config",
            return_value=fallback,
        ),
        patch(
            "core.execution.fallback_activity.fallback_event_meta",
            return_value=_fallback_meta(),
        ),
    ):
        result = await _run_chat_cycle_with_fallback(
            owner,
            prompt="hello",
            trigger="message:human",
            message_intent="",
            images=None,
            prior_messages=None,
            thread_id="default",
            primary_config=primary,
            active_config=primary,
        )

    assert result.summary == "fallback succeeded"
    assert owner.agent.run_cycle.await_count == 2
    overrides = [
        call.kwargs["model_config_override"]
        for call in owner.agent.run_cycle.await_args_list
    ]
    assert overrides == [primary, fallback]
    owner._activity.log.assert_called_once()
    assert owner._activity.log.call_args.args == ("model_fallback",)
    assert owner._activity.log.call_args.kwargs["meta"]["phase"] == "runtime_retry"


@pytest.mark.asyncio
async def test_blocking_retry_failure_uses_normal_error_path_without_third_attempt() -> None:
    primary, fallback = _configs()
    owner = MagicMock()
    owner.agent.run_cycle = AsyncMock(
        side_effect=[
            LLMAPIError("rate limit exceeded"),
            LLMAPIError("fallback also failed"),
        ]
    )

    with (
        patch(
            "core._anima_messaging.resolve_effective_model_config",
            return_value=fallback,
        ),
        patch(
            "core.execution.fallback_activity.fallback_event_meta",
            return_value=_fallback_meta(),
        ),
        pytest.raises(LLMAPIError, match="fallback also failed"),
    ):
        await _run_chat_cycle_with_fallback(
            owner,
            prompt="hello",
            trigger="message:human",
            message_intent="",
            images=None,
            prior_messages=None,
            thread_id="default",
            primary_config=primary,
            active_config=primary,
        )

    assert owner.agent.run_cycle.await_count == 2


@pytest.mark.asyncio
async def test_stream_terminal_chunk_is_suppressed_and_retried_once() -> None:
    primary, fallback = _configs()
    owner = MagicMock()
    seen_configs: list[ModelConfig] = []

    async def _stream(*args, **kwargs):
        config = kwargs["model_config_override"]
        seen_configs.append(config)
        if len(seen_configs) == 1:
            yield {
                "type": "error",
                "message": "[Codex turn failed: usageLimitExceeded]",
                "terminal": True,
                "reason": "quota_exhausted",
            }
            return
        yield {"type": "text_delta", "text": "ok"}
        yield {
            "type": "cycle_done",
            "cycle_result": {
                "trigger": "message:human",
                "action": "responded",
                "summary": "ok",
            },
        }

    owner.agent.run_cycle_streaming = _stream
    with (
        patch(
            "core._anima_messaging.resolve_effective_model_config",
            return_value=fallback,
        ),
        patch(
            "core.execution.fallback_activity.fallback_event_meta",
            return_value=_fallback_meta(),
        ),
    ):
        chunks = [
            chunk
            async for chunk in _run_chat_stream_with_fallback(
                owner,
                prompt="hello",
                trigger="message:human",
                message_intent="",
                images=None,
                prior_messages=None,
                thread_id="default",
                primary_config=primary,
                active_config=primary,
            )
        ]

    assert seen_configs == [primary, fallback]
    assert [chunk["type"] for chunk in chunks] == ["text_delta", "cycle_done"]


@pytest.mark.asyncio
async def test_stream_retry_failure_is_exposed_without_third_attempt() -> None:
    primary, fallback = _configs()
    owner = MagicMock()
    call_count = 0

    async def _stream(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        yield {
            "type": "error",
            "message": "[Codex turn failed: usageLimitExceeded]",
            "terminal": True,
            "reason": "quota_exhausted",
        }

    owner.agent.run_cycle_streaming = _stream
    with (
        patch(
            "core._anima_messaging.resolve_effective_model_config",
            return_value=fallback,
        ),
        patch(
            "core.execution.fallback_activity.fallback_event_meta",
            return_value=_fallback_meta(),
        ),
    ):
        chunks = [
            chunk
            async for chunk in _run_chat_stream_with_fallback(
                owner,
                prompt="hello",
                trigger="message:human",
                message_intent="",
                images=None,
                prior_messages=None,
                thread_id="default",
                primary_config=primary,
                active_config=primary,
            )
        ]

    assert call_count == 2
    assert len(chunks) == 1
    assert chunks[0]["type"] == "error"
    assert chunks[0]["terminal"] is True


def test_preflight_fallback_records_activity_event() -> None:
    primary, fallback = _configs()
    owner = MagicMock()
    with (
        patch(
            "core._anima_messaging.resolve_effective_model_config",
            return_value=fallback,
        ),
        patch(
            "core.execution.fallback_activity.fallback_event_meta",
            return_value=_fallback_meta(),
        ),
    ):
        effective = _resolve_chat_model_config(owner, primary, phase="preflight")

    assert effective == fallback
    owner._activity.log.assert_called_once_with(
        "model_fallback",
        summary="Model fallback: codex/gpt-5.4 -> x:grok/grok-4.5",
        channel="chat",
        meta={**_fallback_meta(), "phase": "preflight"},
        safe=True,
    )
