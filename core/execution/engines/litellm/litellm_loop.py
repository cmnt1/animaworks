from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Mode A executor: LiteLLM plus a shared tool-use loop.

Per-call transport differences live in ``_llm_call``. ``ToolLoop`` owns the
conversation state and all decisions that apply across blocking, token-stream,
and Ollama iteration-stream execution.
"""

import asyncio
import json as _json
import logging
from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import asdict
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from core.exceptions import LLMAPIError
from core.execution._session import save_threshold_shortterm
from core.execution._streaming import (
    parse_accumulated_tool_calls,
    stream_error_boundary,
    try_parse_text_tool_call,
)
from core.execution.base import (
    BaseExecutor,
    ExecutionResult,
    RepetitionDetector,
    TokenUsage,
    ToolCallRecord,
    join_answer_parts,
    resolve_streamed_leaked_thinking,
    strip_thinking_tags,
    strip_untagged_thinking,
)
from core.execution.engines.litellm._litellm_context import ContextMixin, _extract_tool_uses_from_messages
from core.execution.engines.litellm._litellm_tools import (
    ToolProcessingMixin,
    _convert_litellm_tool_calls,
)
from core.execution.engines.litellm._llm_call import (
    BlockingCall,
    CallResult,
    CallUpdate,
    IterationCall,
    StreamingCall,
    load_ollama_total_timeout,
)
from core.execution.events import (
    context_update_event,
    done_event,
    error_event,
    stream_events,
    text_delta_event,
    tool_start_event,
)
from core.execution.loop_guards import (
    FINAL_RESPONSE_ERROR_TEXT,
    EmptyResponseTracker,
    LlmCallInterrupted,
    RunawayGuard,
    call_llm_with_retry,
    record_finalization_failure,
    record_runaway_event,
    strip_tool_protocol_messages,
    tool_call_signature,
)
from core.execution.reminder import (
    SystemReminderQueue,
    msg_context_threshold,
    msg_empty_response,
    msg_final_iteration,
    msg_output_truncated,
    msg_tool_loop_halt,
    msg_tool_loop_warning,
)
from core.llm.guard.backoff import decorrelated_jitter
from core.llm.guard.error_classifier import (
    FailoverReason,
    classify_llm_error,
    guard_key,
    litellm_realm_of,
    provider_family_of,
)
from core.llm.guard.rate_guard import get_rate_guard
from core.memory import MemoryManager
from core.memory.conversation.shortterm import ShortTermMemory
from core.prompt.context import ContextTracker
from core.schemas import ImageData, ModelConfig

if TYPE_CHECKING:
    from core.tooling.handler import ToolHandler

logger = logging.getLogger("animaworks.execution.litellm_loop")


# Backward-compatible public location for this loop-level callback.
def _make_rate_guard_reporter(guard: Any, key: str, label: str) -> Any:
    """Build the per-attempt error callback for ``call_llm_with_retry``."""

    def _report(reason: Any, hint: Any, exc: Exception, attempt: int) -> None:
        del attempt
        if reason in (
            FailoverReason.RATE_LIMIT,
            FailoverReason.OVERLOADED,
            FailoverReason.QUOTA_EXHAUSTED,
            FailoverReason.AUTH,
        ):
            long_lived = reason in (FailoverReason.QUOTA_EXHAUSTED, FailoverReason.AUTH)
            guard.report_block(
                key,
                guard.config.quota_block_seconds
                if long_lived
                else hint.backoff_s or guard.config.default_block_seconds,
                reason.value,
                reset_in_s=getattr(hint, "reset_in_s", None),
            )
        if reason in (FailoverReason.AUTH, FailoverReason.BILLING):
            logger.error(
                "%s LiteLLM %s — human attention required: %s",
                label,
                reason.value,
                exc,
            )

    return _report


class ToolLoop:
    """Single Mode A conversation loop shared by all LiteLLM call adapters."""

    def __init__(
        self,
        executor: LiteLLMExecutor,
        *,
        adapter: BlockingCall | IterationCall | StreamingCall,
        streaming: bool,
        prompt: str,
        system_prompt: str,
        tracker: ContextTracker | None,
        shortterm: ShortTermMemory | None,
        images: list[ImageData] | None,
        prior_messages: list[dict[str, Any]] | None,
        trigger: str,
    ) -> None:
        import litellm

        litellm.modify_params = True
        self.litellm = litellm
        self.executor = executor
        self.adapter = adapter
        self.streaming = streaming
        self.prompt = prompt
        self.tracker = tracker
        self.shortterm = shortterm
        self.trigger = trigger
        self.tools = executor._build_base_tools(trigger=trigger)
        self.context_window = executor._resolve_cw()
        self.messages = executor._build_initial_messages(
            system_prompt,
            prompt,
            images,
            prior_messages=prior_messages,
        )
        self.llm_kwargs = executor._build_llm_kwargs()
        # call_llm_with_retry is the only retry authority on this path.
        self.llm_kwargs["num_retries"] = 0
        self._current_response: CallResult | None = None
        self.iteration = 0

        # Anthropic requires thinking_blocks on resumed assistant tool turns
        # when extended thinking is active; preserve the prior token path's
        # compatibility patch only for the token-stream adapter.
        thinking_enabled = self.llm_kwargs.get("thinking") or self.llm_kwargs.get("reasoning_effort")
        if isinstance(adapter, StreamingCall) and thinking_enabled:
            patched = 0
            for message in self.messages:
                if (
                    message.get("role") == "assistant"
                    and message.get("tool_calls")
                    and not message.get("thinking_blocks")
                ):
                    message["thinking_blocks"] = [{"type": "thinking", "thinking": "(resumed session)"}]
                    patched += 1
            if patched:
                logger.info("A stream: injected synthetic thinking_blocks into %d prior assistant message(s)", patched)

        self.response_text: list[str] = []
        self.tool_records: list[ToolCallRecord] = []
        self.usage = TokenUsage()
        self.empty_responses = EmptyResponseTracker()
        self.repetition = RepetitionDetector()
        self.runaway = RunawayGuard()
        self.force_final = False
        self.final_reminder_sent = False
        self.finalization_failed = False

        family = provider_family_of(executor._model_config.model)
        self.guard_key = guard_key(family, litellm_realm_of(executor._model_config.model))
        self.classify = partial(classify_llm_error, provider_family=family)
        self.rate_guard = get_rate_guard()
        label = "A ollama stream" if isinstance(adapter, IterationCall) else "A stream" if streaming else "A"
        self.on_llm_error = _make_rate_guard_reporter(self.rate_guard, self.guard_key, label)

        if not streaming:
            blocked = self.rate_guard.blocked_remaining(self.guard_key)
            if blocked > 0:
                logger.info(
                    "A session start: %s rate-guarded for %.0fs (continuing; retries apply)",
                    self.guard_key,
                    blocked,
                )

    async def run(self) -> AsyncGenerator[dict[str, Any], None]:
        """Yield the shared loop's events, translating stream failures once."""
        if self.streaming:
            executor_name = "A-ollama-stream" if isinstance(self.adapter, IterationCall) else "A-stream"
            async with stream_error_boundary(self.response_text, executor_name=executor_name):
                async for event in self._run_turns():
                    yield event
            return

        async for event in self._run_turns():
            yield event

    async def _request(
        self, call_kwargs: dict[str, Any], iteration_messages: list[dict[str, Any]], iteration: int
    ) -> Any:
        async def _open() -> Any:
            try:
                return await self.adapter.open(self.litellm.acompletion, call_kwargs)
            except TimeoutError:
                if isinstance(self.adapter, IterationCall) and self.adapter.timeout_s > 0:
                    raise self.adapter.timeout_error() from None
                raise

        if self.streaming and iteration > 0:
            # A later call is a fresh request, but once earlier output has been
            # delivered only a context-overflow recovery is safe to retry.
            try:
                return await _open()
            except LLMAPIError:
                raise
            except Exception as exc:
                reason, _ = self.classify(exc)
                if getattr(reason, "value", None) == "context_overflow" and await self.executor._try_compact_messages(
                    iteration_messages,
                    self.llm_kwargs,
                    self.litellm,
                ):
                    logger.warning(
                        "A stream: context overflow at iteration=%d; compacting and retrying once",
                        iteration,
                    )
                    return await _open()
                raise

        try:
            return await call_llm_with_retry(
                _open,
                classify=self.classify,
                next_backoff=decorrelated_jitter,
                interrupt_check=self.executor._check_interrupted,
                on_classified_error=self.on_llm_error,
                on_context_overflow=partial(
                    self.executor._try_compact_messages,
                    iteration_messages,
                    self.llm_kwargs,
                    self.litellm,
                ),
            )
        except (LlmCallInterrupted, LLMAPIError):
            raise
        except Exception as exc:
            if self.streaming:
                raise
            logger.exception("LiteLLM API error")
            raise LLMAPIError(f"LiteLLM API error: {exc}") from exc

    def _account_usage(self, data: dict[str, int] | None) -> dict[str, Any] | None:
        if not data:
            return None

        self.usage.input_tokens += data.get("input_tokens", 0) or 0
        self.usage.output_tokens += data.get("output_tokens", 0) or 0
        self.usage.cache_read_tokens += data.get("cache_read_tokens", 0) or 0
        self.usage.cache_write_tokens += data.get("cache_write_tokens", 0) or 0

        context_event: dict[str, Any] | None = None
        if self.tracker:
            self.tracker.update_from_usage(data)
            if self.streaming:
                context_event = context_update_event(
                    context_usage_ratio=self.tracker.usage_ratio,
                    input_tokens=self.tracker._input_tokens,
                    context_window=self.tracker.context_window,
                    threshold=self.tracker.threshold,
                )
            if self.tracker.threshold_exceeded:
                try:
                    ratio = float(self.tracker.usage_ratio)
                except (TypeError, ValueError):
                    ratio = 0.0
                self.executor.reminder_queue.push_sync(msg_context_threshold(ratio=ratio))

            if not self.streaming and not self.force_final:
                current_text = ""
                # The blocking path records the latest assistant content for
                # threshold handoff before tool-call parsing mutates it.
                # ``_current_response`` is assigned when a call is consumed.
                if self._current_response is not None:
                    raw_content = getattr(self._current_response.message, "content", None) or ""
                    _, current_text = strip_thinking_tags(str(raw_content))
                save_threshold_shortterm(
                    self.tracker,
                    self.shortterm,
                    session_id="litellm-a",
                    trigger="a_tool_loop",
                    original_prompt=self.prompt,
                    accumulated_response="\n".join(self.response_text),
                    current_text=current_text,
                    turn_count=self.iteration,
                    tool_uses=_extract_tool_uses_from_messages(self.messages),
                )
        return context_event

    def _done(self, text: str, *, stop_kind: str, truncated: bool) -> dict[str, Any]:
        return done_event(
            text,
            result_message=None,
            tool_call_records=[asdict(record) for record in self.tool_records],
            usage=self.usage.to_dict(),
            stop_kind=stop_kind,
            truncated=truncated,
        )

    def _salvage_text(self, *, mode: str) -> str:
        salvaged = join_answer_parts(self.response_text)
        if salvaged.strip():
            logger.warning("%s: salvaging %d chars of prior response text", mode, len(salvaged))
            return salvaged
        logger.error("%s: no final answer to salvage", mode)
        return FINAL_RESPONSE_ERROR_TEXT

    @staticmethod
    def _trailing_event(update: CallUpdate) -> dict[str, Any]:
        if update.kind == "trailing_thinking":
            return {"type": "thinking_delta", "text": update.text}
        return text_delta_event(update.text)

    def _assistant_history(
        self,
        result: CallResult,
        parsed_calls: list[dict[str, Any]],
        text: str,
        *,
        text_tool_call: bool,
    ) -> dict[str, Any]:
        if isinstance(self.adapter, IterationCall) and not text_tool_call:
            message = result.message
            model_dump = getattr(message, "model_dump", None)
            dumped = model_dump() if callable(model_dump) else None
            assistant_message = dict(dumped) if isinstance(dumped, dict) else {"role": "assistant"}
            assistant_message.setdefault("role", "assistant")
            dumped_calls = assistant_message.get("tool_calls")
            if isinstance(dumped_calls, list):
                dumped_calls = [dict(call) if isinstance(call, dict) else call for call in dumped_calls]
                assistant_message["tool_calls"] = dumped_calls
                for index, parsed in enumerate(parsed_calls):
                    if index < len(dumped_calls) and isinstance(dumped_calls[index], dict):
                        if not dumped_calls[index].get("id"):
                            dumped_calls[index]["id"] = parsed["id"]
            return assistant_message

        serialized_calls: list[dict[str, Any]] = []
        for call in parsed_calls:
            arguments = call["arguments"]
            serialized_calls.append(
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": _json.dumps(arguments, ensure_ascii=False) if arguments is not None else "{}",
                    },
                }
            )
        assistant_message = {
            "role": "assistant",
            "content": text or None,
            "tool_calls": serialized_calls,
        }
        if result.thinking_blocks:
            assistant_message["thinking_blocks"] = result.thinking_blocks
        return assistant_message

    async def _run_turns(self) -> AsyncGenerator[dict[str, Any], None]:
        iteration = -1
        while True:
            iteration += 1
            self.iteration = iteration
            if (iteration + 1) % 10 == 0:
                logger.info("A tool loop progress: %d iterations", iteration + 1)
            if self.executor._check_interrupted():
                logger.info("LiteLLM execution interrupted at iteration=%d", iteration)
                interrupted = "[Session interrupted by user]"
                if self.streaming:
                    yield text_delta_event(interrupted)
                    if isinstance(self.adapter, IterationCall):
                        yield done_event(
                            interrupted,
                            result_message=None,
                            usage=self.usage.to_dict(),
                            stop_kind="interrupted",
                            truncated=True,
                        )
                    else:
                        yield done_event(
                            interrupted,
                            result_message=None,
                            stop_kind="interrupted",
                            truncated=True,
                        )
                else:
                    yield done_event(
                        interrupted,
                        result_message=None,
                        stop_kind="interrupted",
                        truncated=True,
                    )
                return

            is_final_iteration = self.force_final
            iter_tools = [] if is_final_iteration else self.tools
            if is_final_iteration and not self.final_reminder_sent:
                self.final_reminder_sent = True
                self.messages.append(
                    {
                        "role": "user",
                        "content": SystemReminderQueue.format_reminder(msg_final_iteration()),
                    }
                )
                logger.info("A final iteration=%d: tools removed", iteration)

            iteration_messages = strip_tool_protocol_messages(self.messages) if is_final_iteration else self.messages
            iter_kwargs = await self.executor._preflight_clamp_with_compaction(
                self.llm_kwargs,
                iteration_messages,
                iter_tools,
                self.litellm,
            )
            if iter_kwargs is None:
                message = f"[Error: prompt too large for {self.executor._model_config.model}]"
                if self.streaming:
                    yield text_delta_event(message)
                    yield error_event(message, terminal=True, reason="context_overflow")
                else:
                    yield error_event(message, terminal=True, reason="context_overflow")
                return

            call_kwargs: dict[str, Any] = {
                "messages": iteration_messages,
                **iter_kwargs,
            }
            if iter_tools:
                call_kwargs["tools"] = iter_tools
            call_kwargs = self.adapter.prepare_kwargs(call_kwargs, has_tools=bool(iter_tools))

            try:
                response = await self._request(call_kwargs, iteration_messages, iteration)
            except LlmCallInterrupted:
                logger.info("LiteLLM call interrupted during retry backoff at iteration=%d", iteration)
                interrupted = "[Session interrupted by user]"
                if self.streaming:
                    yield text_delta_event(interrupted)
                    if isinstance(self.adapter, IterationCall):
                        yield done_event(
                            interrupted,
                            result_message=None,
                            usage=self.usage.to_dict(),
                            stop_kind="interrupted",
                            truncated=True,
                        )
                    else:
                        yield done_event(
                            interrupted,
                            result_message=None,
                            stop_kind="interrupted",
                            truncated=True,
                        )
                else:
                    yield done_event(
                        interrupted,
                        result_message=None,
                        stop_kind="interrupted",
                        truncated=True,
                    )
                return

            self._current_response: CallResult | None = None
            streamed_text_parts: list[str] = []
            trailing_updates: list[CallUpdate] = []
            pending_usage: dict[str, int] | None = None
            thinking_seen = False
            result: CallResult | None = None
            repetition_detected = False
            async with aclosing(self.adapter.read(response, tools=iter_tools, iteration=iteration)) as updates:
                async for update in updates:
                    if isinstance(update, CallResult):
                        result = update
                        break
                    if update.kind == "usage":
                        if update.usage is not None:
                            pending_usage = update.usage
                        continue
                    if update.kind in ("trailing_text", "trailing_thinking"):
                        trailing_updates.append(update)
                        thinking_seen = thinking_seen or update.kind == "trailing_thinking"
                        continue
                    if update.kind == "text_delta":
                        if (
                            self.streaming
                            and isinstance(self.adapter, StreamingCall)
                            and self.adapter.incremental
                            and self.repetition.feed(update.text)
                        ):
                            streamed_text_parts.append(update.text)
                            yield text_delta_event(update.text)
                            truncation = "\n\n[Response truncated: repetition detected]"
                            streamed_text_parts.append(truncation)
                            yield text_delta_event(truncation)
                            repetition_detected = True
                            break
                        streamed_text_parts.append(update.text)
                        if self.streaming:
                            yield text_delta_event(update.text)
                        continue
                    if update.kind.startswith("thinking_"):
                        thinking_seen = True
                    if self.streaming:
                        yield {"type": update.kind, "text": update.text} if update.text else {"type": update.kind}

            if result is None and not repetition_detected:
                raise RuntimeError("LiteLLM call adapter ended without a CallResult")

            if result is not None:
                self._current_response = result
                iter_text = result.text
                usage_data = result.usage or pending_usage
            else:
                iter_text = "".join(streamed_text_parts)
                usage_data = pending_usage

            # Iteration-level and non-streaming responses are only available as
            # a whole. Detect repetition before parsing any apparent tool call.
            if (
                self.streaming
                and isinstance(self.adapter, IterationCall)
                and result is not None
                and self.repetition.check_full_text(iter_text)
            ):
                iter_text += "\n\n[Response truncated: repetition detected]"
                self.response_text.append(iter_text)
                context_event = self._account_usage(usage_data)
                if iter_text:
                    yield text_delta_event(iter_text)
                if context_event is not None:
                    yield context_event
                yield done_event(
                    join_answer_parts(self.response_text),
                    result_message=None,
                    tool_call_records=[asdict(record) for record in self.tool_records],
                    usage=self.usage.to_dict(),
                )
                return

            parsed_calls: list[dict[str, Any]] = []
            parse_failed = False
            text_tool_call = False
            has_structured_calls = bool(result is not None and (result.tool_calls or result.accumulated_tool_calls))

            if result is not None and not repetition_detected:
                try:
                    if result.accumulated_tool_calls is not None:
                        parsed_calls = parse_accumulated_tool_calls(result.accumulated_tool_calls)
                    elif result.tool_calls:
                        parsed_calls = _convert_litellm_tool_calls(result.tool_calls)
                except (ValueError, KeyError, AttributeError) as exc:
                    parse_failed = True
                    logger.warning(
                        "Tool-call conversion failed (model=%s, iteration=%d): %s — treating as text",
                        self.executor._model_config.model,
                        iteration,
                        exc,
                    )

                if not parse_failed and not has_structured_calls and iter_tools and iter_text:
                    text_call = try_parse_text_tool_call(iter_text, iter_tools)
                    if text_call:
                        name, arguments_json = text_call
                        call_id = f"text_call_{iteration}_{id(name) % 0xFFFF:04x}"
                        parsed_calls = [
                            {
                                "id": call_id,
                                "name": name,
                                "arguments": _json.loads(arguments_json),
                                "raw_arguments": None,
                            }
                        ]
                        text_tool_call = True
                        logger.info("A text-format tool call parsed: %s args=%s", name, arguments_json)
                        iter_text = ""

                parsed_calls = [call for call in parsed_calls if call.get("name")]
                if isinstance(self.adapter, IterationCall):
                    for index, call in enumerate(parsed_calls):
                        if not call.get("id"):
                            call["id"] = f"ollama_{iteration}_{index}"

            # Emit complete (non-streaming) response text after tool-call
            # detection so a JSON text call is not exposed as an answer.
            if self.streaming and result is not None and not result.incremental and not repetition_detected:
                for thinking in result.thinking:
                    yield {"type": "thinking_start"}
                    yield {"type": "thinking_delta", "text": thinking}
                    yield {"type": "thinking_end"}
                if iter_text:
                    yield text_delta_event(iter_text)

            context_event = self._account_usage(usage_data)
            if result is not None and result.finish_reason == "length":
                self.executor.reminder_queue.push_sync(msg_output_truncated())

            if repetition_detected:
                self.response_text.append(iter_text)
                if context_event is not None:
                    yield context_event
                full_text = join_answer_parts(self.response_text)
                yield self._done(
                    full_text,
                    stop_kind="runaway_halt" if is_final_iteration else "normal",
                    truncated=is_final_iteration,
                )
                return

            if parse_failed:
                if not self.streaming or isinstance(self.adapter, IterationCall):
                    if iter_text:
                        self.response_text.append(iter_text)
                if context_event is not None:
                    yield context_event
                for update in trailing_updates:
                    yield self._trailing_event(update)
                continue

            if not parsed_calls:
                if has_structured_calls:
                    logger.info("All tool calls filtered at iteration=%d — treating as text", iteration)
                    if not self.streaming or isinstance(self.adapter, IterationCall):
                        if iter_text:
                            self.response_text.append(iter_text)
                    if context_event is not None:
                        yield context_event
                    for update in trailing_updates:
                        yield self._trailing_event(update)
                    continue

                if not self.streaming:
                    final_text = iter_text
                    if EmptyResponseTracker.is_empty(final_text, has_tool_calls=False):
                        if is_final_iteration:
                            record_finalization_failure(
                                self.executor._anima_dir,
                                mode="A",
                                reason="empty_grace_response",
                            )
                            logger.error("A grace turn returned no answer at iteration=%d", iteration)
                            yield self._done(
                                self._salvage_text(mode="A"),
                                stop_kind="runaway_halt",
                                truncated=True,
                            )
                            return
                        if self.empty_responses.should_reprompt():
                            raw_content = getattr(result.message, "content", None) or "" if result else ""
                            self.messages.append({"role": "assistant", "content": raw_content})
                            self.messages.append(
                                {
                                    "role": "user",
                                    "content": SystemReminderQueue.format_reminder(msg_empty_response()),
                                }
                            )
                            logger.info(
                                "A empty response at iteration=%d; reprompting (%d used)",
                                iteration,
                                self.empty_responses.reprompts_used,
                            )
                            if context_event is not None:
                                yield context_event
                            continue
                        logger.warning("A empty response persisted after reprompts at iteration=%d", iteration)
                        record_finalization_failure(
                            self.executor._anima_dir,
                            mode="A",
                            reason="empty_response_after_reprompts",
                        )
                        yield self._done(
                            self._salvage_text(mode="A"),
                            stop_kind="empty_response",
                            truncated=True,
                        )
                        return

                    if final_text:
                        self.response_text.append(final_text)
                    if context_event is not None:
                        yield context_event
                    self.executor.reminder_queue.drain_formatted()
                    yield self._done(
                        join_answer_parts(self.response_text),
                        stop_kind="runaway_halt" if is_final_iteration else "normal",
                        truncated=is_final_iteration,
                    )
                    return

                # Streaming paths return one explicit error answer for an
                # empty final turn; unlike execute(), they do not reprompt.
                if iter_text:
                    self.response_text.append(iter_text)
                full_text = join_answer_parts(self.response_text)
                leaked_thinking = ""
                post_cleanup_events: list[dict[str, Any]] = []
                if isinstance(self.adapter, StreamingCall) and result is not None and result.incremental:
                    leaked_thinking, full_text = resolve_streamed_leaked_thinking(full_text)
                    if leaked_thinking:
                        logger.info("A stream: stripped leaked thinking (%d chars)", len(leaked_thinking))
                        if not thinking_seen:
                            post_cleanup_events.append({"type": "thinking_start"})
                        post_cleanup_events.append({"type": "thinking_delta", "text": leaked_thinking})
                        post_cleanup_events.append({"type": "thinking_end"})
                    elif not thinking_seen:
                        untagged_thinking, cleaned = strip_untagged_thinking(full_text)
                        if untagged_thinking:
                            full_text = cleaned
                            logger.info("A stream: stripped untagged thinking (%d chars)", len(untagged_thinking))
                            post_cleanup_events.extend(
                                (
                                    {"type": "thinking_start"},
                                    {"type": "thinking_delta", "text": untagged_thinking},
                                    {"type": "thinking_end"},
                                )
                            )
                    if result.reasoning_parts and not leaked_thinking and not thinking_seen:
                        reasoning = "".join(result.reasoning_parts)
                        if reasoning:
                            post_cleanup_events.extend(
                                (
                                    {"type": "thinking_start"},
                                    {"type": "thinking_delta", "text": reasoning},
                                    {"type": "thinking_end"},
                                )
                            )

                empty_final = not full_text.strip()
                if empty_final:
                    record_finalization_failure(
                        self.executor._anima_dir,
                        mode="A ollama stream" if isinstance(self.adapter, IterationCall) else "A stream",
                        reason="empty_grace_response" if is_final_iteration else "empty_final_response",
                    )
                    logger.error("A stream returned no answer at iteration=%d", iteration)
                    full_text = FINAL_RESPONSE_ERROR_TEXT

                if context_event is not None:
                    yield context_event
                for update in trailing_updates:
                    yield self._trailing_event(update)
                for event in post_cleanup_events:
                    yield event
                if empty_final:
                    yield text_delta_event(full_text)
                yield self._done(
                    full_text,
                    stop_kind=("runaway_halt" if is_final_iteration else "empty_response" if empty_final else "normal"),
                    truncated=is_final_iteration or empty_final,
                )
                return

            if is_final_iteration:
                self.finalization_failed = True
                record_finalization_failure(
                    self.executor._anima_dir,
                    mode="A ollama stream"
                    if isinstance(self.adapter, IterationCall)
                    else "A stream"
                    if self.streaming
                    else "A",
                    reason="tool_call_during_grace_turn",
                )
                logger.error("A grace turn returned tool calls at iteration=%d", iteration)
                if context_event is not None:
                    yield context_event
                for update in trailing_updates:
                    if update.kind == "trailing_thinking":
                        yield {"type": "thinking_delta", "text": update.text}
                    else:
                        yield text_delta_event(update.text)
                full_text = self._salvage_text(mode="A stream" if self.streaming else "A")
                if self.streaming and not self.response_text:
                    yield text_delta_event(full_text)
                yield self._done(full_text, stop_kind="runaway_halt", truncated=True)
                return

            turn_signature = tuple(tool_call_signature(call["name"], call["arguments"]) for call in parsed_calls)
            decision = self.runaway.observe(turn_signature)
            tool_names = sorted({call["name"] for call in parsed_calls})
            if decision == RunawayGuard.HALT:
                count = self.runaway.repetition_count
                logger.error(
                    "A runaway tool loop halted at iteration=%d (count=%d): %s",
                    iteration,
                    count,
                    ", ".join(tool_names),
                )
                record_runaway_event(
                    self.executor._anima_dir,
                    decision=decision,
                    mode="A ollama stream"
                    if isinstance(self.adapter, IterationCall)
                    else "A stream"
                    if self.streaming
                    else "A",
                    iteration=iteration,
                    count=count,
                    tool_names=tool_names,
                )
                self.force_final = True
                self.final_reminder_sent = True
                self.messages.append(
                    {
                        "role": "user",
                        "content": SystemReminderQueue.format_reminder(msg_tool_loop_halt(count=count)),
                    }
                )
                if context_event is not None:
                    yield context_event
                for update in trailing_updates:
                    if update.kind == "trailing_thinking":
                        yield {"type": "thinking_delta", "text": update.text}
                    else:
                        yield text_delta_event(update.text)
                continue

            if decision == RunawayGuard.WARN:
                count = self.runaway.repetition_count
                self.executor.reminder_queue.push_sync(
                    msg_tool_loop_warning(tool_names=", ".join(tool_names), count=count)
                )
                logger.warning("A runaway tool loop warning at iteration=%d (count=%d)", iteration, count)
                record_runaway_event(
                    self.executor._anima_dir,
                    decision=decision,
                    mode="A ollama stream"
                    if isinstance(self.adapter, IterationCall)
                    else "A stream"
                    if self.streaming
                    else "A",
                    iteration=iteration,
                    count=count,
                    tool_names=tool_names,
                )

            if iter_text.strip():
                self.response_text.append(iter_text)

            logger.info(
                "A tool calls at iteration=%d: %s",
                iteration,
                ", ".join(call["name"] for call in parsed_calls),
            )
            for call in parsed_calls:
                yield tool_start_event(call["name"], str(call.get("id") or ""))
            if context_event is not None:
                yield context_event
            for update in trailing_updates:
                if update.kind == "trailing_thinking":
                    yield {"type": "thinking_delta", "text": update.text}
                else:
                    yield text_delta_event(update.text)

            self.messages.append(
                self._assistant_history(
                    result,
                    parsed_calls,
                    iter_text,
                    text_tool_call=text_tool_call,
                )
            )
            async for event in self.executor._process_streaming_tool_calls(
                parsed_calls,
                self.messages,
                self.tools,
                context_window=self.context_window,
                record_errors=not self.streaming,
            ):
                if "record" in event:
                    self.tool_records.append(event["record"])
                yield event

            reminder = self.executor.reminder_queue.drain_sync()
            if reminder:
                self.messages.append(
                    {
                        "role": "user",
                        "content": SystemReminderQueue.format_reminder(reminder),
                    }
                )


