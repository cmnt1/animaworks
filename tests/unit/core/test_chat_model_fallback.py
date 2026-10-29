"""Chat-path integration tests for model fallback and one-shot retry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.anima.messaging import _resolve_chat_model_config, _run_chat_stream_with_fallback
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


def _install_stream_attempts(owner: MagicMock, attempts: list[CycleResult | Exception]) -> list[ModelConfig]:
    seen_configs: list[ModelConfig] = []

    async def _stream(*args, **kwargs):
        config = kwargs["model_config_override"]
        seen_configs.append(config)
        attempt = attempts[len(seen_configs) - 1]
        if isinstance(attempt, Exception):
            raise attempt
        yield {"type": "cycle_done", "cycle_result": attempt.model_dump(mode="json")}

    owner.agent.run_cycle_streaming = _stream
    return seen_configs


async def _run_chat_fallback(owner: MagicMock, primary: ModelConfig) -> list[dict[str, object]]:
    return [
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("summary", "reason"),
    [
        ("usage balance exhausted", "quota_exhausted"),
        ("authentication failed", "auth"),
    ],
)
async def test_blocking_terminal_error_retries_once_with_fallback(summary: str, reason: str) -> None:
    primary, fallback = _configs()
    owner = MagicMock()
    seen_configs = _install_stream_attempts(
        owner,
        [
            CycleResult(trigger="message:human", action="error", summary=summary, reason=reason),
            CycleResult(trigger="message:human", action="responded", summary="fallback succeeded"),
        ],
    )

    with (
        patch("core.anima.messaging.resolve_effective_model_config", return_value=fallback),
        patch("core.execution.fallback_activity.fallback_event_meta", return_value=_fallback_meta()),
    ):
        chunks = await _run_chat_fallback(owner, primary)

    assert chunks[-1]["cycle_result"]["summary"] == "fallback succeeded"
    assert seen_configs == [primary, fallback]
    owner._activity.log.assert_called_once()
    assert owner._activity.log.call_args.args == ("model_fallback",)
    assert owner._activity.log.call_args.kwargs["meta"]["phase"] == "runtime_retry"


@pytest.mark.asyncio
async def test_blocking_content_policy_error_does_not_fallback() -> None:
    primary, fallback = _configs()
    owner = MagicMock()
    seen_configs = _install_stream_attempts(
        owner,
        [
            CycleResult(
                trigger="message:human",
                action="error",
                summary="This request violates our usage policies",
                reason="content_policy",
            )
        ],
    )

    with patch("core.anima.messaging.resolve_effective_model_config", return_value=fallback) as resolve:
        chunks = await _run_chat_fallback(owner, primary)

    assert chunks[0]["cycle_result"]["summary"] == "This request violates our usage policies"
    assert seen_configs == [primary]
    resolve.assert_not_called()


@pytest.mark.asyncio
async def test_blocking_unknown_structured_error_still_falls_back() -> None:
    primary, fallback = _configs()
    owner = MagicMock()
    seen_configs = _install_stream_attempts(
        owner,
        [
            CycleResult(
                trigger="message:human",
                action="error",
                summary="A future provider failure we have never seen before",
                reason="unknown",
            ),
            CycleResult(trigger="message:human", action="responded", summary="fallback succeeded"),
        ],
    )

    with (
        patch("core.anima.messaging.resolve_effective_model_config", return_value=fallback),
        patch("core.execution.fallback_activity.fallback_event_meta", return_value=_fallback_meta()),
    ):
        chunks = await _run_chat_fallback(owner, primary)

    assert chunks[-1]["cycle_result"]["summary"] == "fallback succeeded"
    assert seen_configs == [primary, fallback]


@pytest.mark.asyncio
async def test_blocking_retry_failure_uses_normal_error_path_without_third_attempt() -> None:
    primary, fallback = _configs()
    owner = MagicMock()
    seen_configs = _install_stream_attempts(
        owner,
        [LLMAPIError("rate limit exceeded"), LLMAPIError("fallback also failed")],
    )

    with (
        patch("core.anima.messaging.resolve_effective_model_config", return_value=fallback),
        patch("core.execution.fallback_activity.fallback_event_meta", return_value=_fallback_meta()),
        pytest.raises(LLMAPIError, match="fallback also failed"),
    ):
        await _run_chat_fallback(owner, primary)

    assert seen_configs == [primary, fallback]


@pytest.mark.asyncio
async def test_blocking_walks_all_fallbacks_until_one_is_alive() -> None:
    primary, first_fallback = _configs()
    second_fallback = primary.model_copy(
        update={
            "model": "openai/deepseek-v4-flash-0731",
            "execution_mode": "a",
            "resolved_mode": "A",
            "credential": "deepseek",
        }
    )
    owner = MagicMock()
    seen_configs = _install_stream_attempts(
        owner,
        [
            CycleResult(
                trigger="message:human",
                action="responded",
                summary="You've reached your Fable 5 limit. Switch to another model.",
            ),
            LLMAPIError("API Error: 529 Overloaded"),
            CycleResult(trigger="message:human", action="responded", summary="deepseek succeeded"),
        ],
    )

    with (
        patch(
            "core.anima.messaging.resolve_effective_model_config",
            side_effect=[first_fallback, second_fallback],
        ),
        patch("core.execution.fallback_activity.fallback_event_meta", return_value=_fallback_meta()),
    ):
        chunks = await _run_chat_fallback(owner, primary)

    assert chunks[-1]["cycle_result"]["summary"] == "deepseek succeeded"
    assert seen_configs == [primary, first_fallback, second_fallback]
    assert owner._activity.log.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason",
    ["quota_exhausted", "rate_limit", "overloaded"],
)
async def test_stream_terminal_chunk_is_suppressed_and_retried_once(
    reason: str,
) -> None:
    primary, fallback = _configs()
    owner = MagicMock()
    seen_configs: list[ModelConfig] = []

    async def _stream(*args, **kwargs):
        config = kwargs["model_config_override"]
        seen_configs.append(config)
        if len(seen_configs) == 1:
            yield {
                "type": "error",
                "message": "[Grok CLI Error: Internal error]",
                "terminal": True,
                "reason": reason,
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
            "core.anima.messaging.resolve_effective_model_config",
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
            "core.anima.messaging.resolve_effective_model_config",
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


@pytest.mark.asyncio
async def test_stream_walks_multiple_fallbacks() -> None:
    primary, first_fallback = _configs()
    second_fallback = primary.model_copy(
        update={"model": "deepseek/deepseek-chat", "execution_mode": "a", "resolved_mode": "A"}
    )
    owner = MagicMock()
    seen_configs: list[ModelConfig] = []

    async def _stream(*args, **kwargs):
        config = kwargs["model_config_override"]
        seen_configs.append(config)
        if len(seen_configs) < 3:
            yield {
                "type": "error",
                "message": "provider overloaded",
                "terminal": True,
                "reason": "overloaded",
            }
            return
        yield {"type": "text_delta", "text": "ok"}
        yield {
            "type": "cycle_done",
            "cycle_result": {"trigger": "message:human", "action": "responded", "summary": "ok"},
        }

    owner.agent.run_cycle_streaming = _stream
    with (
        patch(
            "core.anima.messaging.resolve_effective_model_config",
            side_effect=[first_fallback, second_fallback],
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

    assert seen_configs == [primary, first_fallback, second_fallback]
    assert [chunk["type"] for chunk in chunks] == ["text_delta", "cycle_done"]


def test_preflight_fallback_records_activity_event() -> None:
    primary, fallback = _configs()
    owner = MagicMock()
    with (
        patch(
            "core.anima.messaging.resolve_effective_model_config",
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


@pytest.mark.asyncio
async def test_reply_mentioning_403_is_not_an_auth_failure(tmp_path) -> None:
    """A normal reply quoting an API 403 must not block the provider (#natsume-deepseek)."""
    from core.execution import fallback_activity as fa

    calls: list[str] = []
    monkey = pytest.MonkeyPatch()
    monkey.setattr(fa, "report_capacity_block", lambda *a, **k: calls.append("blocked"))
    try:
        cfg = ModelConfig(
            model="codex/gpt-5.6-luna",
            execution_mode="c",
            resolved_mode="C",
            fallback_models=["a:openai/deepseek-v4-flash"],
        )
        reply = CycleResult(
            trigger="cron:x",
            action="responded",
            summary=(
                "Chatwork統合監視で代表宛メンションを1件検知しました。room 373957118 の再取得は "
                "Chatwork API HTTP 403 Forbidden で失敗したため本文の確定は保留。" + "対応内容の要約。" * 60
            ),
        )

        async def run(_c):
            return reply

        result = await fa.run_with_model_fallback(
            run, activity=MagicMock(), primary_config=cfg, active_config=cfg, channel="cron"
        )
    finally:
        monkey.undo()
    assert result is reply
    assert calls == []
