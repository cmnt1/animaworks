from __future__ import annotations

from core.prompt.builder import MEETING_DONE_SENTINEL, PROMPT_PROFILE_MEETING

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CycleMixin -- blocking and streaming execution cycles.

Extracted from ``core.agent.agent_core.AgentCore`` as a Mixin.  All ``self`` references
are resolved at runtime via MRO when mixed into ``AgentCore``.
"""

import asyncio
import inspect
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

    from core.execution.base import ExecutionResult

from core.agent.priming import SystemPromptContext
from core.agent.prompt_log import _save_prompt_log, _save_prompt_log_end
from core.execution.session.engine_session import aclear_all_engine_sessions, aclear_engine_session
from core.execution.session.session_context import RuntimeSessionContext, runtime_session_scope
from core.execution.session.session_types import (
    is_clean_start_session,
    resolve_runtime_session_type,
    trigger_uses_chat_session,
)
from core.i18n import t
from core.memory.conversation.shortterm import SessionState, ShortTermMemory
from core.platform.state_writer import get_state_writer
from core.prompt.context import ContextTracker
from core.schemas import CycleResult, ImageData, ModelConfig
from core.time_utils import now_iso, now_local

logger = logging.getLogger("animaworks.agent")


@dataclass
class _PreparedCyclePrompt:
    """Prompt and session context shared by blocking and streaming cycles."""

    prompt: str
    system_prompt: str
    tracker: ContextTracker
    shortterm: ShortTermMemory
    uses_chat_session: bool
    prompt_context: SystemPromptContext


def _request_background_review(anima_dir: Path, trigger: str) -> None:
    try:
        from core.memory.maintenance.background_review import request_background_review

        request_background_review(anima_dir, trigger)
    except Exception:
        logger.warning("Could not queue background review (%s)", trigger)


async def _await_if_needed(value: Any) -> Any:
    """Await async persistence while keeping synchronous test doubles compatible."""
    if inspect.isawaitable(value):
        return await value
    return value


_USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens")
_STREAM_RETRY_AFTER_BUFFER_S = 1.0

# Meeting turns can end on a bare acknowledgement ("I'll check") because the Agent
# SDK closes a turn on any text-only message. When that happens we re-invoke the
# model (same resumable session) with a nudge to actually deliver findings, up to
# this many times, before giving up and returning whatever we have.
_MEETING_CONT_MAX_RETRIES = 2

# The server wraps each meeting speaker's whole stream in a fixed wall-clock budget
# (server.routes.room.MEETING_MIN_STREAM_TIMEOUT = 120s). Each continuation pass
# runs inside that same budget, so we must not START a new pass once we are close
# to it — otherwise the server emits STREAM_TIMEOUT and discards the work. This
# deadline (seconds of elapsed wall time in the child) stays comfortably under the
# server MIN so an in-flight continuation pass can finish and stream back in time.
_MEETING_CONT_DEADLINE_S = 90.0


def _strip_meeting_sentinel(text: str) -> str:
    """Remove the meeting completion sentinel (and any now-empty line) from text."""
    if not text or MEETING_DONE_SENTINEL not in text:
        return text
    return text.replace(MEETING_DONE_SENTINEL, "").rstrip()


def _merge_stream_usage(acc: dict[str, int], chunk_usage: dict[str, int] | None) -> None:
    """Accumulate chunk usage into the streaming accumulator dict."""
    if not chunk_usage:
        return
    for k in _USAGE_KEYS:
        acc[k] = acc.get(k, 0) + (chunk_usage.get(k, 0) or 0)


def _resolve_error_category(reason: str, message: str) -> str | None:
    """Derive a stable ``error_category`` for a terminal execution error.

    Prefers the executor-provided ``FailoverReason`` value (set when an
    executor classifies the underlying exception with ``classify_llm_error*``),
    falling back to classifying the terminal error message through the same
    shared classifier.  Returns ``None`` for non-error terminals.
    """
    if reason:
        return reason
    if not message:
        return None
    try:
        from core.llm.guard.error_classifier import classify_llm_error_message

        classified, _hint = classify_llm_error_message(message)
        return getattr(classified, "value", None)
    except Exception:
        logger.debug("failed to classify terminal error message", exc_info=True)
        return None


async def _log_session_token_usage(
    anima_dir: Path,
    *,
    model: str,
    mode: str,
    trigger: str,
    usage: dict[str, int] | None,
    duration_ms: int = 0,
    turns: int = 0,
) -> None:
    """Fire-and-forget token usage log entry."""
    if not usage or not any(usage.values()):
        return
    try:
        from core.usage.token_usage import TokenUsageLogger

        tul = TokenUsageLogger(anima_dir)
        await tul.alog(
            model=model,
            trigger=trigger,
            mode=mode,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_tokens", 0),
            cache_write_tokens=usage.get("cache_write_tokens", 0),
            turns=turns,
            duration_ms=duration_ms,
        )
    except Exception:
        logger.debug("Failed to log token usage", exc_info=True)


async def _save_handoff_shortterm(
    shortterm: ShortTermMemory,
    *,
    result_text: str,
    tool_records: list[Any],
    session_id: str,
    turn_count: int,
    trigger: str,
    prompt: str,
    tracker: ContextTracker,
) -> None:
    """Persist response and tool history when a chat session must be handed off."""
    from dataclasses import asdict, is_dataclass

    tool_uses = [asdict(record) if is_dataclass(record) else dict(record) for record in tool_records]
    state = SessionState(
        session_id=session_id,
        timestamp=now_iso(),
        trigger=trigger,
        original_prompt=prompt,
        accumulated_response=result_text,
        tool_uses=tool_uses,
        context_usage_ratio=tracker.usage_ratio,
        turn_count=turn_count,
    )
    saved = shortterm.asave(state)
    if inspect.isawaitable(saved):
        await saved
    else:
        await asyncio.to_thread(shortterm.save, state)


class CycleMixin:
    """Mixin: blocking and streaming execution cycles + session chaining."""

    async def _guard_chat_sdk_session(
        self,
        *,
        executor: Any,
        uses_chat_session: bool,
        active_model_config: ModelConfig,
        thread_id: str,
    ) -> Any | None:
        """Recycle an overgrown or over-aged SDK session before resume."""
        if getattr(executor, "tracks_sdk_session_state", False) is not True or not uses_chat_session:
            return None
        from core.execution.engines.claude._sdk_session import SESSION_TYPE_CHAT, load_session_state

        state = load_session_state(self.anima_dir, SESSION_TYPE_CHAT, thread_id)
        if state is None:
            return None
        if not state.session_id:
            await aclear_engine_session(self.anima_dir, "agent_sdk", SESSION_TYPE_CHAT, thread_id)
            return None
        now = datetime.now(UTC)
        try:
            created = datetime.fromisoformat(state.created_at)
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)
            age_hours = max(0.0, (now - created).total_seconds() / 3600)
        except ValueError:
            age_hours = 0.0
        reasons: list[str] = []
        if state.last_ratio >= active_model_config.context_absolute_ceiling:
            reasons.append("ceiling")
        if age_hours >= active_model_config.max_session_age_hours:
            reasons.append("max_age")
        if not reasons:
            return state

        from core.agent.session_compactor import _compact_mode_s_shared

        reason = "+".join(reasons)
        logger.info(
            "Recycling chat SDK session before resume: reason=%s ratio=%.3f age_hours=%.2f session=%s thread=%s",
            reason,
            state.last_ratio,
            age_hours,
            state.session_id,
            thread_id,
        )
        _request_background_review(self.anima_dir, "auto_compact")
        await _compact_mode_s_shared(
            self.anima_dir,
            self.anima_dir.name,
            thread_id,
            trigger="session_recycled",
            notes="Auto-saved before session recycling",
        )
        try:
            from core.activity.logger import ActivityLogger

            await ActivityLogger(self.anima_dir).alog(
                "session_recycled",
                summary=f"SDK chat session recycled ({reason})",
                meta={
                    "reason": reason,
                    "last_ratio": state.last_ratio,
                    "age_hours": age_hours,
                    "session_id": state.session_id,
                    "thread_id": thread_id,
                },
            )
        except Exception:
            logger.warning("Failed to log session_recycled activity", exc_info=True)
        return None

    def _cycle_fallback_channel(self, trigger: str) -> str:
        """Activity-log channel name derived from the cycle trigger."""
        return (trigger or "cycle").split(":", 1)[0] or "cycle"

    def _cycle_preflight_config(
        self,
        model_config_override: ModelConfig | None,
        trigger: str,
    ) -> tuple[ModelConfig, ModelConfig | None]:
        """Apply the rate-guard fallback preflight for any cycle route.

        Returns ``(primary_config, override_to_use)``.  ``override_to_use`` is
        ``None`` when the caller passed no override and no fallback applied, so
        the cached ``self._executor`` fast path is preserved.
        """
        primary = model_config_override or self.model_config
        if not isinstance(primary, ModelConfig) or not primary.fallback_models:
            return primary, model_config_override

        from core.execution.fallback_activity import preflight_fallback_config

        effective = preflight_fallback_config(
            self.anima_dir,
            primary,
            channel=self._cycle_fallback_channel(trigger),
        )
        if effective is primary:
            return primary, model_config_override
        return primary, effective

    def _cycle_runtime_fallback(
        self,
        result: CycleResult,
        primary_config: ModelConfig,
        active_override: ModelConfig | None,
        trigger: str,
    ) -> ModelConfig | None:
        """Return a config to re-run a failed blocking cycle with, if any."""
        if not isinstance(result, CycleResult) or not isinstance(primary_config, ModelConfig):
            return None
        if not primary_config.fallback_models:
            return None
        if result.action != "error" and not result.reason:
            return None
        from core.execution.fallback_activity import has_partial_execution, runtime_fallback_config

        return runtime_fallback_config(
            self.anima_dir,
            primary_config,
            active_override or primary_config,
            error_text=result.summary or "",
            reason=str(result.reason or ""),
            channel=self._cycle_fallback_channel(trigger),
            partial_execution=has_partial_execution(result),
        )

    async def _check_monthly_token_budget(
        self,
        *,
        trigger: str,
        model_config: ModelConfig,
    ) -> CycleResult | None:
        """Return a skipped result when the Anima has reached its monthly cap.

        The unlimited path deliberately returns before constructing the usage
        logger, preserving the pre-budget behaviour without aggregation I/O.
        Usage-read failures are fail-closed when a budget is configured so a
        transient observability problem cannot bypass the spending cap.
        """
        budget = model_config.token_budget_monthly
        if budget is None:
            return None

        now = now_local()
        try:
            from core.usage.token_budget import calculate_token_budget_status
            from core.usage.token_usage import TokenUsageLogger

            consumed = await TokenUsageLogger(self.anima_dir).monthly_total_async(now)
            status = calculate_token_budget_status(budget, consumed)
        except Exception as exc:
            logger.warning(
                "Failed to check monthly token budget for %s; blocking cycle",
                self.anima_dir.name,
                exc_info=True,
            )
            try:
                from core.activity.logger import ActivityLogger

                ActivityLogger(self.anima_dir).log(
                    "budget_check_failed",
                    summary="Monthly token budget could not be verified; LLM cycle skipped",
                    meta={
                        "budget": budget,
                        "month": now.strftime("%Y-%m"),
                        "trigger": trigger,
                        "error": type(exc).__name__,
                    },
                    safe=True,
                )
            except Exception:
                logger.warning("Failed to record budget_check_failed activity", exc_info=True)
            return CycleResult(
                trigger=trigger,
                action="skipped",
                stop_kind="budget_skipped",
                summary="Monthly token budget could not be verified; LLM cycle skipped",
            )

        if not status.exceeded:
            return None

        month = now.strftime("%Y-%m")
        meta = {
            "budget": status.budget,
            "consumed": status.consumed,
            "month": month,
            "trigger": trigger,
        }
        try:
            from core.activity.logger import ActivityLogger

            ActivityLogger(self.anima_dir).log(
                "budget_exceeded",
                summary="Monthly token budget reached; LLM cycle skipped",
                meta=meta,
                safe=True,
            )
        except Exception:
            logger.warning("Failed to record budget_exceeded activity", exc_info=True)

        await self._write_budget_exceeded_notification(meta)
        logger.warning(
            "Monthly token budget reached for %s: consumed=%d budget=%d trigger=%s",
            self.anima_dir.name,
            status.consumed,
            budget,
            trigger,
        )
        return CycleResult(
            trigger=trigger,
            action="skipped",
            stop_kind="budget_skipped",
            summary="Monthly token budget reached; LLM cycle skipped",
        )

    async def _write_budget_exceeded_notification(self, meta: dict[str, Any]) -> None:
        """Write the owner notification at most once for each calendar month."""
        try:
            await get_state_writer(self.anima_dir).write_token_budget_notification(str(meta["month"]), meta)
        except Exception:
            logger.warning("Failed to write token budget notification", exc_info=True)

    async def _prepare_clean_start_session(
        self,
        *,
        trigger: str,
        session_type: str,
        thread_id: str,
        shortterm: ShortTermMemory,
    ) -> None:
        """Clear stale runtime state for non-chat sessions before execution."""
        if not is_clean_start_session(trigger):
            return

        try:
            await shortterm.aclear_for_clean_start()
        except Exception:
            logger.debug("Failed to clear non-chat shortterm state", exc_info=True)

        await aclear_all_engine_sessions(self.anima_dir, session_type, thread_id)

    # ── Public API ─────────────────────────────────────────

    async def run_cycle(
        self,
        prompt: str,
        trigger: str = "manual",
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        message_intent: str = "",
        thread_id: str = "default",
        model_config_override: ModelConfig | None = None,
        prompt_tier_override: str | None = None,
    ) -> CycleResult:
        """Run one agent cycle with autonomous memory search.

        Routing:
          - Mode A (autonomous): ``LiteLLMExecutor`` -- LiteLLM + tool_use
          - Mode C (codex):      ``CodexSDKExecutor`` -- Codex CLI wrapper
          - Mode D (cursor):     ``CursorAgentExecutor`` -- Cursor Agent CLI
          - Mode G (gemini):     ``GeminiCLIExecutor`` -- Gemini CLI
          - Mode X (grok):       ``GrokCLIExecutor`` -- Grok Build CLI
          - Mode S (SDK):        ``AgentSDKExecutor`` -- Claude Agent SDK

        If the context threshold is crossed (A mode only), the session is
        externalized to short-term memory and automatically continued.
        SDK and CLI modes use executor-specific session management.
        """
        from core.infra.logging_config import bind_cycle_context, clear_cycle_context

        # Correlate every log line emitted during this cycle. Tokens restore any
        # outer cycle's context so nested cycles don't leak their id upward.
        cycle_tokens = bind_cycle_context(uuid4().hex[:8], trigger)
        try:
            async with self._get_agent_lock(thread_id):
                budget_result = await _await_if_needed(
                    self._check_monthly_token_budget(
                        trigger=trigger,
                        model_config=self.model_config,
                    )
                )
                if budget_result is not None:
                    return budget_result
                primary_config, active_override = self._cycle_preflight_config(model_config_override, trigger)
                result = await self._run_cycle_inner(
                    prompt,
                    trigger,
                    images=images,
                    prior_messages=prior_messages,
                    message_intent=message_intent,
                    thread_id=thread_id,
                    model_config_override=active_override,
                )
                retry_config = self._cycle_runtime_fallback(result, primary_config, active_override, trigger)
                if retry_config is None:
                    return result
                return await self._run_cycle_inner(
                    prompt,
                    trigger,
                    images=images,
                    prior_messages=prior_messages,
                    message_intent=message_intent,
                    thread_id=thread_id,
                    model_config_override=retry_config,
                    prompt_tier_override=prompt_tier_override,
                )
        finally:
            clear_cycle_context(cycle_tokens)

    async def _run_cycle_inner(
        self,
        prompt: str,
        trigger: str,
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        message_intent: str = "",
        thread_id: str = "default",
        model_config_override: ModelConfig | None = None,
        prompt_tier_override: str | None = None,
    ) -> CycleResult:
        session_type = resolve_runtime_session_type(trigger)
        ctx = RuntimeSessionContext.create(
            session_type=session_type,
            thread_id=thread_id,
            trigger=trigger,
        )
        with runtime_session_scope(ctx):
            self._tool_handler.bind_runtime_session(ctx)
            token = self._tool_handler.set_active_session_type(session_type)
            try:
                result = await self._run_cycle_inner_scoped(
                    prompt,
                    trigger,
                    images=images,
                    prior_messages=prior_messages,
                    message_intent=message_intent,
                    thread_id=thread_id,
                    model_config_override=model_config_override,
                    prompt_tier_override=prompt_tier_override,
                )
                result.session_type = ctx.session_type
                result.thread_id = ctx.thread_id
                result.request_id = ctx.request_id
                result.tool_session_id = ctx.tool_session_id
                return result
            finally:
                from core.tooling.handler import active_session_type

                try:
                    active_session_type.reset(token)
                except (TypeError, ValueError):
                    pass

    async def _prepare_cycle_prompt(
        self,
        prompt: str,
        trigger: str,
        *,
        message_intent: str,
        thread_id: str,
        prior_messages: list[dict[str, Any]] | None,
        active_model_config: ModelConfig,
        active_executor: Any,
        mode: str,
        save_prompt_log_after_preflight: bool,
        prompt_tier_override: str | None = None,
    ) -> _PreparedCyclePrompt:
        """Resolve, build, fit, and log the prompt shared by both cycle paths."""
        from core.prompt.builder import TIER_MICRO, resolve_prompt_tier
        from core.prompt.context import resolve_context_window

        context_window = resolve_context_window(
            active_model_config.model,
            overrides=self._load_context_window_overrides(),
        )
        prompt_profile = PROMPT_PROFILE_MEETING if prompt_tier_override == PROMPT_PROFILE_MEETING else ""
        prompt_tier = TIER_MICRO if prompt_profile else prompt_tier_override or resolve_prompt_tier(context_window)
        priming_section, pending_human_notifications = await self._run_priming(
            prompt,
            trigger,
            message_intent=message_intent,
            prompt_tier=prompt_tier,
            model_config=active_model_config,
        )

        session_type = resolve_runtime_session_type(trigger)
        uses_chat_session = trigger_uses_chat_session(trigger)
        session_state = await self._guard_chat_sdk_session(
            executor=active_executor,
            uses_chat_session=uses_chat_session,
            active_model_config=active_model_config,
            thread_id=thread_id,
        )
        shortterm = ShortTermMemory(self.anima_dir, session_type=session_type, thread_id=thread_id)
        await _await_if_needed(shortterm.ensure_ready())
        await self._prepare_clean_start_session(
            trigger=trigger,
            session_type=session_type,
            thread_id=thread_id,
            shortterm=shortterm,
        )
        shortterm_text = ""
        if uses_chat_session and shortterm.has_pending():
            shortterm_text = shortterm.render_for_injection()
            logger.info("Included short-term memory in system prompt allocation")
        tracker = ContextTracker(
            model=active_model_config.model,
            threshold=active_model_config.context_threshold,
            absolute_ceiling=active_model_config.context_absolute_ceiling,
            baseline_tokens=session_state.baseline_tokens if session_state is not None else 0,
            context_window_overrides=self._load_context_window_overrides(),
            anima_dir=self.anima_dir,
            session_type=session_type
            if getattr(active_executor, "tracks_sdk_session_state", False) is True and uses_chat_session
            else "",
            thread_id=thread_id,
            session_id=session_state.session_id if session_state is not None else "",
            session_created_at=session_state.created_at if session_state is not None else "",
            session_last_ratio=session_state.last_ratio if session_state is not None else 0.0,
        )
        prompt_context = SystemPromptContext(
            priming_section=priming_section,
            execution_mode=mode,
            message=prompt,
            trigger=trigger,
            context_window=context_window,
            pending_human_notifications=pending_human_notifications,
            thread_id=thread_id,
            shortterm_text=shortterm_text,
            prompt_tier=prompt_tier,
            prompt_profile=prompt_profile,
        )
        system_prompt = self._compose_system_prompt(prompt_context).system_prompt
        if not save_prompt_log_after_preflight:
            logger.debug("System prompt assembled, length=%d tier=%s", len(system_prompt), prompt_tier)

        system_prompt = self._fit_prompt_to_context_window(
            system_prompt,
            prompt,
            context_window,
            priming_section=priming_section,
            mode=mode,
            trigger=trigger,
            pending_human_notifications=pending_human_notifications,
            thread_id=thread_id,
            shortterm_text=shortterm_text,
            prompt_tier=prompt_tier,
            prompt_profile=prompt_profile,
        )

        async def _save_cycle_prompt_log() -> None:
            from core.tooling.policy.schemas import load_all_tool_schemas

            tool_schemas = load_all_tool_schemas(
                tool_registry=self._tool_registry,
                personal_tools=self._personal_tools,
            )
            await _await_if_needed(
                _save_prompt_log(
                    self.anima_dir,
                    trigger=trigger,
                    sender=self._extract_sender(prompt, trigger),
                    model=active_model_config.model,
                    mode=mode,
                    system_prompt=system_prompt,
                    user_message=prompt,
                    tools=self._tool_registry,
                    session_id=self._tool_handler.session_id,
                    context_window=context_window,
                    prior_messages=prior_messages,
                    tool_schemas=tool_schemas,
                )
            )

        if not save_prompt_log_after_preflight:
            await _save_cycle_prompt_log()

        conv_memory = None
        if uses_chat_session:
            from core.memory.conversation.memory import ConversationMemory

            conv_memory = ConversationMemory(self.anima_dir, active_model_config, thread_id=thread_id)
        system_prompt, prompt = await self._preflight_size_check(
            system_prompt,
            prompt,
            conv_memory,
            priming_section=priming_section,
            mode=mode,
            message=prompt,
            trigger=trigger,
            context_window=context_window,
            pending_human_notifications=pending_human_notifications,
            thread_id=thread_id,
            shortterm_text=shortterm_text,
            prompt_tier=prompt_tier,
            prompt_profile=prompt_profile,
        )
        prompt_context = replace(prompt_context, message=prompt)
        active_executor.prepare_tracker(tracker, system_prompt, prompt)

        if save_prompt_log_after_preflight:
            await _save_cycle_prompt_log()

        return _PreparedCyclePrompt(
            prompt=prompt,
            system_prompt=system_prompt,
            tracker=tracker,
            shortterm=shortterm,
            uses_chat_session=uses_chat_session,
            prompt_context=prompt_context,
        )

    async def _run_cycle_inner_scoped(
        self,
        prompt: str,
        trigger: str,
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        message_intent: str = "",
        thread_id: str = "default",
        model_config_override: ModelConfig | None = None,
        prompt_tier_override: str | None = None,
    ) -> CycleResult:
        start = time.monotonic()
        active_model_config = model_config_override or self.model_config
        active_executor = (
            self._create_executor(active_model_config) if model_config_override is not None else self._executor
        )
        executor_config = getattr(active_executor, "_model_config", None)
        if isinstance(executor_config, ModelConfig):
            active_model_config = executor_config
        mode = self._resolve_execution_mode(active_model_config)
        from core.provider_cooldown import (
            format_cooldown_message,
            get_provider_cooldown,
            provider_key_for_model_config,
        )

        provider_key = provider_key_for_model_config(active_model_config)
        provider_cooldown = get_provider_cooldown(provider_key)
        logger.info(
            "run_cycle START trigger=%s prompt_len=%d mode=%s",
            trigger,
            len(prompt),
            mode,
        )
        if provider_cooldown is not None:
            summary = format_cooldown_message(provider_cooldown)
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "Provider cooldown preflight blocked blocking execution: provider=%s trigger=%s remaining=%.1fs",
                provider_cooldown.provider,
                trigger,
                provider_cooldown.remaining_s,
            )
            return CycleResult(
                trigger=trigger,
                action="error",
                summary=summary,
                duration_ms=duration_ms,
            )

        prepared_prompt = await self._prepare_cycle_prompt(
            prompt,
            trigger,
            message_intent=message_intent,
            thread_id=thread_id,
            prior_messages=prior_messages,
            active_model_config=active_model_config,
            active_executor=active_executor,
            mode=mode,
            save_prompt_log_after_preflight=False,
            prompt_tier_override=prompt_tier_override,
        )
        prompt = prepared_prompt.prompt
        system_prompt = prepared_prompt.system_prompt
        tracker = prepared_prompt.tracker
        shortterm = prepared_prompt.shortterm
        uses_chat_session = prepared_prompt.uses_chat_session

        try:
            result = await active_executor.execute(
                prompt=prompt,
                system_prompt=system_prompt,
                tracker=tracker,
                trigger=trigger,
                images=images,
                thread_id=thread_id,
                shortterm=(
                    shortterm
                    if uses_chat_session and getattr(active_executor, "saves_threshold_shortterm", False) is True
                    else None
                ),
                prior_messages=(
                    prior_messages if getattr(active_executor, "wants_structured_history", False) is True else None
                ),
            )
        except (Exception, asyncio.CancelledError) as exc:
            # Preserve usage observed before an interruption for every engine.
            observed = getattr(exc, "usage", None)
            if isinstance(observed, dict):
                await _await_if_needed(
                    _log_session_token_usage(
                        self.anima_dir,
                        model=active_model_config.model,
                        mode=mode,
                        trigger=trigger,
                        usage=observed,
                        duration_ms=int((time.monotonic() - start) * 1000),
                    )
                )
            raise

        return await self._finalize_engine_result(
            result=result,
            mode=mode,
            trigger=trigger,
            thread_id=thread_id,
            prompt=prompt,
            tracker=tracker,
            shortterm=shortterm,
            uses_chat_session=uses_chat_session,
            active_executor=active_executor,
            active_model_config=active_model_config,
            start=start,
        )

    async def _finalize_engine_result(
        self,
        *,
        result: ExecutionResult,
        mode: str,
        trigger: str,
        thread_id: str,
        prompt: str,
        tracker: ContextTracker,
        shortterm: ShortTermMemory,
        uses_chat_session: bool,
        active_executor: Any,
        active_model_config: ModelConfig,
        start: float,
    ) -> CycleResult:
        """Apply engine-independent postprocessing and build the cycle result."""
        from dataclasses import asdict

        if result.replied_to_from_transcript:
            self._tool_handler.merge_replied_to(result.replied_to_from_transcript)

        tool_records = [asdict(record) for record in result.tool_call_records]
        await _await_if_needed(
            _save_prompt_log_end(
                self.anima_dir,
                session_id=self._tool_handler.session_id,
                tool_call_count=len(tool_records),
            )
        )

        compaction_review_requested = False
        if result.force_chain and not tracker.threshold_exceeded:
            _request_background_review(self.anima_dir, "auto_compact")
            compaction_review_requested = True
            tracker.force_threshold()
            logger.info("Context auto-compact: forcing threshold_exceeded for session handoff")

        result_message = result.result_message
        session_id = getattr(result_message, "session_id", "") or ""
        reported_turns = getattr(result_message, "num_turns", 0)
        total_turns = reported_turns if isinstance(reported_turns, int) else 0

        if uses_chat_session and tracker.threshold_exceeded:
            if not compaction_review_requested:
                _request_background_review(self.anima_dir, "auto_compact")
            logger.info(
                "Session context at %.1f%% — saving shortterm for next message",
                tracker.usage_ratio * 100,
            )
            if getattr(active_executor, "saves_threshold_shortterm", False) is not True:
                await shortterm.aclear()
                await _save_handoff_shortterm(
                    shortterm,
                    result_text=result.text,
                    tool_records=result.tool_call_records,
                    session_id=session_id,
                    turn_count=total_turns,
                    trigger=trigger,
                    prompt=prompt,
                    tracker=tracker,
                )
            await asyncio.to_thread(active_executor.clear_session, trigger, thread_id)
        elif uses_chat_session and result.session_rotation_pending:
            await _save_handoff_shortterm(
                shortterm,
                result_text=result.text,
                tool_records=result.tool_call_records,
                session_id=session_id,
                turn_count=total_turns,
                trigger=trigger,
                prompt=prompt,
                tracker=tracker,
            )
            logger.info("Session rotation pending — saved shortterm for next turn")
        elif uses_chat_session:
            await shortterm.aclear()

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "run_cycle END trigger=%s duration_ms=%d response_len=%d",
            trigger,
            duration_ms,
            len(result.text),
        )
        usage = result.usage.to_dict() if result.usage else None
        await _await_if_needed(
            _log_session_token_usage(
                self.anima_dir,
                model=active_model_config.model,
                mode=mode,
                trigger=trigger,
                usage=usage,
                duration_ms=duration_ms,
                turns=total_turns,
            )
        )

        is_error = result.error is True
        error_reason = result.reason if isinstance(result.reason, str) else ""
        error_category = _resolve_error_category(error_reason, result.text) if is_error else None
        return CycleResult(
            trigger=trigger,
            action="error" if is_error else "responded",
            stop_kind="stream_error" if is_error else "normal",
            reason=(error_category or "unknown") if is_error else "",
            error_category=error_category,
            summary=result.text,
            duration_ms=duration_ms,
            context_usage_ratio=tracker.usage_ratio,
            context_window=tracker.context_window,
            context_threshold=tracker.threshold,
            total_turns=total_turns,
            tool_call_records=tool_records,
            usage=usage,
            truncated=result.truncated is True,
        )

    # ── Streaming ──────────────────────────────────────────

    async def run_cycle_streaming(
        self,
        prompt: str,
        trigger: str = "manual",
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        message_intent: str = "",
        thread_id: str = "default",
        model_config_override: ModelConfig | None = None,
        prompt_tier_override: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Streaming version of run_cycle.

        Yields stream chunks. Session chaining is handled seamlessly.
        Final event is ``{"type": "cycle_done", "cycle_result": {...}}``.
        """
        from core.infra.logging_config import bind_cycle_context, clear_cycle_context

        # Correlate every log line emitted during this cycle. Tokens restore any
        # outer cycle's context so nested cycles don't leak their id upward.
        cycle_tokens = bind_cycle_context(uuid4().hex[:8], trigger)
        try:
            session_type = resolve_runtime_session_type(trigger)
            ctx = RuntimeSessionContext.create(
                session_type=session_type,
                thread_id=thread_id,
                trigger=trigger,
            )
            async with self._get_agent_lock(thread_id):
                budget_result = await _await_if_needed(
                    self._check_monthly_token_budget(
                        trigger=trigger,
                        model_config=self.model_config,
                    )
                )
                if budget_result is not None:
                    budget_result.session_type = ctx.session_type
                    budget_result.thread_id = ctx.thread_id
                    budget_result.request_id = ctx.request_id
                    yield {
                        "type": "cycle_done",
                        "cycle_result": budget_result.model_dump(mode="json"),
                    }
                    return
                primary_config, active_override = self._cycle_preflight_config(model_config_override, trigger)
                with runtime_session_scope(ctx):
                    self._tool_handler.bind_runtime_session(ctx)
                    token = self._tool_handler.set_active_session_type(session_type)
                    try:
                        async for chunk in self._run_cycle_streaming_inner(
                            prompt,
                            trigger,
                            images=images,
                            prior_messages=prior_messages,
                            message_intent=message_intent,
                            thread_id=thread_id,
                            model_config_override=active_override,
                            prompt_tier_override=prompt_tier_override,
                            primary_config=primary_config,
                        ):
                            if chunk.get("type") == "cycle_done":
                                cycle_result = chunk.get("cycle_result")
                                if isinstance(cycle_result, dict):
                                    cycle_result["trigger"] = ctx.trigger
                                    cycle_result["session_type"] = ctx.session_type
                                    cycle_result["thread_id"] = ctx.thread_id
                                    cycle_result["request_id"] = ctx.request_id
                                    cycle_result["tool_session_id"] = ctx.tool_session_id
                            yield chunk
                    finally:
                        from core.tooling.handler import active_session_type

                        try:
                            active_session_type.reset(token)
                        except (TypeError, ValueError):
                            pass
        finally:
            clear_cycle_context(cycle_tokens)

    async def _run_cycle_streaming_inner(
        self,
        prompt: str,
        trigger: str = "manual",
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        message_intent: str = "",
        thread_id: str = "default",
        model_config_override: ModelConfig | None = None,
        prompt_tier_override: str | None = None,
        primary_config: ModelConfig | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Streaming implementation scoped by ``run_cycle_streaming``."""
        start = time.monotonic()
        original_task_prompt = prompt
        active_model_config = model_config_override or self.model_config
        if primary_config is None:
            primary_config = active_model_config
        active_executor = (
            self._create_executor(active_model_config) if model_config_override is not None else self._executor
        )
        executor_config = getattr(active_executor, "_model_config", None)
        if isinstance(executor_config, ModelConfig):
            active_model_config = executor_config
        mode = self._resolve_execution_mode(active_model_config)
        from core.provider_cooldown import (
            format_cooldown_message,
            get_provider_cooldown,
            provider_key_for_model_config,
            record_provider_rate_limit,
        )

        provider_key = provider_key_for_model_config(active_model_config)
        provider_cooldown = get_provider_cooldown(provider_key)
        logger.info(
            "run_cycle_streaming START trigger=%s prompt_len=%d mode=%s",
            trigger,
            len(prompt),
            mode,
        )
        if provider_cooldown is not None:
            terminal_error_message = format_cooldown_message(provider_cooldown)
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.warning(
                "Provider cooldown preflight blocked execution: provider=%s trigger=%s remaining=%.1fs",
                provider_cooldown.provider,
                trigger,
                provider_cooldown.remaining_s,
            )
            yield {"type": "error", "message": terminal_error_message}
            yield {
                "type": "cycle_done",
                "cycle_result": CycleResult(
                    trigger=trigger,
                    action="error",
                    summary=terminal_error_message,
                    duration_ms=duration_ms,
                ).model_dump(mode="json"),
            }
            return

        # Non-streaming executors: fall back to blocking execution
        if not active_executor.supports_streaming:
            cycle = await self._run_cycle_inner_scoped(
                prompt,
                trigger,
                images=images,
                prior_messages=prior_messages,
                message_intent=message_intent,
                thread_id=thread_id,
                model_config_override=model_config_override,
                prompt_tier_override=prompt_tier_override,
            )
            yield {"type": "text_delta", "text": cycle.summary}
            yield {
                "type": "cycle_done",
                "cycle_result": cycle.model_dump(mode="json"),
            }
            return

        prepared_prompt = await self._prepare_cycle_prompt(
            prompt,
            trigger,
            message_intent=message_intent,
            thread_id=thread_id,
            prior_messages=prior_messages,
            active_model_config=active_model_config,
            active_executor=active_executor,
            mode=mode,
            save_prompt_log_after_preflight=True,
            prompt_tier_override=prompt_tier_override,
        )
        prompt = prepared_prompt.prompt
        system_prompt = prepared_prompt.system_prompt
        tracker = prepared_prompt.tracker
        shortterm = prepared_prompt.shortterm
        uses_chat_session = prepared_prompt.uses_chat_session
        prompt_context = prepared_prompt.prompt_context

        # ── Stream retry configuration ────────────────────
        retry_cfg = self._load_stream_retry_config()
        checkpoint_enabled = retry_cfg["checkpoint_enabled"]
        max_retries = retry_cfg["retry_max"]
        retry_delay = retry_cfg["retry_delay_s"]

        # Primary session with checkpoint + retry support
        full_text_parts: list[str] = []
        thinking_text_parts: list[str] = []
        all_tool_call_records: list[dict] = []
        result_message: Any = None
        _stream_force_chain = False
        rotation_pending = False
        _stream_usage: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }
        terminal_error_message = ""
        terminal_error_reason = ""
        terminal_error_chunk: dict[str, Any] | None = None
        fallback_swapped = False
        stream_started_work = False
        stream_stop_kind = "normal"
        stream_truncated = False
        current_prompt = prompt
        current_system_prompt = system_prompt
        retry_count = 0
        task_compaction_enabled = trigger.startswith("task:") and active_model_config.task_compaction_tokens > 0
        task_compaction_count = 0
        task_resume_session_id: str | None = None
        task_compaction_after_pending: int | None = None

        # Meeting turns hide the completion sentinel from the live stream. The
        # sentinel can arrive split across text_delta chunks, so we hold back a
        # tail that could be the start of the sentinel until we see more text.
        _is_meeting_turn = prompt_context.prompt_profile == PROMPT_PROFILE_MEETING
        _mtg_carry = ""
        _sentinel_seen = False

        def _filter_meeting_delta(text: str) -> str:
            """For meeting turns, strip the sentinel from a live text_delta, holding
            back any tail that might be a partial sentinel for the next chunk."""
            nonlocal _mtg_carry
            if not _is_meeting_turn:
                return text
            buf = _mtg_carry + text
            buf = buf.replace(MEETING_DONE_SENTINEL, "")
            for hold in range(len(MEETING_DONE_SENTINEL) - 1, 0, -1):
                if buf.endswith(MEETING_DONE_SENTINEL[:hold]):
                    _mtg_carry = buf[-hold:]
                    return buf[:-hold]
            _mtg_carry = ""
            return buf

        while True:
            completed_tools: list[dict[str, Any]] = []
            text_parts_this_attempt: list[str] = []
            stream_succeeded = False
            attempt_usage: dict[str, int] = {}
            attempt_started = time.monotonic()
            attempt_turns = 0
            attempt_task_compact_requested = False

            def record_usage(usage: dict[str, int] | None, acc: dict[str, int] = attempt_usage) -> None:
                _merge_stream_usage(_stream_usage, usage)
                _merge_stream_usage(acc, usage)

            try:
                self._active_streaming_executor = active_executor
                try:
                    stream_kwargs: dict[str, Any] = {}
                    if task_compaction_enabled and callable(getattr(active_executor, "compact_session_by_id", None)):
                        stream_kwargs = {
                            "task_compaction_count": task_compaction_count,
                            "resume_session_id": task_resume_session_id,
                        }
                    async for chunk in active_executor.execute_streaming(
                        current_system_prompt,
                        current_prompt,
                        tracker,
                        images=images,
                        prior_messages=prior_messages,
                        trigger=trigger,
                        thread_id=thread_id,
                        **stream_kwargs,
                    ):
                        if chunk["type"] in {"tool_start", "tool_end"} or (
                            chunk["type"] == "text_delta" and chunk.get("text")
                        ):
                            stream_started_work = True
                        if self._progress_callback:
                            self._progress_callback()
                        if chunk["type"] == "usage":
                            record_usage(chunk.get("usage"))
                        elif chunk["type"] == "done":
                            full_text_parts.append(chunk["full_text"])
                            text_parts_this_attempt.append(chunk["full_text"])
                            if _is_meeting_turn and MEETING_DONE_SENTINEL in chunk["full_text"]:
                                _sentinel_seen = True
                            result_message = chunk["result_message"]
                            all_tool_call_records.extend(chunk.get("tool_call_records", []))
                            if not chunk.get("usage_already_emitted"):
                                record_usage(chunk.get("usage"))
                            reported_turns = getattr(result_message, "num_turns", 0)
                            if isinstance(reported_turns, int):
                                attempt_turns = reported_turns
                            transcript_replied = chunk.get("replied_to_from_transcript", set())
                            if transcript_replied:
                                self._tool_handler.merge_replied_to(transcript_replied)
                            if chunk.get("force_chain", False):
                                _stream_force_chain = True
                            if chunk.get("session_rotation_pending", False):
                                rotation_pending = True
                            if chunk.get("task_compact_requested", False):
                                attempt_task_compact_requested = True
                            if chunk.get("truncated", False):
                                stream_truncated = True
                            stream_stop_kind = str(chunk.get("stop_kind") or "normal")
                            stream_succeeded = True
                        elif chunk["type"] == "error" and chunk.get("terminal") is True:
                            if not chunk.get("usage_already_emitted"):
                                record_usage(chunk.get("usage"))
                            all_tool_call_records.extend(chunk.get("tool_call_records", []))
                            terminal_error_message = chunk.get("message", "[Terminal LLM error]")
                            terminal_error_reason = str(chunk.get("reason") or "")
                            # Held back until the fallback decision below: a
                            # successful model swap must not surface an error.
                            terminal_error_chunk = chunk
                        elif chunk["type"] == "tool_end" and checkpoint_enabled:
                            record = chunk.get("record")
                            summary = (getattr(record, "result_summary", "") if record else "") or chunk.get(
                                "tool_name", "unknown"
                            )
                            completed_tools.append(
                                {
                                    "tool_name": chunk.get("tool_name", ""),
                                    "tool_id": chunk.get("tool_id", ""),
                                    "summary": summary,
                                }
                            )
                            from core.memory.conversation.shortterm import StreamCheckpoint

                            await shortterm.asave_checkpoint(
                                StreamCheckpoint(
                                    timestamp=now_iso(),
                                    trigger=trigger,
                                    original_prompt=prompt,
                                    completed_tools=completed_tools,
                                    accumulated_text="\n".join(full_text_parts),
                                    retry_count=retry_count,
                                )
                            )
                            yield chunk
                        else:
                            if chunk["type"] == "text_delta":
                                _delta_text = chunk.get("text", "")
                                text_parts_this_attempt.append(_delta_text)
                                if _is_meeting_turn:
                                    _emit = _filter_meeting_delta(_delta_text)
                                    if _emit:
                                        yield {**chunk, "text": _emit}
                                    continue
                            elif chunk["type"] == "thinking_delta":
                                thinking_text_parts.append(chunk.get("text", ""))
                            if chunk["type"] == "context_update" and task_compaction_after_pending is not None:
                                from core.activity.logger import ActivityLogger

                                await ActivityLogger(self.anima_dir).alog(
                                    "task_compacted_after",
                                    summary=t("task.compacted_after_activity_summary"),
                                    meta={
                                        "task_id": trigger.removeprefix("task:"),
                                        "tokens_after": chunk.get("input_tokens", 0),
                                        "compaction_number": task_compaction_after_pending,
                                    },
                                    safe=True,
                                )
                                logger.info(
                                    "Task context compaction resumed (task_id=%s, compaction=%d, tokens_after=%d)",
                                    trigger.removeprefix("task:"),
                                    task_compaction_after_pending,
                                    chunk.get("input_tokens", 0),
                                )
                                task_compaction_after_pending = None
                            yield chunk
                finally:
                    if self._active_streaming_executor is active_executor:
                        self._active_streaming_executor = None

            except (asyncio.CancelledError, GeneratorExit) as exc:
                observed = getattr(exc, "usage", None)
                if isinstance(observed, dict) and not getattr(exc, "usage_already_emitted", False):
                    record_usage(observed)
                raise
            except Exception as e:
                observed = getattr(e, "usage", None)
                if isinstance(observed, dict) and not getattr(e, "usage_already_emitted", False):
                    record_usage(observed)
                records = getattr(e, "tool_call_records", None)
                if isinstance(records, list):
                    all_tool_call_records.extend(records)
                from core.execution.base import StreamDisconnectedError

                is_stream_error = isinstance(e, StreamDisconnectedError)
                fallback_eligible = True
                if is_stream_error:
                    from core.llm.guard.error_classifier import FailoverReason, classify_llm_error

                    cause = e.__cause__ if isinstance(e.__cause__, Exception) else e
                    classified, hint = classify_llm_error(cause)
                    # API adapters wrap even a failed connection before the
                    # first response as a stream disconnect. Their own API
                    # retry budget is already exhausted: do not multiply it
                    # by the stream retry budget or lose its provider reason.
                    can_route = (
                        hint.fallback_ok
                        and getattr(primary_config, "fallback_models", None)
                        and not stream_started_work
                        and not all_tool_call_records
                    )
                    if classified != FailoverReason.UNKNOWN and (hint.is_terminal or can_route):
                        is_stream_error = False
                        terminal_error_reason = classified.value
                        fallback_eligible = hint.fallback_ok
                if not is_stream_error:
                    # Non-stream errors are not eligible for stream retries.
                    logger.exception("Agent SDK streaming error (non-retryable)")
                    terminal_error_message = f"[Agent SDK Error: {e}]"
                    if fallback_eligible and not fallback_swapped and getattr(primary_config, "fallback_models", None):
                        from core.execution.fallback_activity import runtime_fallback_config

                        swap_config = runtime_fallback_config(
                            self.anima_dir,
                            primary_config,
                            active_model_config,
                            error_text=terminal_error_message,
                            reason=terminal_error_reason,
                            channel=self._cycle_fallback_channel(trigger),
                            partial_execution=stream_started_work or bool(all_tool_call_records),
                        )
                        if swap_config is not None:
                            logger.warning(
                                "Terminal LLM error on %s → retrying with fallback %s",
                                active_model_config.model,
                                swap_config.model,
                            )
                            fallback_swapped = True
                            active_model_config = swap_config
                            active_executor = self._create_executor(swap_config)
                            mode = self._resolve_execution_mode(active_model_config)
                            provider_key = provider_key_for_model_config(active_model_config)
                            terminal_error_message = ""
                            terminal_error_reason = ""
                            current_prompt = prompt
                            tracker.reset()
                            current_system_prompt = self._compose_system_prompt(
                                prompt_context, execution_mode=mode
                            ).system_prompt
                            yield {
                                "type": "retry_start",
                                "retry": retry_count,
                                "max_retries": max_retries,
                                "fallback_model": swap_config.model,
                            }
                            continue
                    yield {"type": "error", "message": terminal_error_message}
                    break

                # ── Stream disconnect: attempt retry ──────────
                partial_text = getattr(e, "partial_text", "") or ""
                if partial_text:
                    full_text_parts.append(partial_text)

                if getattr(e, "category", None) == "rate_limit":
                    cooldown = record_provider_rate_limit(
                        provider_key,
                        retry_after_s=getattr(e, "retry_after_s", None),
                        trigger=trigger,
                        model=active_model_config.model,
                        reason=str(e),
                    )
                    if cooldown is not None:
                        terminal_error_message = format_cooldown_message(cooldown)
                    else:
                        terminal_error_message = "RATE_LIMIT_DEFERRED: provider returned HTTP 429/RATE_LIMIT_EXCEEDED"
                    logger.error(
                        "Provider rate limit deferred execution: provider=%s trigger=%s retry_after=%s",
                        provider_key,
                        trigger,
                        getattr(e, "retry_after_s", None),
                    )
                    yield {
                        "type": "error",
                        "message": terminal_error_message,
                    }
                    break

                if retry_count >= max_retries:
                    if getattr(e, "category", None) == "rate_limit":
                        terminal_error_message = (
                            f"RATE_LIMIT: provider returned HTTP 429/RATE_LIMIT_EXCEEDED "
                            f"after {retry_count} retry attempt(s): {e}"
                        )
                    else:
                        terminal_error_message = t("agent.stream_retry_exhausted", retry_count=retry_count)
                    logger.error(
                        "Stream retry exhausted (%d/%d)",
                        retry_count,
                        max_retries,
                    )
                    yield {
                        "type": "error",
                        "message": terminal_error_message,
                    }
                    break

                retry_count += 1
                skip_delay = getattr(e, "immediate_retry", False)
                retry_after_s = getattr(e, "retry_after_s", None)
                if retry_after_s is not None:
                    actual_delay = max(retry_delay, float(retry_after_s) + _STREAM_RETRY_AFTER_BUFFER_S)
                    retry_reason = f" (retry-after: {float(retry_after_s):.1f}s)"
                elif skip_delay:
                    actual_delay = 0.5
                    retry_reason = " (immediate: buffer overflow)"
                else:
                    actual_delay = retry_delay
                    retry_reason = ""
                if getattr(e, "category", None) == "rate_limit":
                    logger.warning(
                        "Provider rate limit, retrying %d/%d after %.1fs%s",
                        retry_count,
                        max_retries,
                        actual_delay,
                        retry_reason,
                    )
                else:
                    logger.warning(
                        "Stream disconnected, retrying %d/%d after %.1fs%s",
                        retry_count,
                        max_retries,
                        actual_delay,
                        retry_reason,
                    )
                    # リトライ1回目は必ずfresh session（壊れたセッションIDを持ち越さない）
                    if retry_count == 1:
                        try:
                            if uses_chat_session:
                                await asyncio.to_thread(active_executor.clear_session, trigger, thread_id)
                            logger.info("Session IDs cleared for retry 1 (fresh session forced)")
                        except Exception as e:
                            logger.warning("Failed to clear session IDs for retry: %s", e)
                    yield {
                        "type": "retry_start",
                        "retry": retry_count,
                        "max_retries": max_retries,
                    }

                    # Load checkpoint and build retry prompt
                    from core.execution._shortterm_handoff import build_stream_retry_prompt
                    from core.memory.conversation.shortterm import StreamCheckpoint

                    checkpoint = shortterm.load_checkpoint()
                    if checkpoint is None:
                        checkpoint = StreamCheckpoint(
                            timestamp=now_iso(),
                            trigger=trigger,
                            original_prompt=prompt,
                            completed_tools=completed_tools,
                            accumulated_text="\n".join(full_text_parts),
                            retry_count=retry_count,
                        )

                    checkpoint.retry_count = retry_count
                    current_prompt = build_stream_retry_prompt(checkpoint)

                    # Reset tracker for fresh session
                    tracker.reset()
                    current_system_prompt = self._compose_system_prompt(prompt_context).system_prompt

                checkpoint.retry_count = retry_count
                current_prompt = build_stream_retry_prompt(checkpoint)
                tracker.reset()
                current_system_prompt = self._compose_system_prompt(prompt_context, execution_mode=mode).system_prompt

                await asyncio.sleep(actual_delay)
                continue
            finally:
                # Flush each execution attempt under its actual model/mode,
                # including failures, cancellation and generator close. A
                # fallback can use a different provider's token semantics.
                await _await_if_needed(
                    _log_session_token_usage(
                        self.anima_dir,
                        model=active_model_config.model,
                        mode=mode,
                        trigger=trigger,
                        usage=attempt_usage,
                        duration_ms=int((time.monotonic() - attempt_started) * 1000),
                        turns=attempt_turns,
                    )
                )

            if (
                attempt_task_compact_requested
                and stream_succeeded
                and task_compaction_enabled
                and task_compaction_count < active_model_config.task_compaction_max
            ):
                task_compaction_count += 1
                _request_background_review(self.anima_dir, "auto_compact")
                session_id = getattr(result_message, "session_id", None) or chunk.get("session_id")
                compacted = False
                compact_fn = getattr(active_executor, "compact_session_by_id", None)
                if session_id and callable(compact_fn):
                    try:
                        compacted = await compact_fn(
                            session_id,
                            system_prompt=current_system_prompt,
                            trigger=trigger,
                            summary_instructions=t("task.compaction_summary_instructions"),
                        )
                    except Exception:
                        logger.exception(
                            "Task context compaction call failed (task_id=%s, compaction=%d)",
                            trigger.removeprefix("task:"),
                            task_compaction_count,
                        )
                logger.info(
                    "Task context compaction attempt %s (task_id=%s, compaction=%d, tokens_before=%d)",
                    "succeeded" if compacted else "failed",
                    trigger.removeprefix("task:"),
                    task_compaction_count,
                    tracker._input_tokens,
                )
                try:
                    from core.activity.logger import ActivityLogger

                    await ActivityLogger(self.anima_dir).alog(
                        "task_compacted",
                        summary=t("task.compacted_activity_summary"),
                        meta={
                            "task_id": trigger.removeprefix("task:"),
                            "tokens_before": tracker._input_tokens,
                            "compaction_number": task_compaction_count,
                            "success": compacted,
                        },
                        safe=True,
                    )
                except Exception:
                    logger.warning("Failed to record task_compacted activity", exc_info=True)

                if session_id:
                    task_resume_session_id = session_id
                    current_prompt = t(
                        "task.compaction_continue_prompt",
                        original_prompt=original_task_prompt,
                    )
                    tracker.reset()
                    task_compaction_after_pending = task_compaction_count
                    continue
                logger.warning(
                    "Cannot resume task after compaction request because SDK session id is missing (task_id=%s)",
                    trigger.removeprefix("task:"),
                )

            if terminal_error_message and not fallback_swapped and getattr(primary_config, "fallback_models", None):
                from core.execution.fallback_activity import runtime_fallback_config

                swap_config = runtime_fallback_config(
                    self.anima_dir,
                    primary_config,
                    active_model_config,
                    error_text=terminal_error_message,
                    reason=terminal_error_reason,
                    channel=self._cycle_fallback_channel(trigger),
                    partial_execution=stream_started_work or bool(all_tool_call_records),
                )
                if swap_config is not None:
                    logger.warning(
                        "Terminal LLM error on %s → retrying with fallback %s",
                        active_model_config.model,
                        swap_config.model,
                    )
                    fallback_swapped = True
                    active_model_config = swap_config
                    active_executor = self._create_executor(swap_config)
                    mode = self._resolve_execution_mode(active_model_config)
                    provider_key = provider_key_for_model_config(active_model_config)
                    terminal_error_message = ""
                    terminal_error_reason = ""
                    terminal_error_chunk = None
                    current_prompt = prompt
                    tracker.reset()
                    current_system_prompt = self._compose_system_prompt(
                        prompt_context,
                        execution_mode=mode,
                    ).system_prompt
                    yield {
                        "type": "retry_start",
                        "retry": retry_count,
                        "max_retries": max_retries,
                        "fallback_model": swap_config.model,
                    }
                    continue

            if stream_succeeded or terminal_error_message:
                # A structured terminal provider error is a completed failure,
                # not a disconnected stream eligible for retry.
                if terminal_error_chunk is not None:
                    yield terminal_error_chunk
                await shortterm.aclear_checkpoint()
                break

        # ── Meeting continuation guard ────────────────────
        # A meeting turn can end on a bare acknowledgement ("I'll check") because
        # the Agent SDK closes a turn on any text-only message. If the model has
        # not yet signalled completion (sentinel absent), re-invoke it in the same
        # resumable session with a nudge to actually deliver findings, bounded by
        # a small retry cap.
        if _is_meeting_turn and not terminal_error_message and getattr(active_executor, "supports_streaming", True):
            _mtg_cont = 0
            while (
                not _sentinel_seen
                and _mtg_cont < _MEETING_CONT_MAX_RETRIES
                and (time.monotonic() - start) < _MEETING_CONT_DEADLINE_S
            ):
                _mtg_cont += 1
                nudge = t("agent.meeting_continue_nudge", sentinel=MEETING_DONE_SENTINEL)
                logger.info(
                    "Meeting continuation nudge %d/%d (no findings yet) trigger=%s",
                    _mtg_cont,
                    _MEETING_CONT_MAX_RETRIES,
                    trigger,
                )
                yield {"type": "meeting_continue", "attempt": _mtg_cont}
                _cont_done = False
                try:
                    async for chunk in active_executor.execute_streaming(
                        current_system_prompt,
                        nudge,
                        tracker,
                        images=None,
                        prior_messages=None,
                        trigger=trigger,
                        thread_id=thread_id,
                    ):
                        if self._progress_callback:
                            self._progress_callback()
                        if chunk["type"] == "done":
                            full_text_parts.append(chunk["full_text"])
                            if MEETING_DONE_SENTINEL in chunk["full_text"]:
                                _sentinel_seen = True
                            result_message = chunk["result_message"]
                            all_tool_call_records.extend(chunk.get("tool_call_records", []))
                            _merge_stream_usage(_stream_usage, chunk.get("usage"))
                            transcript_replied = chunk.get("replied_to_from_transcript", set())
                            if transcript_replied:
                                self._tool_handler.merge_replied_to(transcript_replied)
                            if chunk.get("truncated", False):
                                stream_truncated = True
                            _cont_done = True
                        elif chunk["type"] == "text_delta":
                            _emit = _filter_meeting_delta(chunk.get("text", ""))
                            if _emit:
                                yield {**chunk, "text": _emit}
                        elif chunk["type"] == "thinking_delta":
                            thinking_text_parts.append(chunk.get("text", ""))
                            yield chunk
                        else:
                            yield chunk
                except Exception:
                    logger.warning("Meeting continuation stream failed", exc_info=True)
                    break
                if not _cont_done:
                    break

        if not uses_chat_session:
            await shortterm.aclear_checkpoint()

        total_turns = result_message.num_turns if result_message else 0

        # Session chaining — force_chain from mid-session auto-compact.
        compaction_review_requested = False
        if _stream_force_chain and not tracker.threshold_exceeded:
            _request_background_review(self.anima_dir, "auto_compact")
            compaction_review_requested = True
            tracker.force_threshold()
            logger.info("Context auto-compact (stream): forcing threshold_exceeded")

        if tracker.threshold_exceeded and uses_chat_session:
            if not compaction_review_requested:
                _request_background_review(self.anima_dir, "auto_compact")
            # Defer continuation until the next message rather than chaining mid-response.
            logger.info(
                "Session context at %.1f%% — saving shortterm, will resume on next message (stream)",
                tracker.usage_ratio * 100,
            )
            await shortterm.aclear()
            await _save_handoff_shortterm(
                shortterm,
                result_text="\n".join(full_text_parts),
                tool_records=all_tool_call_records,
                session_id=getattr(result_message, "session_id", "") or "",
                turn_count=total_turns,
                trigger=trigger,
                prompt=prompt,
                tracker=tracker,
            )
            await asyncio.to_thread(active_executor.clear_session, trigger, thread_id)
        elif uses_chat_session and rotation_pending:
            await _save_handoff_shortterm(
                shortterm,
                result_text="\n".join(full_text_parts),
                tool_records=all_tool_call_records,
                session_id=getattr(result_message, "session_id", "") or "",
                turn_count=total_turns,
                trigger=trigger,
                prompt=prompt,
                tracker=tracker,
            )
        elif uses_chat_session:
            await shortterm.aclear()

        await _await_if_needed(
            _save_prompt_log_end(
                self.anima_dir,
                session_id=self._tool_handler.session_id,
                tool_call_count=len(all_tool_call_records),
            )
        )

        full_text = "\n".join(full_text_parts)
        if _is_meeting_turn:
            full_text = _strip_meeting_sentinel(full_text)
        thinking_text = "".join(thinking_text_parts)
        final_action = "error" if terminal_error_message else "responded"
        final_summary = full_text or terminal_error_message
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "run_cycle_streaming END trigger=%s duration_ms=%d response_len=%d retries=%d",
            trigger,
            duration_ms,
            len(full_text),
            retry_count,
        )

        _final_usage = _stream_usage if any(_stream_usage.values()) else None
        yield {
            "type": "cycle_done",
            "cycle_result": CycleResult(
                trigger=trigger,
                action=final_action,
                stop_kind="stream_error" if terminal_error_message else stream_stop_kind,
                summary=final_summary,
                reason=terminal_error_reason,
                error_category=_resolve_error_category(terminal_error_reason, terminal_error_message),
                thread_id=thread_id,
                thinking_text=thinking_text[:10000],
                duration_ms=duration_ms,
                context_usage_ratio=tracker.usage_ratio,
                context_window=tracker.context_window,
                context_threshold=tracker.threshold,
                total_turns=total_turns,
                tool_call_records=all_tool_call_records,
                # Preserve the inner-cycle replay guard across IPC and the
                # outer fallback wrapper, even if a failed stream never
                # produced its final tool records. Text already delivered is
                # also conservatively treated as started work, as above.
                fallback_safe=not (stream_started_work or all_tool_call_records),
                usage=_final_usage,
                truncated=stream_truncated,
            ).model_dump(mode="json"),
        }