class LiteLLMExecutor(ToolProcessingMixin, ContextMixin, BaseExecutor):
    """Execute Mode A through one shared LiteLLM tool-use loop."""

    saves_threshold_shortterm = True
    wants_structured_history = True

    def __init__(
        self,
        model_config: ModelConfig,
        anima_dir: Path,
        tool_handler: ToolHandler,
        tool_registry: list[str],
        memory: MemoryManager,
        personal_tools: dict[str, str] | None = None,
        interrupt_event: asyncio.Event | None = None,
    ) -> None:
        super().__init__(model_config, anima_dir, interrupt_event=interrupt_event)
        self._tool_handler = tool_handler
        self._tool_registry = tool_registry
        self._personal_tools = personal_tools or {}

    @property
    def _is_ollama_model(self) -> bool:
        """Return True if the configured model is served via Ollama."""
        model = self._model_config.model
        return model.startswith("ollama/") or model.startswith("ollama_chat/")

    async def execute(
        self,
        prompt: str,
        system_prompt: str = "",
        tracker: ContextTracker | None = None,
        shortterm: ShortTermMemory | None = None,
        trigger: str = "",
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        thread_id: str = "default",
    ) -> ExecutionResult:
        """Run the shared loop with non-streaming calls and aggregate its result."""
        del thread_id
        loop = ToolLoop(
            self,
            adapter=BlockingCall(),
            streaming=False,
            prompt=prompt,
            system_prompt=system_prompt,
            tracker=tracker,
            shortterm=shortterm,
            images=images,
            prior_messages=prior_messages,
            trigger=trigger,
        )
        terminal: dict[str, Any] | None = None
        async for event in loop.run():
            if event.get("type") in ("done", "error"):
                terminal = event

        if terminal is None:
            raise RuntimeError("LiteLLM tool loop ended without a terminal event")
        if terminal["type"] == "error":
            return ExecutionResult(
                text=terminal.get("message", "LiteLLM execution failed"),
                tool_call_records=loop.tool_records,
                error=True,
                reason=terminal.get("reason", ""),
            )
        if terminal.get("stop_kind") == "interrupted":
            return ExecutionResult(text=terminal["full_text"], truncated=True)

        serialized_records = terminal.get("tool_call_records", [])
        records = [ToolCallRecord(**record) for record in serialized_records]
        usage_data = terminal.get("usage")
        usage = TokenUsage(**usage_data) if usage_data is not None else None
        return ExecutionResult(
            text=terminal["full_text"],
            tool_call_records=records,
            usage=usage,
            truncated=bool(terminal.get("truncated", False)),
        )

    @stream_events
    async def execute_streaming(
        self,
        system_prompt: str,
        prompt: str,
        tracker: ContextTracker,
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        trigger: str = "",
        thread_id: str = "default",
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield events from the shared loop using the model's call adapter.

        Session chaining is handled by AgentCore.run_cycle_streaming(), not here.
        """
        del thread_id
        if self._is_ollama_model:
            adapter: BlockingCall | IterationCall | StreamingCall = IterationCall(
                timeout_s=load_ollama_total_timeout(),
                model=self._model_config.model,
                trigger=trigger,
            )
        else:
            adapter = StreamingCall(model=self._model_config.model)

        loop = ToolLoop(
            self,
            adapter=adapter,
            streaming=True,
            prompt=prompt,
            system_prompt=system_prompt,
            tracker=tracker,
            shortterm=None,
            images=images,
            prior_messages=prior_messages,
            trigger=trigger,
        )
        async for event in loop.run():
            yield event
