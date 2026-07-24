from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CycleMixin -- blocking and streaming execution cycles.

Extracted from ``core.agent.AgentCore`` as a Mixin.  All ``self`` references
are resolved at runtime via MRO when mixed into ``AgentCore``.
"""

import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

    from core.execution.base import ExecutionResult

from core._agent_prompt_log import _save_prompt_log, _save_prompt_log_end
from core.execution.session_context import RuntimeSessionContext, runtime_session_scope
from core.execution.session_types import is_clean_start_session, resolve_runtime_session_type, trigger_uses_chat_session
from core.i18n import t
from core.memory.shortterm import SessionState, ShortTermMemory
from core.prompt.builder import (
    MEETING_DONE_SENTINEL,
    PROMPT_PROFILE_MEETING,
    TIER_MICRO,
    build_system_prompt,
    inject_shortterm,
)
from core.prompt.context import CHARS_PER_TOKEN, ContextTracker
from core.schemas import CycleResult, ImageData, ModelConfig
from core.time_utils import now_iso, now_local

logger = logging.getLogger("animaworks.agent")


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


def _update_tracker_from_prompt_estimate(
    tracker: ContextTracker,
    system_prompt: str,
    prompt: str,
) -> None:
    estimated_tokens = (len(system_prompt) + len(prompt)) // CHARS_PER_TOKEN
    tracker.update({"input_tokens": estimated_tokens}, include_output_in_ratio=False)


def _merge_stream_usage(acc: dict[str, int], chunk_usage: dict[str, int] | None) -> None:
    """Accumulate chunk usage into the streaming accumulator dict."""
    if not chunk_usage:
        return
    for k in _USAGE_KEYS:
        acc[k] = acc.get(k, 0) + (chunk_usage.get(k, 0) or 0)


def _log_session_token_usage(
    anima_dir: Path,
    *,
    model: str,
    mode: str,
    trigger: str,
    usage: dict[str, int] | None,
    duration_ms: int = 0,
    turns: int = 0,
    chains: int = 0,
) -> None:
    """Fire-and-forget token usage log entry."""
    if not usage or not any(usage.values()):
        return
    try:
        from core.memory.token_usage import TokenUsageLogger

        tul = TokenUsageLogger(anima_dir)
        tul.log(
            model=model,
            trigger=trigger,
            mode=mode,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            cache_read_tokens=usage.get("cache_read_tokens", 0),
            cache_write_tokens=usage.get("cache_write_tokens", 0),
            turns=turns,
            chains=chains,
            duration_ms=duration_ms,
        )
    except Exception:
        logger.debug("Failed to log token usage", exc_info=True)


class CycleMixin:
    """Mixin: blocking and streaming execution cycles + session chaining."""

    def _check_monthly_token_budget(
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
            from core.memory.token_budget import calculate_token_budget_status
            from core.memory.token_usage import TokenUsageLogger

            consumed = TokenUsageLogger(self.anima_dir).monthly_total(now)
            status = calculate_token_budget_status(budget, consumed)
        except Exception as exc:
            logger.warning(
                "Failed to check monthly token budget for %s; blocking cycle",
                self.anima_dir.name,
                exc_info=True,
            )
            try:
                from core.memory.activity import ActivityLogger

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
            from core.memory.activity import ActivityLogger

            ActivityLogger(self.anima_dir).log(
                "budget_exceeded",
                summary="Monthly token budget reached; LLM cycle skipped",
                meta=meta,
                safe=True,
            )
        except Exception:
            logger.warning("Failed to record budget_exceeded activity", exc_info=True)

        self._write_budget_exceeded_notification(meta)
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
            summary="Monthly token budget reached; LLM cycle skipped",
        )

    def _write_budget_exceeded_notification(self, meta: dict[str, Any]) -> None:
        """Write the owner notification at most once for each calendar month."""
        month = str(meta["month"])
        marker_dir = self.anima_dir / "state" / "token_budget_notifications"
        marker_path = marker_dir / f"{month}.notified"
        marker_created = False
        try:
            marker_dir.mkdir(parents=True, exist_ok=True)
            # Exclusive creation makes duplicate suppression safe across lanes
            # or processes that reach the cap concurrently.
            with marker_path.open("x", encoding="utf-8") as marker:
                marker.write(now_iso() + "\n")
            marker_created = True

            notif_dir = self.anima_dir / "state" / "background_notifications"
            notif_dir.mkdir(parents=True, exist_ok=True)
            notif_path = notif_dir / f"token_budget_exceeded_{month}.md"
            notif_path.write_text(
                "# Monthly token budget reached\n\n"
                f"- month: {month}\n"
                f"- budget: {meta['budget']}\n"
                f"- consumed: {meta['consumed']}\n"
                f"- trigger: {meta['trigger']}\n",
                encoding="utf-8",
            )
        except FileExistsError:
            return
        except Exception:
            if marker_created:
                try:
                    marker_path.unlink()
                except OSError:
                    pass
            logger.warning("Failed to write token budget notification", exc_info=True)

    def _prepare_clean_start_session(
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
            shortterm.clear_for_clean_start()
        except Exception:
            logger.debug("Failed to clear non-chat shortterm state", exc_info=True)

        try:
            from core.execution._sdk_session import clear_session_id_for_type

            clear_session_id_for_type(self.anima_dir, session_type, thread_id)
        except Exception:
            logger.debug("Failed to clear non-chat SDK session ID", exc_info=True)

        try:
            from core.execution.codex_sdk import clear_codex_thread_id

            clear_codex_thread_id(self.anima_dir, session_type, thread_id)
        except Exception:
            logger.debug("Failed to clear non-chat Codex thread ID", exc_info=True)

        try:
            from core.execution.grok_cli import _clear_session_id as clear_grok_session_id

            clear_grok_session_id(self.anima_dir, session_type, thread_id)
        except Exception:
            logger.debug("Failed to clear non-chat Grok session ID", exc_info=True)

    # ── Public API ─────────────────────────────────────────

    async def run_cycle(
        self,
        prompt: str,
        trigger: str = "manual",
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        message_intent: str = "",
        max_turns_override: int | None = None,
        thread_id: str = "default",
        model_config_override: ModelConfig | None = None,
        prompt_tier_override: str | None = None,
    ) -> CycleResult:
        """Run one agent cycle with autonomous memory search.

        Routing:
          - Mode B (basic):      ``AssistedExecutor``  -- text-based tool loop
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
        from core.logging_config import bind_cycle_context, clear_cycle_context

        # Correlate every log line emitted during this cycle. Tokens restore any
        # outer cycle's context so nested cycles don't leak their id upward.
        cycle_tokens = bind_cycle_context(uuid4().hex[:8], trigger)
        try:
            async with self._get_agent_lock(thread_id):
                budget_result = self._check_monthly_token_budget(
                    trigger=trigger,
                    model_config=self.model_config,
                )
                if budget_result is not None:
                    return budget_result
                return await self._run_cycle_inner(
                    prompt,
                    trigger,
                    images=images,
                    prior_messages=prior_messages,
                    message_intent=message_intent,
                    max_turns_override=max_turns_override,
                    thread_id=thread_id,
                    model_config_override=model_config_override,
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
        max_turns_override: int | None = None,
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
                    max_turns_override=max_turns_override,
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

    async def _run_cycle_inner_scoped(
        self,
        prompt: str,
        trigger: str,
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        message_intent: str = "",
        max_turns_override: int | None = None,
        thread_id: str = "default",
        model_config_override: ModelConfig | None = None,
        prompt_tier_override: str | None = None,
    ) -> CycleResult:
        start = time.monotonic()
        active_model_config = model_config_override or self.model_config
        active_executor = (
            self._create_executor(active_model_config) if model_config_override is not None else self._executor
        )
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

        # ── Resolve context window and prompt tier ────────────
        from core.prompt.builder import resolve_prompt_tier
        from core.prompt.context import resolve_context_window

        _ctx_window = resolve_context_window(
            active_model_config.model,
            overrides=self._load_context_window_overrides(),
        )
        _prompt_profile = PROMPT_PROFILE_MEETING if prompt_tier_override == PROMPT_PROFILE_MEETING else ""
        _prompt_tier = TIER_MICRO if _prompt_profile else prompt_tier_override or resolve_prompt_tier(_ctx_window)

        # ── Priming: Automatic memory retrieval ────────────────
        priming_section, pending_human_notifications = await self._run_priming(
            prompt,
            trigger,
            message_intent=message_intent,
            prompt_tier=_prompt_tier,
            model_config=active_model_config,
        )

        session_type = resolve_runtime_session_type(trigger)
        uses_chat_session = trigger_uses_chat_session(trigger)
        shortterm = ShortTermMemory(self.anima_dir, session_type=session_type, thread_id=thread_id)
        self._prepare_clean_start_session(
            trigger=trigger,
            session_type=session_type,
            thread_id=thread_id,
            shortterm=shortterm,
        )
        tracker = ContextTracker(
            model=active_model_config.model,
            threshold=active_model_config.context_threshold,
            context_window_overrides=self._load_context_window_overrides(),
        )

        build_result = build_system_prompt(
            self.memory,
            tool_registry=self._tool_registry,
            personal_tools=self._personal_tools,
            priming_section=priming_section,
            execution_mode=mode,
            message=prompt,
            retriever=self._get_retriever(),
            trigger=trigger,
            context_window=_ctx_window,
            pending_human_notifications=pending_human_notifications,
            thread_id=thread_id,
            prompt_tier=_prompt_tier,
            prompt_profile=_prompt_profile,
        )
        system_prompt = build_result.system_prompt
        logger.debug("System prompt assembled, length=%d tier=%s", len(system_prompt), _prompt_tier)

        # ── Context-window-aware tier downgrade ────────────
        system_prompt = self._fit_prompt_to_context_window(
            system_prompt,
            prompt,
            _ctx_window,
            priming_section=priming_section,
            mode=mode,
            trigger=trigger,
            pending_human_notifications=pending_human_notifications,
            thread_id=thread_id,
            prompt_tier=_prompt_tier,
            prompt_profile=_prompt_profile,
        )

        if uses_chat_session and shortterm.has_pending():
            system_prompt = inject_shortterm(system_prompt, shortterm)
            logger.info("Injected short-term memory into system prompt")

        # ── Prompt log: save full payload for debugging ───
        from core.tooling.schemas import load_all_tool_schemas

        _tool_schemas = load_all_tool_schemas(
            tool_registry=self._tool_registry,
            personal_tools=self._personal_tools,
        )
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
            context_window=_ctx_window,
            prior_messages=prior_messages,
            tool_schemas=_tool_schemas,
        )

        # ── Helper: convert ExecutionResult tool records to dicts ──
        def _tool_records_to_dicts(result: ExecutionResult) -> list[dict]:
            from dataclasses import asdict as _asdict

            return [_asdict(r) for r in result.tool_call_records]

        # ── Mode B: text-based tool-call loop ─────────────
        if mode == "b":
            result = await active_executor.execute(
                prompt=prompt,
                system_prompt=system_prompt,
                trigger=trigger,
                images=images,
                max_turns_override=max_turns_override,
                thread_id=thread_id,
            )
            _save_prompt_log_end(
                self.anima_dir,
                session_id=self._tool_handler.session_id,
                tool_call_count=len(result.tool_call_records),
            )
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "run_cycle END (mode-b) trigger=%s duration_ms=%d response_len=%d",
                trigger,
                duration_ms,
                len(result.text),
            )
            _b_usage = result.usage.to_dict() if result.usage else None
            _log_session_token_usage(
                self.anima_dir,
                model=active_model_config.model,
                mode="b",
                trigger=trigger,
                usage=_b_usage,
                duration_ms=duration_ms,
            )
            _b_action = (
                "error"
                if result.text.startswith("[Agent SDK Error:") or result.text.startswith("[Codex Error:")
                else "responded"
            )
            return CycleResult(
                trigger=trigger,
                action=_b_action,
                summary=result.text,
                duration_ms=duration_ms,
                context_window=tracker.context_window,
                context_threshold=tracker.threshold,
                tool_call_records=_tool_records_to_dicts(result),
                usage=_b_usage,
                truncated=result.truncated,
            )

        # ── Mode C: Codex SDK ─────────────────────────────
        if mode == "c":
            _update_tracker_from_prompt_estimate(tracker, system_prompt, prompt)
            result = await active_executor.execute(
                prompt=prompt,
                system_prompt=system_prompt,
                tracker=tracker,
                trigger=trigger,
                images=images,
                max_turns_override=max_turns_override,
                thread_id=thread_id,
            )
            if result.replied_to_from_transcript:
                self._tool_handler.merge_replied_to(result.replied_to_from_transcript)
            _save_prompt_log_end(
                self.anima_dir,
                session_id=self._tool_handler.session_id,
                tool_call_count=len(result.tool_call_records),
            )
            if tracker.threshold_exceeded and uses_chat_session:
                shortterm.clear()
                shortterm.save(
                    SessionState(
                        session_id=result.result_message.session_id if result.result_message else "",
                        timestamp=now_iso(),
                        trigger=trigger,
                        original_prompt=prompt,
                        accumulated_response=result.text,
                        context_usage_ratio=tracker.usage_ratio,
                        turn_count=result.result_message.num_turns if result.result_message else 0,
                    )
                )
                try:
                    from core.execution.codex_sdk import clear_codex_thread_ids

                    clear_codex_thread_ids(self.anima_dir, thread_id)
                except Exception:
                    logger.debug("Failed to clear Codex thread ID after Mode C threshold", exc_info=True)
            elif uses_chat_session:
                shortterm.clear()
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "run_cycle END (c) trigger=%s duration_ms=%d response_len=%d",
                trigger,
                duration_ms,
                len(result.text),
            )
            _c_usage = result.usage.to_dict() if result.usage else None
            _log_session_token_usage(
                self.anima_dir,
                model=active_model_config.model,
                mode="c",
                trigger=trigger,
                usage=_c_usage,
                duration_ms=duration_ms,
            )
            _c_action = (
                "error"
                if result.text.startswith("[Agent SDK Error:") or result.text.startswith("[Codex Error:")
                else "responded"
            )
            return CycleResult(
                trigger=trigger,
                action=_c_action,
                summary=result.text,
                duration_ms=duration_ms,
                context_usage_ratio=tracker.usage_ratio,
                context_window=tracker.context_window,
                context_threshold=tracker.threshold,
                tool_call_records=_tool_records_to_dicts(result),
                usage=_c_usage,
                truncated=result.truncated,
            )

        # ── Mode D: Cursor Agent CLI ─────────────────────
        if mode == "d":
            result = await active_executor.execute(
                prompt=prompt,
                system_prompt=system_prompt,
                tracker=tracker,
                trigger=trigger,
                images=images,
                max_turns_override=max_turns_override,
                thread_id=thread_id,
            )
            if result.replied_to_from_transcript:
                self._tool_handler.merge_replied_to(result.replied_to_from_transcript)
            _save_prompt_log_end(
                self.anima_dir,
                session_id=self._tool_handler.session_id,
                tool_call_count=len(result.tool_call_records),
            )
            if result.session_rotation_pending and uses_chat_session:
                from dataclasses import asdict as _d_asdict

                shortterm.save(
                    SessionState(
                        timestamp=now_iso(),
                        trigger=trigger,
                        original_prompt=prompt,
                        accumulated_response=result.text[-2000:] if result.text else "",
                        tool_uses=[_d_asdict(r) for r in result.tool_call_records],
                        turn_count=0,
                    )
                )
                logger.info("Mode D rotation pending — saved shortterm for next turn")
            elif uses_chat_session:
                shortterm.clear()
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "run_cycle END (d) trigger=%s duration_ms=%d response_len=%d",
                trigger,
                duration_ms,
                len(result.text),
            )
            _d_usage = result.usage.to_dict() if result.usage else None
            _log_session_token_usage(
                self.anima_dir,
                model=active_model_config.model,
                mode="d",
                trigger=trigger,
                usage=_d_usage,
                duration_ms=duration_ms,
            )
            _d_action = (
                "error" if result.text.startswith(("[Agent SDK Error:", "[Cursor Error:", "[Error:")) else "responded"
            )
            return CycleResult(
                trigger=trigger,
                action=_d_action,
                summary=result.text,
                duration_ms=duration_ms,
                context_usage_ratio=tracker.usage_ratio,
                context_window=tracker.context_window,
                context_threshold=tracker.threshold,
                tool_call_records=_tool_records_to_dicts(result),
                usage=_d_usage,
                truncated=result.truncated,
            )

        # ── Mode G: Gemini CLI ─────────────────────────────
        if mode == "g":
            result = await active_executor.execute(
                prompt=prompt,
                system_prompt=system_prompt,
                tracker=tracker,
                trigger=trigger,
                images=images,
                max_turns_override=max_turns_override,
                thread_id=thread_id,
            )
            if result.replied_to_from_transcript:
                self._tool_handler.merge_replied_to(result.replied_to_from_transcript)
            _save_prompt_log_end(
                self.anima_dir,
                session_id=self._tool_handler.session_id,
                tool_call_count=len(result.tool_call_records),
            )
            if uses_chat_session:
                shortterm.clear()
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "run_cycle END (g) trigger=%s duration_ms=%d response_len=%d",
                trigger,
                duration_ms,
                len(result.text),
            )
            _g_usage = result.usage.to_dict() if result.usage else None
            _log_session_token_usage(
                self.anima_dir,
                model=active_model_config.model,
                mode="g",
                trigger=trigger,
                usage=_g_usage,
                duration_ms=duration_ms,
            )
            _g_action = (
                "error" if result.text.startswith(("[Agent SDK Error:", "[Gemini Error:", "[Error:")) else "responded"
            )
            return CycleResult(
                trigger=trigger,
                action=_g_action,
                summary=result.text,
                duration_ms=duration_ms,
                context_usage_ratio=tracker.usage_ratio,
                context_window=tracker.context_window,
                context_threshold=tracker.threshold,
                tool_call_records=_tool_records_to_dicts(result),
                usage=_g_usage,
                truncated=result.truncated,
            )

        # ── Mode X: Grok Build CLI ─────────────────────────
        if mode == "x":
            result = await active_executor.execute(
                prompt=prompt,
                system_prompt=system_prompt,
                tracker=tracker,
                trigger=trigger,
                images=images,
                max_turns_override=max_turns_override,
                thread_id=thread_id,
            )
            if result.replied_to_from_transcript:
                self._tool_handler.merge_replied_to(result.replied_to_from_transcript)
            _save_prompt_log_end(
                self.anima_dir,
                session_id=self._tool_handler.session_id,
                tool_call_count=len(result.tool_call_records),
            )
            if uses_chat_session:
                shortterm.clear()
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "run_cycle END (x) trigger=%s duration_ms=%d response_len=%d",
                trigger,
                duration_ms,
                len(result.text),
            )
            _x_usage = result.usage.to_dict() if result.usage else None
            _log_session_token_usage(
                self.anima_dir,
                model=active_model_config.model,
                mode="x",
                trigger=trigger,
                usage=_x_usage,
                duration_ms=duration_ms,
            )
            return CycleResult(
                trigger=trigger,
                action="responded",
                summary=result.text,
                duration_ms=duration_ms,
                context_usage_ratio=tracker.usage_ratio,
                context_window=tracker.context_window,
                context_threshold=tracker.threshold,
                tool_call_records=_tool_records_to_dicts(result),
                usage=_x_usage,
                truncated=result.truncated,
            )

        # ── Mode A: LiteLLM tool_use loop ─────────────────
        if mode == "a":
            result = await active_executor.execute(
                prompt=prompt,
                system_prompt=system_prompt,
                tracker=tracker,
                shortterm=shortterm if uses_chat_session else None,
                images=images,
                prior_messages=prior_messages,
                max_turns_override=max_turns_override,
                thread_id=thread_id,
                trigger=trigger,
            )
            _save_prompt_log_end(
                self.anima_dir,
                session_id=self._tool_handler.session_id,
                tool_call_count=len(result.tool_call_records),
            )
            if uses_chat_session and not tracker.threshold_exceeded:
                shortterm.clear()
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.info(
                "run_cycle END (a) trigger=%s duration_ms=%d response_len=%d",
                trigger,
                duration_ms,
                len(result.text),
            )
            _a_usage = result.usage.to_dict() if result.usage else None
            _log_session_token_usage(
                self.anima_dir,
                model=active_model_config.model,
                mode="a",
                trigger=trigger,
                usage=_a_usage,
                duration_ms=duration_ms,
            )
            _a_action = (
                "error" if result.text.startswith(("[Agent SDK Error:", "[LiteLLM Error:", "[Error:")) else "responded"
            )
            return CycleResult(
                trigger=trigger,
                action=_a_action,
                summary=result.text,
                duration_ms=duration_ms,
                context_usage_ratio=tracker.usage_ratio,
                context_window=tracker.context_window,
                context_threshold=tracker.threshold,
                tool_call_records=_tool_records_to_dicts(result),
                usage=_a_usage,
                truncated=result.truncated,
            )

        # ── Mode S: Claude Agent SDK ──────────────────────
        # Pre-flight: check prompt size to prevent Agent SDK buffer overflow
        conv_memory = None
        if uses_chat_session:
            from core.memory.conversation import ConversationMemory

            conv_memory = ConversationMemory(self.anima_dir, active_model_config, thread_id=thread_id)
        system_prompt, prompt, use_fallback = await self._preflight_size_check(
            system_prompt,
            prompt,
            conv_memory,
            priming_section=priming_section,
            mode=mode,
            message=prompt,
            trigger=trigger,
            context_window=_ctx_window,
            pending_human_notifications=pending_human_notifications,
            prompt_tier=_prompt_tier,
            prompt_profile=_prompt_profile,
        )
        if use_fallback:
            executor = self._create_fallback_executor(active_model_config)
            result = await executor.execute(
                prompt=prompt,
                system_prompt=system_prompt,
                tracker=tracker,
                trigger=trigger,
                images=images,
                prior_messages=prior_messages,
                max_turns_override=max_turns_override,
                thread_id=thread_id,
            )
        else:
            result = await active_executor.execute(
                prompt=prompt,
                system_prompt=system_prompt,
                tracker=tracker,
                trigger=trigger,
                images=images,
                max_turns_override=max_turns_override,
                thread_id=thread_id,
            )
        # Merge transcript-parsed replied_to for S mode
        if result.replied_to_from_transcript:
            self._tool_handler.merge_replied_to(result.replied_to_from_transcript)
            logger.info("Merged transcript replied_to: %s", result.replied_to_from_transcript)
        result_msg = result.result_message
        accumulated_tool_records = _tool_records_to_dicts(result)

        # Session chaining: if threshold was crossed, continue in a new session.
        # force_chain is set by S mode mid-session context auto-compact (PreToolUse
        # hook returned continue_=False).  In that case ResultMessage.usage may
        # not have updated the tracker, so we force the threshold flag.
        if result.force_chain and not tracker.threshold_exceeded:
            tracker.force_threshold()
            logger.info(
                "Context auto-compact: forcing threshold_exceeded for session "
                "chaining (S mode mid-session context budget exceeded)"
            )

        session_chained = False
        total_turns = result_msg.num_turns if result_msg else 0
        chain_count = 0
        accumulated_text = result.text

        if tracker.threshold_exceeded and uses_chat_session:
            # Save shortterm for the next message to pick up via inject_shortterm.
            # Do NOT chain here — chaining mid-response causes the LLM to produce
            # unnatural "session handoff" messages.
            logger.info(
                "Session context at %.1f%% — saving shortterm, will resume on next message",
                tracker.usage_ratio * 100,
            )
            shortterm.clear()
            shortterm.save(
                SessionState(
                    session_id=result_msg.session_id if result_msg else "",
                    timestamp=now_iso(),
                    trigger=trigger,
                    original_prompt=prompt,
                    accumulated_response=accumulated_text,
                    context_usage_ratio=tracker.usage_ratio,
                    turn_count=result_msg.num_turns if result_msg else 0,
                )
            )
            # Clear SDK session ID so the next session starts fresh
            if mode == "s":
                try:
                    from core.execution._sdk_session import (
                        _RESUMABLE_SESSION_TYPES,
                        _clear_session_id,
                        _resolve_session_type,
                    )

                    _st = _resolve_session_type(trigger)
                    if _st in _RESUMABLE_SESSION_TYPES:
                        _clear_session_id(self.anima_dir, _st, thread_id)
                except Exception:
                    logger.debug("Failed to clear session ID for deferred chain", exc_info=True)
        elif uses_chat_session:
            shortterm.clear()

        _save_prompt_log_end(
            self.anima_dir,
            session_id=self._tool_handler.session_id,
            tool_call_count=len(accumulated_tool_records),
        )

        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "run_cycle END trigger=%s duration_ms=%d response_len=%d chained=%s",
            trigger,
            duration_ms,
            len(accumulated_text),
            session_chained,
        )
        _cycle_usage = result.usage.to_dict() if result.usage else None
        _log_session_token_usage(
            self.anima_dir,
            model=active_model_config.model,
            mode="s",
            trigger=trigger,
            usage=_cycle_usage,
            duration_ms=duration_ms,
            turns=total_turns,
            chains=chain_count if session_chained else 0,
        )
        _s_nb_action = "error" if accumulated_text.startswith("[Agent SDK Error:") else "responded"
        return CycleResult(
            trigger=trigger,
            action=_s_nb_action,
            summary=accumulated_text,
            duration_ms=duration_ms,
            context_usage_ratio=tracker.usage_ratio,
            context_window=tracker.context_window,
            context_threshold=tracker.threshold,
            session_chained=session_chained,
            total_turns=total_turns,
            tool_call_records=accumulated_tool_records,
            usage=_cycle_usage,
            truncated=result.truncated,
        )

    # ── Streaming ──────────────────────────────────────────

    async def run_cycle_streaming(
        self,
        prompt: str,
        trigger: str = "manual",
        images: list[ImageData] | None = None,
        prior_messages: list[dict[str, Any]] | None = None,
        message_intent: str = "",
        max_turns_override: int | None = None,
        thread_id: str = "default",
        model_config_override: ModelConfig | None = None,
        prompt_tier_override: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Streaming version of run_cycle.

        Yields stream chunks. Session chaining is handled seamlessly.
        Final event is ``{"type": "cycle_done", "cycle_result": {...}}``.
        """
        from core.logging_config import bind_cycle_context, clear_cycle_context

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
                budget_result = self._check_monthly_token_budget(
                    trigger=trigger,
                    model_config=self.model_config,
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
                            max_turns_override=max_turns_override,
                            thread_id=thread_id,
                            model_config_override=model_config_override,
                            prompt_tier_override=prompt_tier_override,
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
        max_turns_override: int | None = None,
        thread_id: str = "default",
        model_config_override: ModelConfig | None = None,
        prompt_tier_override: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Streaming implementation scoped by ``run_cycle_streaming``."""
        start = time.monotonic()
        active_model_config = model_config_override or self.model_config
        active_executor = (
            self._create_executor(active_model_config) if model_config_override is not None else self._executor
        )
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
                max_turns_override=max_turns_override,
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

        # ── Resolve context window and prompt tier ────────────
        from core.prompt.builder import resolve_prompt_tier as _rpt
        from core.prompt.context import resolve_context_window as _rcw

        _ctx_window_s = _rcw(
            active_model_config.model,
            overrides=self._load_context_window_overrides(),
        )
        _prompt_profile_s = PROMPT_PROFILE_MEETING if prompt_tier_override == PROMPT_PROFILE_MEETING else ""
        _prompt_tier_s = TIER_MICRO if _prompt_profile_s else prompt_tier_override or _rpt(_ctx_window_s)

        # ── All streaming-capable executors ──────────────────────
        priming_section, pending_human_notifications = await self._run_priming(
            prompt,
            trigger,
            message_intent=message_intent,
            prompt_tier=_prompt_tier_s,
            model_config=active_model_config,
        )

        session_type = resolve_runtime_session_type(trigger)
        uses_chat_session = trigger_uses_chat_session(trigger)
        shortterm = ShortTermMemory(self.anima_dir, session_type=session_type, thread_id=thread_id)
        self._prepare_clean_start_session(
            trigger=trigger,
            session_type=session_type,
            thread_id=thread_id,
            shortterm=shortterm,
        )
        tracker = ContextTracker(
            model=active_model_config.model,
            threshold=active_model_config.context_threshold,
            context_window_overrides=self._load_context_window_overrides(),
        )

        build_result = build_system_prompt(
            self.memory,
            tool_registry=self._tool_registry,
            personal_tools=self._personal_tools,
            priming_section=priming_section,
            execution_mode=mode,
            message=prompt,
            retriever=self._get_retriever(),
            trigger=trigger,
            context_window=_ctx_window_s,
            pending_human_notifications=pending_human_notifications,
            thread_id=thread_id,
            prompt_tier=_prompt_tier_s,
            prompt_profile=_prompt_profile_s,
        )
        system_prompt = build_result.system_prompt

        # ── Context-window-aware tier downgrade ────────────
        system_prompt = self._fit_prompt_to_context_window(
            system_prompt,
            prompt,
            _ctx_window_s,
            priming_section=priming_section,
            mode=mode,
            trigger=trigger,
            pending_human_notifications=pending_human_notifications,
            thread_id=thread_id,
            prompt_tier=_prompt_tier_s,
            prompt_profile=_prompt_profile_s,
        )

        if uses_chat_session and shortterm.has_pending():
            system_prompt = inject_shortterm(system_prompt, shortterm)

        # Pre-flight size check for streaming path
        conv_memory = None
        if uses_chat_session:
            from core.memory.conversation import ConversationMemory

            conv_memory = ConversationMemory(self.anima_dir, active_model_config, thread_id=thread_id)
        system_prompt, prompt, use_fallback = await self._preflight_size_check(
            system_prompt,
            prompt,
            conv_memory,
            priming_section=priming_section,
            mode=mode,
            message=prompt,
            trigger=trigger,
            context_window=_ctx_window_s,
            pending_human_notifications=pending_human_notifications,
            thread_id=thread_id,
            prompt_tier=_prompt_tier_s,
            prompt_profile=_prompt_profile_s,
        )
        if use_fallback:
            logger.warning("Streaming fallback: using blocking S Fallback for oversized prompt")
            cycle = await self._run_cycle_inner_scoped(
                prompt,
                trigger,
                message_intent=message_intent,
                images=images,
                max_turns_override=max_turns_override,
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

        if mode == "c":
            _update_tracker_from_prompt_estimate(tracker, system_prompt, prompt)

        # ── Prompt log: save full payload for debugging ───
        from core.tooling.schemas import load_all_tool_schemas as _lats

        _tool_schemas_s = _lats(
            tool_registry=self._tool_registry,
            personal_tools=self._personal_tools,
        )
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
            context_window=_ctx_window_s,
            prior_messages=prior_messages,
            tool_schemas=_tool_schemas_s,
        )

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
        _stream_usage: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }
        terminal_error_message = ""
        stream_truncated = False
        current_prompt = prompt
        current_system_prompt = system_prompt
        retry_count = 0

        # Meeting turns hide the completion sentinel from the live stream. The
        # sentinel can arrive split across text_delta chunks, so we hold back a
        # tail that could be the start of the sentinel until we see more text.
        _is_meeting_turn = _prompt_profile_s == PROMPT_PROFILE_MEETING
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

            try:
                async for chunk in active_executor.execute_streaming(
                    current_system_prompt,
                    current_prompt,
                    tracker,
                    images=images,
                    prior_messages=prior_messages,
                    max_turns_override=max_turns_override,
                    trigger=trigger,
                    thread_id=thread_id,
                ):
                    if self._progress_callback:
                        self._progress_callback()
                    if chunk["type"] == "done":
                        full_text_parts.append(chunk["full_text"])
                        text_parts_this_attempt.append(chunk["full_text"])
                        if _is_meeting_turn and MEETING_DONE_SENTINEL in chunk["full_text"]:
                            _sentinel_seen = True
                        result_message = chunk["result_message"]
                        # Accumulate tool call records from executor
                        all_tool_call_records.extend(chunk.get("tool_call_records", []))
                        _merge_stream_usage(_stream_usage, chunk.get("usage"))
                        # Merge transcript replied_to
                        transcript_replied = chunk.get("replied_to_from_transcript", set())
                        if transcript_replied:
                            self._tool_handler.merge_replied_to(transcript_replied)
                        # Capture force_chain from S mode auto-compact
                        if chunk.get("force_chain", False):
                            _stream_force_chain = True
                        if chunk.get("truncated", False):
                            stream_truncated = True
                        stream_succeeded = True
                    elif chunk["type"] == "error" and chunk.get("terminal") is True:
                        terminal_error_message = chunk.get("message", "[Terminal LLM error]")
                        yield chunk
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
                        # Save checkpoint after each tool completion
                        from core.memory.shortterm import StreamCheckpoint

                        shortterm.save_checkpoint(
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
                        yield chunk

            except Exception as e:
                from core.execution.base import StreamDisconnectedError

                is_stream_error = isinstance(e, StreamDisconnectedError)
                if not is_stream_error:
                    # Non-stream errors: log and break
                    logger.exception("Agent SDK streaming error (non-retryable)")
                    terminal_error_message = f"[Agent SDK Error: {e}]"
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
                        if mode == "c" and uses_chat_session:
                            from core.execution.codex_sdk import clear_codex_thread_ids

                            clear_codex_thread_ids(self.anima_dir, thread_id)
                        elif mode == "x" and uses_chat_session:
                            from core.execution.grok_cli import (
                                _clear_session_id as clear_grok_session_id,
                            )
                            from core.execution.grok_cli import (
                                _resolve_session_type as resolve_grok_session_type,
                            )

                            clear_grok_session_id(
                                self.anima_dir,
                                resolve_grok_session_type(trigger),
                                thread_id,
                            )
                        elif mode not in ("c", "x"):
                            from core.execution._sdk_session import (
                                _RESUMABLE_SESSION_TYPES,
                                _clear_session_id,
                                _resolve_session_type,
                            )

                            _st_retry = _resolve_session_type(trigger)
                            if _st_retry in _RESUMABLE_SESSION_TYPES:
                                _clear_session_id(self.anima_dir, _st_retry, thread_id)
                        logger.info("Session IDs cleared for retry 1 (fresh session forced)")
                    except Exception as e:
                        logger.warning("Failed to clear session IDs for retry: %s", e)
                yield {
                    "type": "retry_start",
                    "retry": retry_count,
                    "max_retries": max_retries,
                    "delay_s": actual_delay,
                    "retry_after_s": retry_after_s,
                }

                # Load checkpoint and build retry prompt
                from core.execution._session import build_stream_retry_prompt
                from core.memory.shortterm import StreamCheckpoint

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
                current_system_prompt = build_system_prompt(
                    self.memory,
                    tool_registry=self._tool_registry,
                    personal_tools=self._personal_tools,
                    priming_section=priming_section,
                    execution_mode=mode,
                    message=prompt,
                    retriever=self._get_retriever(),
                    trigger=trigger,
                    context_window=_ctx_window_s,
                    pending_human_notifications=pending_human_notifications,
                    thread_id=thread_id,
                    prompt_tier=_prompt_tier_s,
                    prompt_profile=_prompt_profile_s,
                ).system_prompt

                await asyncio.sleep(actual_delay)
                continue

            if stream_succeeded or terminal_error_message:
                # A structured terminal provider error is a completed failure,
                # not a disconnected stream eligible for retry.
                shortterm.clear_checkpoint()
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
                        max_turns_override=max_turns_override,
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
            shortterm.clear_checkpoint()

        session_chained = False
        total_turns = result_message.num_turns if result_message else 0
        chain_count = 0

        # Session chaining — force_chain from mid-session auto-compact.
        if _stream_force_chain and not tracker.threshold_exceeded:
            tracker.force_threshold()
            logger.info("Context auto-compact (stream): forcing threshold_exceeded")

        if tracker.threshold_exceeded and uses_chat_session:
            # Save shortterm for the next message to pick up via inject_shortterm.
            # Do NOT chain here — chaining mid-response causes the LLM to produce
            # unnatural "session handoff" messages.
            logger.info(
                "Session context at %.1f%% — saving shortterm, will resume on next message (stream)",
                tracker.usage_ratio * 100,
            )
            shortterm.clear()
            shortterm.save(
                SessionState(
                    session_id=result_message.session_id if result_message else "",
                    timestamp=now_iso(),
                    trigger=trigger,
                    original_prompt=prompt,
                    accumulated_response="\n".join(full_text_parts),
                    context_usage_ratio=tracker.usage_ratio,
                    turn_count=result_message.num_turns if result_message else 0,
                )
            )
            # Clear SDK session ID so the next session starts fresh
            if mode == "s":
                try:
                    from core.execution._sdk_session import (
                        _RESUMABLE_SESSION_TYPES,
                        _clear_session_id,
                        _resolve_session_type,
                    )

                    _st = _resolve_session_type(trigger)
                    if _st in _RESUMABLE_SESSION_TYPES:
                        _clear_session_id(self.anima_dir, _st, thread_id)
                except Exception:
                    logger.debug("Failed to clear session ID for deferred chain", exc_info=True)
            elif mode == "c":
                try:
                    from core.execution.codex_sdk import clear_codex_thread_ids

                    clear_codex_thread_ids(self.anima_dir, thread_id)
                except Exception:
                    logger.debug("Failed to clear Codex thread ID for deferred chain", exc_info=True)
            elif mode == "x":
                try:
                    from core.execution.grok_cli import (
                        _clear_session_id as clear_grok_session_id,
                    )
                    from core.execution.grok_cli import (
                        _resolve_session_type as resolve_grok_session_type,
                    )

                    clear_grok_session_id(
                        self.anima_dir,
                        resolve_grok_session_type(trigger),
                        thread_id,
                    )
                except Exception:
                    logger.debug("Failed to clear Grok session ID for deferred chain", exc_info=True)
        elif uses_chat_session:
            shortterm.clear()

        _save_prompt_log_end(
            self.anima_dir,
            session_id=self._tool_handler.session_id,
            tool_call_count=len(all_tool_call_records),
        )

        full_text = "\n".join(full_text_parts)
        if _is_meeting_turn:
            full_text = _strip_meeting_sentinel(full_text)
        thinking_text = "".join(thinking_text_parts)
        final_action = "error" if terminal_error_message else "responded"
        final_summary = full_text or terminal_error_message
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.info(
            "run_cycle_streaming END trigger=%s duration_ms=%d response_len=%d chained=%s retries=%d",
            trigger,
            duration_ms,
            len(full_text),
            session_chained,
            retry_count,
        )

        _final_usage = _stream_usage if any(_stream_usage.values()) else None
        _log_session_token_usage(
            self.anima_dir,
            model=active_model_config.model,
            mode=mode,
            trigger=trigger,
            usage=_final_usage,
            duration_ms=duration_ms,
            turns=total_turns,
            chains=chain_count if session_chained else 0,
        )
        yield {
            "type": "cycle_done",
            "cycle_result": CycleResult(
                trigger=trigger,
                action=final_action,
                summary=final_summary,
                thinking_text=thinking_text[:10000],
                duration_ms=duration_ms,
                context_usage_ratio=tracker.usage_ratio,
                context_window=tracker.context_window,
                context_threshold=tracker.threshold,
                session_chained=session_chained,
                total_turns=total_turns,
                tool_call_records=all_tool_call_records,
                usage=_final_usage,
                truncated=stream_truncated,
            ).model_dump(mode="json"),
        }
