from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Adapters for one LiteLLM completion inside the shared Mode A tool loop.

The loop consumes :class:`CallUpdate` values while a token stream is active,
then a :class:`CallResult` with the complete turn metadata. Ollama and blocking
execution use the same result contract without opening a token stream.
"""

import asyncio
import logging
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass, field
from typing import Any

from core.execution._streaming import accumulate_tool_call_chunks
from core.execution.base import (
    StreamingThinkFilter,
    strip_thinking_tags,
    strip_untagged_thinking,
    supports_streaming_tool_use,
)
from core.execution.watchdog import engine_events

logger = logging.getLogger("animaworks.execution.litellm_loop")


@dataclass(slots=True)
class CallUpdate:
    """One update produced while adapting an LLM call."""

    kind: str
    text: str = ""
    usage: dict[str, int] | None = None


@dataclass(slots=True)
class CallResult:
    """Normalized result for one LLM turn."""

    text: str
    finish_reason: str | None
    usage: dict[str, int] | None
    tool_calls: list[Any] = field(default_factory=list)
    accumulated_tool_calls: dict[int, dict[str, Any]] | None = None
    thinking: list[str] = field(default_factory=list)
    reasoning_parts: list[str] = field(default_factory=list)
    thinking_blocks: list[dict[str, Any]] | None = None
    message: Any = None
    incremental: bool = False
    trailing_text: str = ""


def _value(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _usage_data(source: Any) -> dict[str, int] | None:
    """Return LiteLLM usage in the shape consumed by Mode A."""
    usage = _value(source, "usage")
    if not usage:
        return None

    prompt_tokens = _as_int(_value(usage, "prompt_tokens", 0))
    completion_tokens = _as_int(_value(usage, "completion_tokens", 0))
    cache_read_tokens = _as_int(_value(usage, "cache_read_input_tokens", 0))
    cache_write_tokens = _as_int(_value(usage, "cache_creation_input_tokens", 0))
    if not cache_read_tokens:
        prompt_details = _value(usage, "prompt_tokens_details")
        cache_read_tokens = _as_int(_value(prompt_details, "cached_tokens", 0)) if prompt_details else 0
    return {
        "input_tokens": prompt_tokens,
        "output_tokens": completion_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
    }


def _response_result(response: Any, *, flavor: str) -> CallResult:
    """Normalize a non-streaming completion while keeping provider objects intact."""
    choice = response.choices[0]
    message = choice.message
    raw_content = _value(message, "content") or ""
    content = raw_content if isinstance(raw_content, str) else str(raw_content)
    thinking_text, text = strip_thinking_tags(content)
    thinking: list[str] = []

    if flavor == "token_fallback":
        reasoning = _value(message, "reasoning_content") or _value(message, "reasoning") or ""
        if reasoning:
            thinking.append(str(reasoning))
        elif thinking_text:
            thinking.append(thinking_text)
        else:
            untagged, text = strip_untagged_thinking(text)
            if untagged:
                thinking.append(untagged)
    elif thinking_text:
        thinking.append(thinking_text)

    raw_tool_calls = _value(message, "tool_calls") or []
    return CallResult(
        text=text,
        finish_reason=_value(choice, "finish_reason"),
        usage=_usage_data(response),
        tool_calls=list(raw_tool_calls),
        thinking=thinking,
        message=message,
    )


class BlockingCall:
    """Non-streaming adapter used by ``execute``.

    ``stream`` is deliberately omitted from the LiteLLM kwargs, matching the
    existing blocking call contract (LiteLLM defaults it to false). This keeps
    blocking execution independent of provider streaming support.
    """

    incremental = False
    iteration_level = False

    def prepare_kwargs(self, kwargs: dict[str, Any], *, has_tools: bool) -> dict[str, Any]:
        del has_tools
        return {**kwargs, "num_retries": 0}

    async def open(self, completion: Any, kwargs: dict[str, Any]) -> Any:
        return await completion(**kwargs)

    async def read(
        self,
        response: Any,
        *,
        tools: list[dict[str, Any]],
        iteration: int,
    ) -> AsyncGenerator[CallUpdate | CallResult, None]:
        del tools, iteration
        yield _response_result(response, flavor="blocking")


class IterationCall(BlockingCall):
    """Ollama adapter: fetch one full response, then hand it to the shared loop."""

    iteration_level = True

    def __init__(self, *, timeout_s: float, model: str, trigger: str) -> None:
        self.timeout_s = timeout_s
        self.model = model
        self.trigger = trigger

    async def open(self, completion: Any, kwargs: dict[str, Any]) -> Any:
        request = completion(**kwargs)
        if self.timeout_s > 0:
            return await asyncio.wait_for(request, timeout=self.timeout_s)
        return await request

    async def read(
        self,
        response: Any,
        *,
        tools: list[dict[str, Any]],
        iteration: int,
    ) -> AsyncGenerator[CallUpdate | CallResult, None]:
        del tools, iteration
        # Keep the original provider message available: Ollama may attach
        # fields that need to remain in assistant history on the next turn.
        yield _response_result(response, flavor="iteration")

    def timeout_error(self) -> Exception:
        from core.exceptions import LLMAPIError

        logger.warning(
            "Ollama LLM call hard-timeout after %.0fs (trigger=%s model=%s)",
            self.timeout_s,
            self.trigger,
            self.model,
        )
        return LLMAPIError(f"Ollama request timed out after {self.timeout_s:.0f}s (model={self.model})")


class StreamingCall:
    """Token-stream adapter for providers that support LiteLLM streaming."""

    iteration_level = False

    def __init__(self, *, model: str) -> None:
        self.model = model
        self.incremental = True

    def prepare_kwargs(self, kwargs: dict[str, Any], *, has_tools: bool) -> dict[str, Any]:
        self.incremental = not has_tools or supports_streaming_tool_use(self.model)
        call_kwargs = {**kwargs, "stream": self.incremental}
        if self.incremental:
            call_kwargs["stream_options"] = {"include_usage": True}
        else:
            call_kwargs.pop("stream_options", None)
        call_kwargs["num_retries"] = 0
        return call_kwargs

    async def open(self, completion: Any, kwargs: dict[str, Any]) -> Any:
        return await completion(**kwargs)

    async def read(
        self,
        response: Any,
        *,
        tools: list[dict[str, Any]],
        iteration: int,
    ) -> AsyncGenerator[CallUpdate | CallResult, None]:
        if not self.incremental:
            yield _response_result(response, flavor="token_fallback")
            return

        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        finish_reason: str | None = None
        usage_data: dict[str, int] | None = None
        reasoning_seen = False
        think_filter = StreamingThinkFilter()
        chunk_count = 0

        async for chunk in engine_events(response):
            chunk_count += 1
            choices = _value(chunk, "choices") or []
            choice = choices[0] if choices else None
            chunk_usage = _usage_data(chunk)
            if chunk_usage is not None:
                usage_data = chunk_usage
                yield CallUpdate(kind="usage", usage=chunk_usage)
            if choice is None:
                continue

            delta = _value(choice, "delta")
            if delta:
                content = _value(delta, "content")
                if content:
                    thinking, visible_text = think_filter.feed(str(content))
                    if thinking:
                        if not reasoning_seen:
                            reasoning_seen = True
                            yield CallUpdate(kind="thinking_start")
                        yield CallUpdate(kind="thinking_delta", text=thinking)
                    if visible_text:
                        text_parts.append(visible_text)
                        yield CallUpdate(kind="text_delta", text=visible_text)

                reasoning = _value(delta, "reasoning_content")
                if reasoning:
                    reasoning_text = str(reasoning)
                    reasoning_parts.append(reasoning_text)
                    if not reasoning_seen:
                        reasoning_seen = True
                        yield CallUpdate(kind="thinking_start")
                    yield CallUpdate(kind="thinking_delta", text=reasoning_text)

                delta_tool_calls = _value(delta, "tool_calls")
                if delta_tool_calls:
                    accumulate_tool_call_chunks(tool_calls_acc, delta_tool_calls)

            choice_finish = _value(choice, "finish_reason")
            if choice_finish:
                finish_reason = choice_finish

        if reasoning_seen:
            yield CallUpdate(kind="thinking_end")

        trailing_text = ""
        flushed = think_filter.flush()
        if flushed:
            if reasoning_seen:
                yield CallUpdate(kind="trailing_thinking", text=flushed)
            else:
                trailing_text = flushed
                yield CallUpdate(kind="trailing_text", text=flushed)

        thinking_blocks = self._thinking_blocks(response, reasoning_parts)
        yield CallResult(
            text="".join(text_parts) + trailing_text,
            finish_reason=finish_reason,
            usage=usage_data,
            accumulated_tool_calls=tool_calls_acc,
            reasoning_parts=reasoning_parts,
            thinking_blocks=thinking_blocks,
            incremental=True,
            trailing_text=trailing_text,
        )

    @staticmethod
    def _thinking_blocks(response: Any, reasoning_parts: list[str]) -> list[dict[str, Any]] | None:
        """Read thinking blocks from LiteLLM's completed stream or build a fallback."""
        response_uptil_now = getattr(response, "response_uptil_now", None)
        if response_uptil_now:
            choices = getattr(response_uptil_now, "choices", None)
            if choices:
                message = getattr(choices[0], "message", None)
                if message:
                    blocks = getattr(message, "thinking_blocks", None)
                    if blocks is not None:
                        return blocks
        if reasoning_parts:
            return [{"type": "thinking", "thinking": "".join(reasoning_parts)}]
        return None


def load_ollama_total_timeout() -> float:
    """Return the configured hard request timeout for Ollama, or zero when disabled."""
    try:
        from core.config import load_config

        return float(load_config().server.ollama_total_timeout)
    except Exception:
        return 0.0
