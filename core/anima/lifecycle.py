from __future__ import annotations

from core.anima._mixin_protocols import _LifecycleHost

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""LifecycleMixin -- heartbeat orchestration, consolidation, cron execution.

Extracted from ``core.anima.digital_anima.DigitalAnima`` as a Mixin.  All ``self``
references are resolved at runtime via MRO when mixed into ``DigitalAnima``.
"""

import asyncio
import contextvars
import hashlib
import inspect
import logging
import os
import re
import signal
import time
from contextlib import AsyncExitStack, nullcontext
from datetime import date, timedelta
from typing import Any

from core.execution.fallback_activity import run_with_model_fallback
from core.i18n import t
from core.paths import load_prompt
from core.platform.process import kill_tree, signal_tree, snapshot_descendants, subprocess_session_kwargs
from core.schemas import CycleResult
from core.time_utils import now_local
from core.trust import ORIGIN_SYSTEM

logger = logging.getLogger("animaworks.anima")

# Monotonic time at which the running consolidation will be cancelled. Daily
# summaries read it to avoid starting an older day that cannot finish in time.
_CONSOLIDATION_DEADLINE_AT: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "consolidation_deadline_at", default=None
)

_CRON_COMMAND_TIMEOUT_SECONDS = 600.0


async def _kill_cron_command_group(proc: asyncio.subprocess.Process) -> None:
    """Kill and reap a timed-out or cancelled cron command and its descendants."""
    descendants = await asyncio.to_thread(snapshot_descendants, proc.pid)
    if os.name == "nt":
        await asyncio.to_thread(kill_tree, proc.pid, descendants=descendants, include_root=True)
    else:
        await asyncio.to_thread(
            signal_tree,
            proc.pid,
            signal.SIGKILL,
            pgid=proc.pid,
            descendants=descendants,
        )
    try:
        await proc.wait()
    except ProcessLookupError:
        pass


_MAX_THREAD_ID_LEN = 36


def _cron_thread_id(task_name: str) -> str:
    """Return a safe, task-specific session thread id for cron work."""
    safe_name = re.sub(r"[^A-Za-z0-9_-]", "_", task_name)
    thread_id = f"cron-{safe_name}"
    if len(thread_id) <= _MAX_THREAD_ID_LEN and task_name.isascii():
        return thread_id
    # The state writer accepts at most 36 chars, and non-ASCII names collapse to
    # underscores, so long or non-ASCII names get a stable hash suffix.
    digest = hashlib.sha1(task_name.encode("utf-8")).hexdigest()[:10]
    head = safe_name.strip("_")[: _MAX_THREAD_ID_LEN - len("cron--") - len(digest)].rstrip("_")
    return f"cron-{head}-{digest}" if head else f"cron-{digest}"


def _agent_for_lane(owner: Any, lane: str):
    getter = getattr(owner, "_agent_for_lane", None)
    if callable(getter):
        return getter(lane)
    return owner.agent


def _agent_session_context(owner: Any, lane: str = "background"):
    getter = getattr(owner, "_agent_session_context", None)
    if callable(getter):
        return getter(lane)
    lock = getattr(owner, "_agent_session_lock", None)
    if isinstance(lock, asyncio.Lock):
        return lock
    return nullcontext()


# ── Consolidation prompt helpers ─────────────────────────────────


def _format_knowledge_list(files: list[dict[str, Any]]) -> str:
    """Format knowledge files into a concise list for prompt injection."""
    if not files:
        return "（knowledgeファイルなし / No knowledge files）"
    lines: list[str] = []
    for f in files:
        conf = f.get("confidence", "?")
        created = str(f.get("created_at", "?"))[:10]
        lines.append(f"- {f['path']} [conf={conf}, created={created}]")
    return "\n".join(lines)


def _format_merge_candidates(candidates: list[tuple[str, str, float]]) -> str:
    """Format merge candidate pairs for prompt injection."""
    if not candidates:
        return "（マージ候補なし / No merge candidates）"
    lines: list[str] = []
    for a, b, sim in candidates:
        lines.append(f"- {a} ↔ {b} (similarity: {sim:.2f})")
    return "\n".join(lines)


def _format_conflict_candidates(candidates: list[tuple[str, str, str]]) -> str:
    """Format conflicting-fact candidate pairs for prompt injection.

    Mirrors ``_format_merge_candidates``: when there are no candidates a
    short "no candidates" line is shown (rather than rendering an empty
    section), so the placeholder always resolves to something.
    """
    if not candidates:
        return "（食い違い候補なし / No conflict candidates）"
    lines: list[str] = []
    for older, newer, desc in candidates:
        lines.append(f"- {older} ↔ {newer}: {desc}")
    return "\n".join(lines)


def _format_forgetting_candidates(candidates: list[Any]) -> str:
    """Format forgetting candidates for prompt injection.

    Returns a bullet list of ``- path — reason`` lines, or a short
    "no candidates" line when there is nothing to review (so the
    placeholder always resolves to something).
    """
    if not candidates:
        return "（忘却候補なし / No forgetting candidates）"
    lines: list[str] = []
    for candidate in candidates:
        lines.append(f"- {candidate.path} — {candidate.reason}")
    return "\n".join(lines)


def _format_hygiene_section(
    report: dict[str, list[dict[str, Any]]],
    *,
    locale: str | None = None,
) -> str:
    """Format detected memory hygiene items for the weekly prompt."""
    categories = (
        ("merged_leftovers", "memory_hygiene.merged_leftovers"),
        ("inherited_dirs", "memory_hygiene.inherited_dirs"),
        ("mdc_files", "memory_hygiene.mdc_files"),
        ("oversized_knowledge", "memory_hygiene.oversized_knowledge"),
        ("noncanonical_archive_dirs", "memory_hygiene.noncanonical_archive_dirs"),
    )
    sections: list[str] = []
    for category, title_key in categories:
        items = report.get(category, [])
        if not items:
            continue
        lines = [t(title_key, locale=locale)]
        for item in items[:20]:
            path = str(item.get("path", ""))
            if category == "oversized_knowledge" and isinstance(item.get("size_bytes"), int):
                path = f"{path} ({item['size_bytes'] / 1024:.1f} KB)"
            lines.append(f"- {path}")
        if len(items) > 20:
            lines.append(t("memory_hygiene.remaining", locale=locale, count=len(items) - 20))
        sections.append("\n".join(lines))
    if not sections:
        return ""
    return t("memory_hygiene.header", locale=locale) + "\n\n" + "\n\n".join(sections)


_PROVIDER_ENV_MAP: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "google": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def _resolve_consolidation_credential(
    consolidation_model: str,
    cfg: Any,
    credential: str = "",
) -> dict[str, Any]:
    """Resolve credential fields for the given consolidation model.

    Returns a dict with keys: api_key, api_base_url, api_key_env, extra_keys.
    These can be used to temporarily override ModelConfig credential fields so
    that consolidation LLM calls reach the correct provider endpoint.

    Resolution order:
      1. ``credential`` argument (explicit per-call credential name)
      2. ``config.consolidation.llm_credential`` (explicit credential name)
      3. Model name prefix (e.g. ``openai/...`` → ``openai`` credential)
    """
    if credential:
        explicit_cred = credential
    else:
        _llm_cred = getattr(cfg.consolidation, "llm_credential", None)
        explicit_cred = _llm_cred if isinstance(_llm_cred, str) and _llm_cred else ""
    explicit_cred = explicit_cred or ""
    parts = consolidation_model.split("/", 1)
    provider = parts[0].lower() if len(parts) > 1 else ""

    if explicit_cred:
        cred = cfg.credentials.get(explicit_cred)
    else:
        cred = cfg.credentials.get(provider) if provider else None

    api_key = cred.api_key if cred else None
    api_base_url = (cred.base_url if cred else None) or None
    api_key_env = _PROVIDER_ENV_MAP.get(provider, "ANTHROPIC_API_KEY")
    extra_keys: dict[str, str] = {}
    if cred and hasattr(cred, "keys") and cred.keys:
        extra_keys = dict(cred.keys)
    return {
        "credential": explicit_cred or provider,
        "api_key": api_key,
        "api_base_url": api_base_url,
        "api_key_env": api_key_env,
        "extra_keys": extra_keys,
    }


def _consolidation_model_config(
    base_model_config: Any,
    consolidation_model: str,
    cfg: Any,
    credential: str = "",
) -> Any:
    """Return a ModelConfig override for consolidation-only LLM calls.

    Consolidation must not inherit a per-Anima chat model/credential mismatch
    (for example a Bedrock main model with a vLLM credential).  Use the
    explicit consolidation helper model and credential while preserving other
    per-Anima limits and org metadata from the base ModelConfig.
    """
    from core.config import resolve_execution_mode

    resolved = _resolve_consolidation_credential(consolidation_model, cfg, credential=credential)
    updates = {
        "model": consolidation_model,
        "credential": resolved["credential"] or getattr(base_model_config, "credential", None),
        "api_key": resolved["api_key"],
        "api_key_env": resolved["api_key_env"],
        "api_base_url": resolved["api_base_url"],
        "extra_keys": resolved["extra_keys"],
        "resolved_mode": resolve_execution_mode(cfg, consolidation_model),
    }
    return base_model_config.model_copy(update=updates)


def _project_consolidation_was_interrupted(result: CycleResult) -> bool:
    return bool(result.truncated)


def _split_episode_prompt_to_limit(
    activity_chunk: str,
    prompt_builder: Any,
    max_input_bytes: int,
) -> tuple[list[tuple[str, str]], str]:
    """Split an activity chunk until each fully rendered prompt fits its byte cap."""
    pending = [activity_chunk]
    prompts: list[tuple[str, str]] = []
    while pending:
        part = pending.pop(0)
        prompt = prompt_builder(part)
        if len(prompt.encode("utf-8")) <= max_input_bytes:
            prompts.append((part, prompt))
            continue
        if len(part) <= 1:
            return [], "rendered prompt exceeds configured input byte limit"

        midpoint = len(part) // 2
        boundary = part.rfind("\n", max(1, midpoint // 2), midpoint)
        split_at = boundary + 1 if boundary >= 0 else midpoint
        if split_at <= 0 or split_at >= len(part):
            split_at = midpoint
        pending[0:0] = [part[:split_at], part[split_at:]]
    return prompts, ""


# Execution modes that one_shot_completion can serve (LiteLLM, Agent SDK, Codex SDK).
_ONE_SHOT_MODES = frozenset({"a", "s", "c"})


def _episode_summary_model_configs(base_model_config: Any, model: str, cfg: Any) -> list[Any]:
    """Build ordered one-shot model configs from existing anima fallback settings."""
    from core.config.model_config import build_model_override_config
    from core.config.model_mode import parse_fallback_entry

    primary = _consolidation_model_config(base_model_config, model, cfg)
    candidates = [primary]
    entries: list[tuple[str, str | None]] = []
    # Explicit consolidation fallback (e.g. a local GPU model) is tried right
    # after the primary and before any per-Anima fallback (background model).
    fallback_model = getattr(getattr(cfg, "consolidation", None), "llm_fallback_model", None)
    if fallback_model:
        entries.append((fallback_model, getattr(getattr(cfg, "consolidation", None), "llm_fallback_credential", None)))
    entries.extend((entry, None) for entry in getattr(base_model_config, "fallback_models", []) or [])
    legacy_fallback = getattr(base_model_config, "fallback_model", None)
    if legacy_fallback:
        entries.append((legacy_fallback, None))
    background_model = getattr(base_model_config, "background_model", None)
    if background_model and background_model != model:
        entries.append((background_model, getattr(base_model_config, "background_credential", None)))

    seen = {(primary.model, primary.credential)}
    for entry, credential_name in entries:
        parsed = parse_fallback_entry(entry, cfg)
        if parsed is None:
            continue
        mode, fallback_model = parsed
        if mode not in _ONE_SHOT_MODES:
            # CLI-only engines (grok/cursor/gemini) have no one-shot backend.
            continue
        candidate = build_model_override_config(
            primary,
            mode,
            fallback_model,
            cfg,
            credential_name=credential_name,
        )
        if candidate is None:
            continue
        key = (candidate.model, candidate.credential)
        if key not in seen:
            seen.add(key)
            candidates.append(candidate)
    return candidates


async def _complete_episode_prompt(
    prompt: str,
    model_configs: list[Any],
    *,
    max_output_tokens: int = 8192,
) -> tuple[str | None, str]:
    """Try the primary one-shot model followed by configured model fallbacks."""
    from core.llm.oneshot import one_shot_completion

    failures: list[str] = []
    for model_config in model_configs:
        try:
            result = await one_shot_completion(
                prompt,
                model=model_config.model,
                credential=model_config.credential or "",
                max_tokens=max_output_tokens,
            )
        except Exception as exc:
            failures.append(f"{model_config.model}:{type(exc).__name__}")
            continue
        if result and result.strip():
            return result, ""
        failures.append(f"{model_config.model}:empty response")
    if len(model_configs) == 1:
        model_config = model_configs[0]
        try:
            retry_result = await one_shot_completion(
                prompt,
                model=model_config.model,
                credential=model_config.credential or "",
                max_tokens=max_output_tokens,
            )
        except Exception as exc:
            failures.append(f"{model_config.model}:retry {type(exc).__name__}")
        else:
            if retry_result and retry_result.strip():
                return retry_result, ""
            failures.append(f"{model_config.model}:retry empty response")
    reason = "; ".join(failures) or "no usable model configured"
    return None, reason[:240].replace("\n", " ")


class LifecycleMixin:
    """Mixin: heartbeat orchestration, memory consolidation, cron task execution."""

    async def _keepalive_while_busy(self: _LifecycleHost, interval: float = 60.0) -> None:
        """Periodically update _last_progress_at to prevent busy-hang false positives.

        Start this as a background task during long-running operations (heartbeat,
        cron, etc.) that may not update progress through the normal streaming path.
        """
        try:
            while True:
                await asyncio.sleep(interval)
                if hasattr(self, "_mark_busy_progress"):
                    self._mark_busy_progress()
                else:
                    self._last_progress_at = now_local()
                    self._write_busy_status_sidecar()
        except asyncio.CancelledError:
            pass

    async def run_heartbeat(self: _LifecycleHost) -> CycleResult:
        self._get_interrupt_event("_background").clear()
        # START is logged only after the background lock is held: "START" must mean
        # "running", not "queued behind another background lane".
        logger.info("[%s] run_heartbeat WAITING_LOCK", self.name)
        try:
            async with self._background_lock:
                logger.info("[%s] run_heartbeat START", self.name)
                self._mark_busy_start()
                _keepalive = asyncio.create_task(self._keepalive_while_busy())
                self._status_slots["background"] = "checking"
                self._last_heartbeat = now_local()
                await self._activity.alog("heartbeat_start", summary=t("anima.heartbeat_start"))

                try:
                    parts = await self._build_heartbeat_prompt()
                    if self.messenger.has_unread():
                        logger.warning(
                            "[%s] Unread messages found during heartbeat — "
                            "inbox processing is handled by Path A (process_inbox_message)",
                            self.name,
                        )
                    return await self._run_heartbeat_agent_session(
                        "\n\n".join(parts),
                        _keepalive,
                    )
                except Exception as exc:
                    _unread = 0
                    try:
                        _unread = self.messenger.unread_count()
                    except OSError:
                        pass
                    await self._handle_heartbeat_failure(exc, [], _unread)
                    raise
                finally:
                    self._status_slots["background"] = "idle"
                    self._task_slots["background"] = ""
                    await self._finalize_session_if_ended()
        finally:
            self._notify_lock_released()
            self._trigger_pending_task_execution()

    async def _run_heartbeat_agent_session(
        self: _LifecycleHost,
        heartbeat_text: str,
        keepalive: asyncio.Task[None],
    ) -> CycleResult:
        """Run the heartbeat agent cycle under the background session lane."""
        from core.config.models import load_config as _load_cfg
        from core.tooling.handler import active_session_type

        prior_msgs = self._build_prior_messages(heartbeat_text)
        hard_timeout = _load_cfg().heartbeat.hard_timeout_seconds
        agent = _agent_for_lane(self, "background")
        async with _agent_session_context(self, "background"):
            agent.set_interrupt_event(self._get_interrupt_event("_background"))
            session_token = agent._tool_handler.set_active_session_type("heartbeat")
            agent._tool_handler.set_session_origin(ORIGIN_SYSTEM)
            try:
                cycle = self._execute_heartbeat_cycle(
                    heartbeat_text,
                    [],
                    0,
                    prior_messages=prior_msgs,
                )
                # hard_timeout_seconds == 0 disables forced termination:
                # busy-hang detection (progress-based) remains the safety net.
                if hard_timeout:
                    return await asyncio.wait_for(cycle, timeout=float(hard_timeout))
                return await cycle
            except TimeoutError:
                return await self._handle_hard_timeout(hard_timeout)
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise
                logger.warning("[%s] run_heartbeat cancelled by request; runner remains alive", self.name)
                return CycleResult(
                    trigger="heartbeat",
                    action="cancelled",
                    summary="Heartbeat cancelled",
                    duration_ms=0,
                )
            finally:
                active_session_type.reset(session_token)
                keepalive.cancel()

    async def _finalize_session_if_ended(self: _LifecycleHost) -> None:
        """Session-boundary finalize; must not be skippable by cycle timeout/cancel."""
        try:
            from core.memory.conversation.memory import ConversationMemory

            await ConversationMemory(self.anima_dir, self.model_config).finalize_if_session_ended()
        except Exception:
            logger.debug("[%s] finalize_if_session_ended failed", self.name, exc_info=True)

    # ── Hard timeout helper ───────────────────────────────────

    async def _handle_hard_timeout(self: _LifecycleHost, hard_timeout: int) -> CycleResult:
        """Write recovery note and return a timeout CycleResult."""
        logger.warning(
            "[%s] Heartbeat hard timeout (%ds) — forced termination",
            self.name,
            hard_timeout,
        )
        try:
            from core.platform.state_writer import get_state_writer

            await get_state_writer(self.anima_dir).write_recovery_note(
                t("reminder.hb_hard_timeout_recovery", timeout=hard_timeout)
            )
        except Exception:
            logger.debug("[%s] Failed to write timeout recovery note", self.name, exc_info=True)
        self._activity.log(
            "heartbeat_end",
            summary=f"[TIMEOUT] Hard timeout after {hard_timeout}s",
            meta={"status": "timeout", "hard_timeout_s": hard_timeout},
            safe=True,
        )
        return CycleResult(
            trigger="heartbeat",
            action="timeout",
            summary=f"Hard timeout after {hard_timeout}s",
            duration_ms=hard_timeout * 1000,
        )

    async def run_consolidation(
        self: _LifecycleHost,
        consolidation_type: str = "daily",
        project: str | None = None,
        deadline_s: float | None = None,
    ) -> CycleResult:
        """Run daily episode extraction or project/weekly knowledge consolidation.

        Daily consolidation for the Anima extracts structured timeline episodes
        from activity_log via ``one_shot_completion`` and does not run a tool
        loop. When ``project`` is specified, the project archive is instead
        consolidated through the Anima's tool loop without Phase A. Weekly
        consolidation retains its existing single-phase flow.

        Daily episode extraction uses ``config.consolidation.llm_model`` as an
        isolated helper model. Project archive and weekly consolidation use
        the configured consolidation helper model/credential while preserving
        the Anima-specific prompt, memory, tools, and org metadata.

        Args:
            consolidation_type: "daily" or "weekly"
            project: Optional project archive to consolidate without Phase A.
        """
        logger.info(
            "[%s] run_consolidation START type=%s",
            self.name,
            consolidation_type,
        )
        from core.tooling.handler import active_session_type

        try:
            async with self._background_lock:
                self._mark_busy_start()
                _keepalive = asyncio.create_task(self._keepalive_while_busy())
                self._status_slots["background"] = "consolidating"
                self._task_slots["background"] = f"Memory consolidation ({consolidation_type})"
                agent = _agent_for_lane(self, "background")
                _session_token = agent._tool_handler.set_active_session_type("heartbeat")
                previous_default_project = getattr(agent._tool_handler, "_default_project", None)
                if project is not None:
                    agent._tool_handler._default_project = project

                from core.platform.state_writer import get_state_writer

                state_writer = get_state_writer(self.anima_dir)
                try:
                    await state_writer.set_consolidation_mode(True)
                except OSError:
                    pass

                try:
                    from core.memory.maintenance.consolidation import ConsolidationEngine

                    engine = (
                        ConsolidationEngine(self.anima_dir, self.name, project=project)
                        if project is not None
                        else ConsolidationEngine(self.anima_dir, self.name)
                    )

                    await self._activity.alog(
                        "consolidation_start",
                        summary=t("anima.consolidation_start", type=consolidation_type),
                    )

                    if consolidation_type == "daily":
                        coro = self._run_daily_consolidation(engine)
                    else:
                        coro = self._run_weekly_consolidation(engine)
                    if deadline_s:
                        deadline_token = _CONSOLIDATION_DEADLINE_AT.set(time.monotonic() + float(deadline_s))
                        try:
                            result = await asyncio.wait_for(coro, timeout=deadline_s)
                        except TimeoutError:
                            logger.warning(
                                "consolidation_deadline_exceeded anima=%s type=%s deadline_s=%s",
                                self.name,
                                consolidation_type,
                                deadline_s,
                            )
                            raise TimeoutError(f"consolidation exceeded deadline of {deadline_s}s") from None
                        finally:
                            _CONSOLIDATION_DEADLINE_AT.reset(deadline_token)
                    else:
                        result = await coro

                    self._last_activity = now_local()
                    await self._activity.alog(
                        "consolidation_end",
                        summary=t("anima.consolidation_end", type=consolidation_type),
                        content=result.summary[:500] if result.summary else "",
                        meta={
                            "type": consolidation_type,
                            "duration_ms": result.duration_ms,
                        },
                    )

                    logger.info(
                        "[%s] run_consolidation END type=%s duration_ms=%d",
                        self.name,
                        consolidation_type,
                        result.duration_ms,
                    )
                    return result

                except Exception as exc:
                    logger.exception(
                        "[%s] run_consolidation FAILED type=%s",
                        self.name,
                        consolidation_type,
                    )
                    await self._activity.alog(
                        "error",
                        summary=t("anima.consolidation_error", exc=type(exc).__name__),
                        meta={"phase": "run_consolidation", "error": str(exc)[:200]},
                        safe=True,
                    )
                    raise
                finally:
                    if project is not None:
                        agent._tool_handler._default_project = previous_default_project
                    _keepalive.cancel()
                    await state_writer.set_consolidation_mode(False)
                    active_session_type.reset(_session_token)
                    self._status_slots["background"] = "idle"
                    self._task_slots["background"] = ""
        finally:
            self._notify_lock_released()

    async def _run_daily_episode_summaries(
        self: _LifecycleHost,
        engine: Any,
        *,
        cfg: Any,
        model: str,
        start_mono: float,
    ) -> CycleResult:
        """Summarize yesterday and a bounded set of recent unprocessed days."""
        from core.config.models import ConsolidationConfig
        from core.memory.maintenance.activity_compaction import ActivityCompactionSettings

        consolidation_cfg = getattr(cfg, "consolidation", None)
        defaults = ConsolidationConfig()
        compaction_settings = ActivityCompactionSettings.from_config(consolidation_cfg, defaults)
        max_output_tokens = int(
            getattr(consolidation_cfg, "episode_summary_max_output_tokens", defaults.episode_summary_max_output_tokens)
        )
        max_input_bytes = int(
            getattr(consolidation_cfg, "episode_summary_max_input_bytes", defaults.episode_summary_max_input_bytes)
        )
        lookback_days = max(
            1, int(getattr(consolidation_cfg, "episode_summary_backfill_days", defaults.episode_summary_backfill_days))
        )
        max_backfill_days = max(
            0,
            int(
                getattr(
                    consolidation_cfg,
                    "episode_summary_backfill_max_days_per_run",
                    defaults.episode_summary_backfill_max_days_per_run,
                )
            ),
        )
        exclude_noop_cron = bool(
            getattr(
                consolidation_cfg,
                "episode_summary_exclude_noop_cron",
                defaults.episode_summary_exclude_noop_cron,
            )
        )

        target_date, _, _ = engine.previous_local_day_window(now_local())
        dates = [target_date]
        dates.extend(target_date - timedelta(days=offset) for offset in range(lookback_days - 1, 0, -1))
        pending_by_date: dict[date, list[str]] = {}
        filtered_by_date: dict[date, bool] = {}
        input_profile_by_date: dict[date, str] = {}
        for candidate_date in dates:
            pending, filter_applied = engine.collect_pending_activity_chunks(
                candidate_date,
                model=model,
                max_input_bytes=max_input_bytes,
                exclude_noop_cron=exclude_noop_cron,
                compaction_settings=compaction_settings,
            )
            if pending:
                pending_by_date[candidate_date] = pending
                filtered_by_date[candidate_date] = filter_applied
                profile_resolver = getattr(engine, "resolve_input_profile_for_date", None)
                input_profile_by_date[candidate_date] = (
                    profile_resolver(candidate_date, compaction_settings.profile)
                    if callable(profile_resolver)
                    else compaction_settings.profile
                )

        selected_dates: list[date] = []
        if target_date in pending_by_date:
            selected_dates.append(target_date)
        # Newest first: an interrupted day is redone from scratch, and the
        # oldest days fall out of the lookback window anyway.
        older_pending = [day for day in reversed(dates[1:]) if day in pending_by_date]
        selected_dates.extend(older_pending[:max_backfill_days])
        if not selected_dates:
            import time as _time

            return CycleResult(
                trigger="consolidation:daily",
                action="skipped",
                summary=t("anima.no_episodes_today"),
                duration_ms=int((_time.monotonic() - start_mono) * 1000),
            )
        if older_pending:
            logger.info(
                "[%s] Episode backfill: pending_days=%d selected_days=%d max_older_days=%d",
                self.name,
                len(older_pending),
                min(len(older_pending), max_backfill_days),
                max_backfill_days,
            )

        source_model_config = self.memory.read_model_config()
        model_configs = _episode_summary_model_configs(source_model_config, model, cfg)
        episode_summaries: list[str] = []
        done_bytes = 0
        done_seconds = 0.0
        for summary_date in selected_dates:
            chunks = pending_by_date[summary_date]
            day_bytes = sum(len(chunk.encode("utf-8")) for chunk in chunks)
            deadline_at = _CONSOLIDATION_DEADLINE_AT.get()
            if summary_date != target_date and deadline_at is not None and done_bytes > 0:
                remaining = deadline_at - time.monotonic()
                estimate = done_seconds / done_bytes * day_bytes * 1.2
                if estimate > remaining:
                    logger.info(
                        "[%s] Episode backfill stopped before %s: estimate=%.0fs remaining=%.0fs",
                        self.name,
                        summary_date.isoformat(),
                        estimate,
                        remaining,
                    )
                    break
            day_started = time.monotonic()
            existing_episode = engine.read_episode_for_date(summary_date)
            existing_context = existing_episode.strip() or "(none)"
            context_byte_limit = min(48_000, max(256, max_input_bytes // 4))
            existing_context = engine._truncate_utf8(existing_context, context_byte_limit)

            logger.info(
                "[%s] Phase A: extracting episodes for %s from %d chunk(s) with model=%s",
                self.name,
                summary_date.isoformat(),
                len(chunks),
                model,
            )
            episode_parts: list[str] = []
            completed_chunks: list[str] = []
            facts_extracted = 0
            facts_failed = 0
            failed_chunks = 0
            failure_reason = ""

            for chunk_index, chunk in enumerate(chunks):
                time_range = f"{summary_date.isoformat()} chunk {chunk_index + 1}/{len(chunks)}"

                def build_prompt(
                    activity_chunk: str,
                    time_range: str = time_range,
                    existing_context: str = existing_context,
                ) -> str:
                    return load_prompt(
                        "memory/episode_extraction",
                        anima_name=self.name,
                        time_range=time_range,
                        activity_chunk=activity_chunk,
                        existing_episode=existing_context,
                    )

                prompt_parts, split_error = _split_episode_prompt_to_limit(
                    chunk,
                    build_prompt,
                    max_input_bytes,
                )
                if split_error:
                    failed_chunks += 1
                    failure_reason = split_error
                    continue

                chunk_summaries: list[str] = []
                for _activity_part, prompt in prompt_parts:
                    raw, reason = await _complete_episode_prompt(
                        prompt,
                        model_configs,
                        max_output_tokens=max_output_tokens,
                    )
                    if not raw:
                        failure_reason = reason
                        break
                    sanitized = engine._sanitize_llm_output(raw)
                    if not sanitized.strip():
                        failure_reason = "empty sanitized summary"
                        break
                    chunk_summaries.append(sanitized)

                if len(chunk_summaries) != len(prompt_parts):
                    failed_chunks += 1
                    continue
                episode_parts.extend(chunk_summaries)
                completed_chunks.append(chunk)
                chunk_summary = engine.merge_timeline_parts(chunk_summaries)
                try:
                    fact_outcome = await engine.extract_facts_from_text_outcome(
                        chunk_summary,
                        source_episode=f"episodes/{summary_date.isoformat()}.md",
                        source_session_id="consolidation:daily",
                    )
                    facts_extracted += int(getattr(fact_outcome, "facts_extracted", 0) or 0)
                    facts_failed += int(getattr(fact_outcome, "facts_failed", 0) or 0)
                except Exception as exc:
                    from core.memory.facts.observability import warn_rate_limited

                    warn_rate_limited(
                        logger,
                        "fact_extraction.phase_a",
                        "[%s] Phase A atomic fact extraction failed",
                        self.name,
                        exc_info=(type(exc), exc, exc.__traceback__),
                    )
                    facts_failed += 1

            if episode_parts:
                merged_episodes = engine.merge_timeline_parts(episode_parts)
                episode_path = engine.write_consolidated_episode(summary_date, merged_episodes)
                engine.record_consolidated_chunks(
                    summary_date,
                    completed_chunks,
                    noop_cron_filtered=filtered_by_date.get(summary_date, False),
                    input_profile=input_profile_by_date.get(summary_date, compaction_settings.profile),
                )
                logger.info(
                    "[%s] Phase A complete: date=%s wrote=%d chars to %s facts_extracted=%d facts_failed=%d",
                    self.name,
                    summary_date.isoformat(),
                    len(merged_episodes),
                    episode_path.name,
                    facts_extracted,
                    facts_failed,
                )
                episode_summaries.append(f"## {summary_date.isoformat()}\n\n{merged_episodes}")

            if failed_chunks:
                reason = failure_reason or "one or more chunk prompts failed"
                logger.warning(
                    "[%s] Episode summary failed date=%s failed_chunks=%d/%d reason=%s",
                    self.name,
                    summary_date.isoformat(),
                    failed_chunks,
                    len(chunks),
                    reason[:240].replace("\n", " "),
                )
            done_bytes += day_bytes
            done_seconds += time.monotonic() - day_started

        import time as _time

        return CycleResult(
            trigger="consolidation:daily",
            action="completed" if episode_summaries else "skipped",
            summary=("\n\n".join(episode_summaries) if episode_summaries else t("anima.no_episodes_today")),
            duration_ms=int((_time.monotonic() - start_mono) * 1000),
        )

    async def _run_daily_consolidation(
        self: _LifecycleHost,
        engine: Any,
    ) -> CycleResult:
        """Run daily episode extraction or project archive consolidation.

        Daily consolidation extracts structured timeline episodes from
        activity_log. When an engine has a project, consolidate its recent
        project episodes into project knowledge with the Anima's tool loop.
        """
        import time as _time

        from core.config import load_config

        cfg = load_config()
        consolidation_model = cfg.consolidation.llm_model
        start_mono = _time.monotonic()
        project = getattr(engine, "project", None)

        # ── Phase A: Episode extraction ─────────────────────────
        if project is None:
            return await LifecycleMixin._run_daily_episode_summaries(
                self,
                engine,
                cfg=cfg,
                model=consolidation_model,
                start_mono=start_mono,
            )

        episodes = engine._collect_recent_episodes(hours=24)
        if not episodes:
            return CycleResult(
                trigger="consolidation:daily",
                action="skipped",
                summary=t("anima.no_episodes_today"),
                duration_ms=int((_time.monotonic() - start_mono) * 1000),
            )
        episodes_summary = "\n\n".join(f"## {e['date']} {e['time']}\n{e['content']}" for e in episodes)

        prompt = load_prompt(
            "memory/consolidation_instruction",
            anima_name=self.name,
            episodes_summary=episodes_summary,
            # Retain formatting compatibility with previously installed templates.
            resolved_events_summary="",
            reflections_summary="",
            knowledge_files_list="",
            merge_candidates="",
            error_patterns_summary="",
        )
        if project is not None:
            prompt += (
                "\n\n## Project archive boundary\n"
                f"Read episodes only from `episodes/projects/{project}/`. "
                f"Read and write knowledge only in `knowledge/projects/{project}/`. "
                "Do not use or modify memory outside this project archive."
            )

        base_model_config = self.memory.read_model_config()
        consolidation_model_config = _consolidation_model_config(
            base_model_config,
            consolidation_model,
            cfg,
        )
        logger.info(
            "[%s] Project consolidation: knowledge update with consolidation model=%s",
            self.name,
            consolidation_model_config.model,
        )

        agent = _agent_for_lane(self, "background")
        async with _agent_session_context(self, "background"):
            if hasattr(self, "_get_interrupt_event"):
                self._get_interrupt_event("_background").clear()
                agent.set_interrupt_event(self._get_interrupt_event("_background"))
            if hasattr(agent, "_tool_handler"):
                agent._tool_handler.set_session_origin(ORIGIN_SYSTEM)
            try:
                result = await agent.run_cycle(
                    prompt,
                    trigger="consolidation:daily",
                    thread_id="consolidation-daily",
                    message_intent="request",
                    model_config_override=consolidation_model_config,
                )
            except TimeoutError:
                logger.warning(
                    "consolidation_timeout anima=%s phase=project type=daily",
                    self.name,
                )
                raise

        autolearn = self._run_autonomous_skill_learning()
        summary = result.summary or ""
        truncated = _project_consolidation_was_interrupted(result)
        if truncated:
            summary += "\n\n[TRUNCATED] Project consolidation was interrupted; partial outputs were kept."
        if autolearn is not None and autolearn.report_lines:
            summary = (summary + "\n\n" if summary else "") + "\n".join(autolearn.report_lines)

        elapsed_ms = int((_time.monotonic() - start_mono) * 1000)
        return CycleResult(
            trigger="consolidation:daily",
            action="truncated" if truncated else "completed",
            summary=summary,
            duration_ms=elapsed_ms,
        )

    async def _run_weekly_consolidation(
        self: _LifecycleHost,
        engine: Any,
    ) -> CycleResult:
        """Execute weekly consolidation with the configured consolidation model."""
        import time as _time

        from core.config import load_config

        cfg = load_config()
        start_mono = _time.monotonic()
        project = getattr(engine, "project", None)
        weekly_model = getattr(cfg.consolidation, "weekly_llm_model", None)
        weekly_credential = getattr(cfg.consolidation, "weekly_llm_credential", None) or ""
        if weekly_model:
            consolidation_model = str(weekly_model)
        else:
            consolidation_model = str(cfg.consolidation.llm_model)
            weekly_credential = ""

        try:
            merge_candidates = await asyncio.to_thread(engine._find_merge_candidates, max_pairs=30)
        except Exception:
            logger.debug("[%s] merge candidate detection failed", self.name, exc_info=True)
            merge_candidates = []
        merge_candidates_text = _format_merge_candidates(merge_candidates)

        try:
            conflict_candidates = engine._find_conflicting_fact_candidates(max_pairs=20)
        except Exception:
            logger.debug("[%s] conflicting-fact candidate detection failed", self.name, exc_info=True)
            conflict_candidates = []
        conflict_candidates_text = _format_conflict_candidates(conflict_candidates)

        try:
            from core.memory.maintenance.forgetting import ForgettingEngine

            forgetting_candidates = await asyncio.to_thread(
                ForgettingEngine(self.anima_dir, self.name).list_forgetting_candidates,
                max_items=20,
            )
        except Exception:
            logger.debug("[%s] forgetting candidate detection failed", self.name, exc_info=True)
            forgetting_candidates = []
        forgetting_candidates_text = _format_forgetting_candidates(forgetting_candidates)

        hygiene_section = ""
        if project is None:
            try:
                from core.memory.maintenance.hygiene import scan_memory_hygiene

                hygiene_section = _format_hygiene_section(scan_memory_hygiene(self.anima_dir))
            except Exception:
                logger.debug("[%s] memory hygiene scan failed", self.name, exc_info=True)

        prompt = load_prompt(
            "memory/weekly_consolidation_instruction",
            anima_name=self.name,
            knowledge_files_list="",
            merge_candidates=merge_candidates_text,
            conflict_candidates=conflict_candidates_text,
            forgetting_candidates=forgetting_candidates_text,
            total_knowledge_count=0,
            hygiene_section=hygiene_section,
        )
        if project is not None:
            prompt += (
                "\n\n## Project archive boundary\n"
                f"Read and write knowledge only in `knowledge/projects/{project}/`. "
                "Do not use or modify memory outside this project archive."
            )

        base_model_config = self.memory.read_model_config()
        consolidation_model_config = _consolidation_model_config(
            base_model_config,
            consolidation_model,
            cfg,
            credential=weekly_credential,
        )
        logger.info(
            "[%s] Weekly consolidation: knowledge extraction with consolidation model=%s",
            self.name,
            consolidation_model_config.model,
        )
        agent = _agent_for_lane(self, "background")
        async with _agent_session_context(self, "background"):
            if hasattr(self, "_get_interrupt_event"):
                self._get_interrupt_event("_background").clear()
                agent.set_interrupt_event(self._get_interrupt_event("_background"))
            if hasattr(agent, "_tool_handler"):
                agent._tool_handler.set_session_origin(ORIGIN_SYSTEM)
            result = await agent.run_cycle(
                prompt,
                trigger="consolidation:weekly",
                thread_id="consolidation-weekly",
                message_intent="request",
                model_config_override=consolidation_model_config,
            )

        autolearn = self._run_autonomous_skill_learning()
        summary = result.summary or ""
        if autolearn is not None and autolearn.report_lines:
            summary = (summary + "\n\n" if summary else "") + "\n".join(autolearn.report_lines)

        elapsed_ms = int((_time.monotonic() - start_mono) * 1000)
        return CycleResult(
            trigger="consolidation:weekly",
            action="completed",
            summary=summary,
            duration_ms=elapsed_ms,
        )

    def _run_autonomous_skill_learning(self: _LifecycleHost):
        """Run deterministic skill auto-learning after successful consolidation."""
        from core.config import load_config

        if not load_config().consolidation.skill_autolearn_enabled:
            return None
        from core.skills.autolearn_lifecycle import run_autonomous_skill_learning_for

        return run_autonomous_skill_learning_for(self)

    async def run_cron_task(
        self: _LifecycleHost,
        task_name: str,
        description: str,
        command_output: str | None = None,
        skills: list[str] | None = None,
    ) -> CycleResult:
        """Execute a cron LLM task with heartbeat-equivalent context.

        Args:
            task_name: Cron task name from cron.md.
            description: Task description/instruction.
            command_output: Optional stdout from a preceding command cron.
            skills: Optional cron skill references from cron.md.
        """
        self._get_interrupt_event("_background").clear()
        logger.info("[%s] run_cron_task WAITING_LOCK task=%s", self.name, task_name)
        from core.tooling.handler import active_session_type

        try:
            async with self._background_lock:
                logger.info("[%s] run_cron_task START task=%s", self.name, task_name)
                self._mark_busy_start()
                _keepalive = asyncio.create_task(self._keepalive_while_busy())
                self._status_slots["background"] = "working"
                self._task_slots["background"] = task_name

                cron_skill_rejections = []
                cron_skill_warnings = []
                prompt = self._build_cron_prompt(
                    task_name,
                    description,
                    command_output=command_output,
                    skills=skills,
                    skill_rejections_out=cron_skill_rejections,
                    skill_warnings_out=cron_skill_warnings,
                )
                if inspect.isawaitable(prompt):
                    prompt = await prompt

                # ── Background model swap ──
                try:
                    agent = _agent_for_lane(self, "background")
                    async with _agent_session_context(self, "background"):
                        agent.set_interrupt_event(self._get_interrupt_event("_background"))
                        _session_token = agent._tool_handler.set_active_session_type("cron")
                        agent._tool_handler.set_session_origin(ORIGIN_SYSTEM)
                        bg_config = self._resolve_background_config("cron")
                        active_config = bg_config or agent.model_config

                        async def _run(config):  # noqa: ANN001
                            return await agent.run_cycle(
                                prompt,
                                trigger=f"cron:{task_name}",
                                thread_id=_cron_thread_id(task_name),
                                model_config_override=config,
                            )

                        try:
                            result = await run_with_model_fallback(
                                _run,
                                activity=self._activity,
                                primary_config=active_config,
                                active_config=active_config,
                                channel="cron",
                            )
                        except asyncio.CancelledError:
                            current = asyncio.current_task()
                            if current is not None and current.cancelling():
                                raise
                            logger.warning(
                                "[%s] run_cron_task cancelled by request; runner remains alive task=%s",
                                self.name,
                                task_name,
                            )
                            return CycleResult(
                                trigger=f"cron:{task_name}",
                                action="cancelled",
                                summary="Cron task cancelled",
                                duration_ms=0,
                            )
                        finally:
                            active_session_type.reset(_session_token)
                    self._last_activity = now_local()

                    # Record cron execution result
                    rejection_dicts = [
                        {"ref": rejection.ref, "reason": rejection.reason} for rejection in cron_skill_rejections
                    ]
                    warning_dicts = [
                        {
                            "ref": warning.ref,
                            "reason": warning.reason,
                            "name": warning.name,
                            "path": warning.path,
                        }
                        for warning in cron_skill_warnings
                    ]
                    result.cron_skill_rejections = rejection_dicts
                    result.cron_skill_warnings = warning_dicts
                    cron_summary = (
                        f"[ERROR:{result.reason or result.stop_kind}] {result.summary}"
                        if result.action == "error"
                        else result.summary
                    )
                    self.memory.append_cron_log(
                        task_name,
                        summary=cron_summary,
                        duration_ms=result.duration_ms,
                        skill_rejections=rejection_dicts,
                    )

                    # Activity log: cron executed
                    await self._activity.alog(
                        "cron_executed",
                        summary=t("anima.cron_task_summary", task=task_name),
                        content=result.summary[:500] if result else "",
                        meta={
                            "task_name": task_name,
                            "duration_ms": result.duration_ms if result else 0,
                            "status": "failed" if result.action == "error" else "completed",
                            "reason": result.reason,
                            "stop_kind": result.stop_kind,
                            "skill_rejections": rejection_dicts,
                            "skill_warnings": warning_dicts,
                        },
                    )
                    if warning_dicts:
                        await self._activity.alog(
                            "cron_skill_warning",
                            summary=f"Cron skill warnings: {task_name}",
                            meta={
                                "task_name": task_name,
                                "skill_warnings": warning_dicts,
                            },
                        )

                    logger.info(
                        "[%s] run_cron_task END task=%s duration_ms=%d",
                        self.name,
                        task_name,
                        result.duration_ms,
                    )
                    # Preserve current_state.md across normal cron boundaries.
                    # Stale idle cleanup is handled by taskboard housekeeping.
                    self._enforce_state_size_limit()
                    return result
                except Exception as exc:
                    logger.exception(
                        "[%s] run_cron_task FAILED task=%s",
                        self.name,
                        task_name,
                    )
                    try:
                        self.memory.append_cron_log(
                            task_name,
                            summary=f"[ERROR:{type(exc).__name__}] {str(exc)}",
                            duration_ms=0,
                            skill_rejections=[
                                {"ref": rejection.ref, "reason": rejection.reason}
                                for rejection in cron_skill_rejections
                            ],
                        )
                    except Exception:
                        logger.warning("[%s] Failed to append cron error log", self.name, exc_info=True)
                    # Activity log: error (safe=True to prevent double-fault)
                    await self._activity.alog(
                        "error",
                        summary=t("anima.cron_task_error", exc=type(exc).__name__),
                        meta={"phase": "run_cron_task", "error": str(exc)[:200]},
                        safe=True,
                    )
                    raise
                finally:
                    _keepalive.cancel()
                    self._status_slots["background"] = "idle"
                    self._task_slots["background"] = ""
        finally:
            self._notify_lock_released()

    async def run_cron_command(
        self: _LifecycleHost,
        task_name: str,
        *,
        command: str | None = None,
        tool: str | None = None,
        args: dict[str, Any] | None = None,
        env: dict[str, str] | None = None,
        serialize: bool = True,
    ) -> dict[str, Any]:
        """Execute a command-type cron task (bash or internal tool).

        Args:
            task_name: Task identifier for logging
            command: Bash command to execute (mutually exclusive with tool)
            tool: Internal tool name (mutually exclusive with command)
            args: Tool arguments (only used with tool)
            env: Optional command environment; ``None`` inherits the current environment.
            serialize: Acquire the shared background lock before running the command.

        Returns:
            Dictionary with execution results (exit_code, stdout, stderr, duration_ms)
        """
        logger.info("[%s] run_cron_command WAITING_LOCK task=%s", self.name, task_name)
        start_ms = time.time_ns() // 1_000_000

        stdout = ""
        stderr = ""
        exit_code = 0

        from core.tooling.handler import active_session_type

        try:
            async with AsyncExitStack() as lock_stack:
                if serialize:
                    await lock_stack.enter_async_context(self._background_lock)
                logger.info("[%s] run_cron_command START task=%s", self.name, task_name)
                from core.execution.session.session_context import RuntimeSessionContext, runtime_session_scope

                _runtime_ctx = RuntimeSessionContext.create(
                    session_type="cron",
                    thread_id=_cron_thread_id(task_name),
                    trigger=f"cron:{task_name}",
                )
                active_commands = getattr(self, "_active_cron_commands", None)
                if active_commands is None:
                    active_commands = {}
                    self._active_cron_commands = active_commands
                active_key = f"{task_name}:{id(asyncio.current_task())}"
                first_command = not active_commands
                active_commands[active_key] = (task_name, None)
                if first_command:
                    self._mark_busy_start()
                else:
                    mark_progress = getattr(self, "_mark_busy_progress", None)
                    if callable(mark_progress):
                        mark_progress()
                self._status_slots["background"] = "working"
                self._task_slots["background"] = task_name

                proc = None
                try:
                    if command:
                        normalized_command = command.strip()
                        if os.name == "nt":
                            if set(normalized_command) == {"="}:
                                stderr = f"Blocked suspicious cron command on Windows: {command}"
                                exit_code = 1
                                logger.warning(
                                    "[%s] Skipping suspicious cron command on Windows: %s",
                                    self.name,
                                    command,
                                )
                                self._last_activity = now_local()
                                return {
                                    "task": task_name,
                                    "exit_code": exit_code,
                                    "stdout": "",
                                    "stderr": stderr,
                                    "duration_ms": (time.time_ns() // 1_000_000) - start_ms,
                                }
                            if normalized_command.startswith("/") and not normalized_command.startswith("//"):
                                stderr = f"Blocked POSIX-only cron command on Windows: {command}"
                                exit_code = 1
                                logger.warning(
                                    "[%s] Skipping POSIX-only cron command on Windows: %s",
                                    self.name,
                                    command,
                                )
                                self._last_activity = now_local()
                                return {
                                    "task": task_name,
                                    "exit_code": exit_code,
                                    "stdout": "",
                                    "stderr": stderr,
                                    "duration_ms": (time.time_ns() // 1_000_000) - start_ms,
                                }
                        # Execute bash command
                        logger.debug("[%s] Executing bash: %s", self.name, command)
                        proc = await asyncio.create_subprocess_shell(
                            command,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                            env=env,
                            **subprocess_session_kwargs(),
                        )
                        active_commands[active_key] = (task_name, proc.pid)
                        mark_progress = getattr(self, "_mark_busy_progress", None)
                        if callable(mark_progress):
                            mark_progress()
                        try:
                            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                                proc.communicate(),
                                timeout=_CRON_COMMAND_TIMEOUT_SECONDS,
                            )
                        except TimeoutError:
                            logger.warning(
                                "[%s] Cron command '%s' timed out after %.0fs, killing process group",
                                self.name,
                                task_name,
                                _CRON_COMMAND_TIMEOUT_SECONDS,
                            )
                            await _kill_cron_command_group(proc)
                            stderr = f"TimeoutError: cron command exceeded {_CRON_COMMAND_TIMEOUT_SECONDS:g}s limit"
                            exit_code = 1
                        else:
                            stdout = stdout_bytes.decode("utf-8", errors="replace")
                            stderr = stderr_bytes.decode("utf-8", errors="replace")
                            exit_code = proc.returncode or 0

                    elif tool:
                        # Execute internal tool via ToolHandler
                        logger.debug("[%s] Executing tool: %s", self.name, tool)
                        agent = _agent_for_lane(self, "background")
                        async with _agent_session_context(self, "background"):
                            agent._tool_handler.bind_runtime_session(_runtime_ctx)
                            _session_token = agent._tool_handler.set_active_session_type("cron")
                            agent._tool_handler.set_session_origin(ORIGIN_SYSTEM)
                            try:
                                with runtime_session_scope(_runtime_ctx):
                                    result = agent._tool_handler.handle(tool, args or {})
                            finally:
                                active_session_type.reset(_session_token)
                        stdout = str(result)
                        exit_code = 0

                    else:
                        stderr = "Neither command nor tool specified"
                        exit_code = 1

                    self._last_activity = now_local()

                except Exception as exc:
                    stderr = f"{type(exc).__name__}: {exc}"
                    exit_code = 1
                    logger.exception("[%s] run_cron_command FAILED task=%s", self.name, task_name)
                    # Activity log: error (safe=True to prevent double-fault)
                    await self._activity.alog(
                        "error",
                        summary=t("anima.cron_cmd_error", exc=type(exc).__name__),
                        meta={"phase": "run_cron_command", "error": str(exc)[:200]},
                        safe=True,
                    )
                finally:
                    if proc is not None and proc.returncode is None:
                        await _kill_cron_command_group(proc)
                    active_commands.pop(active_key, None)
                    if active_commands:
                        remaining = list(active_commands.values())[-1][0]
                        self._status_slots["background"] = "working"
                        self._task_slots["background"] = remaining
                        mark_progress = getattr(self, "_mark_busy_progress", None)
                        if callable(mark_progress):
                            mark_progress()
                    else:
                        self._status_slots["background"] = "idle"
                        self._task_slots["background"] = ""

            duration_ms = (time.time_ns() // 1_000_000) - start_ms

            # Log to cron_log with command-specific format
            await asyncio.to_thread(
                self.memory.append_cron_command_log,
                task_name,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
            )

            # Activity log: cron command executed (intentionally logs even on
            # failure — exit_code captures the error state, unlike run_cron_task
            # which re-raises and never reaches this point on error)
            await self._activity.alog(
                "cron_executed",
                summary=t("anima.cron_cmd_summary", task=task_name),
                meta={"task_name": task_name, "exit_code": exit_code, "command": command or "", "tool": tool or ""},
            )

            logger.info(
                "[%s] run_cron_command END task=%s exit_code=%d duration_ms=%d",
                self.name,
                task_name,
                exit_code,
                duration_ms,
            )

            return {
                "task": task_name,
                "exit_code": exit_code,
                "stdout": stdout[:1000],  # Preview for response
                "stderr": stderr[:1000],
                "duration_ms": duration_ms,
            }

        finally:
            self._notify_lock_released()
