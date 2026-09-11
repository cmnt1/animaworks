from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""PrimingEngine - slim orchestrator for six-channel memory priming."""

import asyncio
import logging
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from core.file_access_policy import find_denied_root, load_denied_roots
from core.i18n import t

# Import submodules directly to avoid circular import when package __init__ loads engine
from core.memory.priming import (
    channel_a as _channel_a,
)
from core.memory.priming import (
    channel_b as _channel_b,
)
from core.memory.priming import (
    channel_c as _channel_c,
)
from core.memory.priming import (
    channel_e as _channel_e,
)
from core.memory.priming import (
    channel_f as _channel_f,
)
from core.memory.priming import (
    channel_g as _channel_g,
)
from core.memory.priming import (
    outbound as _outbound,
)
from core.memory.priming.constants import (
    _BUDGET_GRAPH_CONTEXT,
    _DEFAULT_MAX_PRIMING_TOKENS,
)
from core.memory.priming.items import ItemizedMemory, MemoryItem, render_items, select_within_budget
from core.memory.priming.result import PrimingResult
from core.memory.priming.utils import RetrieverCache, build_queries, extract_keywords, truncate_head, truncate_tail

logger = logging.getLogger("animaworks.priming")

_IMPORTANT_HEADER = "### [IMPORTANT] Knowledge (summary pointers)"
_NOTIFICATIONS_HEADER = "## Pending Human Notifications (last 24h)"

# TTL (seconds) before a failed MemoryBackend init is retried once.  Prevents a
# transient failure from permanently disabling graph/episode priming.
_BACKEND_INIT_RETRY_TTL_SECONDS = 300.0


class PrimingEngine:
    """Automatic memory priming engine.

    Executes 6-channel parallel memory retrieval:
      A. Sender profile (direct file read)
      B. Recent activity (unified activity log, replaces old episodes + channels)
      C. Related knowledge (dense vector search)
      E. Pending tasks (persistent task queue summary)
      F. Episodes (dense vector search over episode memory)
      G. Graph context (community summaries + recent facts via MemoryBackend)
    """

    def __init__(
        self,
        anima_dir: Path,
        shared_dir: Path | None = None,
        context_window: int = 0,
    ) -> None:
        self.anima_dir = anima_dir
        self.shared_dir = shared_dir
        self.context_window = context_window
        self.episodes_dir = anima_dir / "episodes"
        self.knowledge_dir = anima_dir / "knowledge"
        self._retriever_cache = RetrieverCache()
        self._retriever: Any | None = None
        self._retriever_initialized = False
        self._config_loaded = False
        self._channel_timeout_seconds = 60.0
        self._get_active_parallel_tasks: Callable[[], dict[str, dict]] | None = None
        self._memory_backend: Any | None = None
        self._memory_backend_init_failed = False
        # Monotonic timestamp of the last failed backend init; ``None`` when the
        # latch was set without a timestamp (e.g. tests) → treated as still latched.
        self._memory_backend_init_failed_at: float | None = None

    def _get_or_create_retriever(self):
        """Get or create a retriever instance from the RetrieverCache."""
        if self._retriever is not None:
            return self._retriever
        return self._retriever_cache.get_or_create(self.anima_dir, self.knowledge_dir)

    def _get_retriever(self):
        """Delegate to _get_or_create_retriever (tests may patch either)."""
        return self._get_or_create_retriever()

    def _get_memory_backend(self):
        """Return lazy-initialized MemoryBackend from config.

        Resolution: per-anima status.json → global config → 'legacy'.
        """
        if self._memory_backend is not None:
            return self._memory_backend
        if self._memory_backend_init_failed:
            failed_at = self._memory_backend_init_failed_at
            if failed_at is None or (time.monotonic() - failed_at) < _BACKEND_INIT_RETRY_TTL_SECONDS:
                return None
            # TTL elapsed: fall through to attempt one re-initialization.
        first_failure = not self._memory_backend_init_failed
        try:
            from core.memory.backend.registry import get_backend, resolve_backend_type

            backend_type = resolve_backend_type(self.anima_dir)
            self._memory_backend = get_backend(backend_type, self.anima_dir)
            self._memory_backend_init_failed = False
            self._memory_backend_init_failed_at = None
            return self._memory_backend
        except Exception:
            if first_failure:
                logger.warning("Failed to init MemoryBackend for priming", exc_info=True)
            else:
                logger.debug("Failed to init MemoryBackend for priming (retry)", exc_info=True)
            self._memory_backend_init_failed = True
            self._memory_backend_init_failed_at = time.monotonic()
            return None

    def _graph_context_enabled(self) -> bool:
        """Return whether channel G should be scheduled for this engine."""
        from core.memory.backend.legacy import LegacyRAGBackend

        if self._memory_backend is not None:
            return not isinstance(self._memory_backend, LegacyRAGBackend)
        try:
            from core.memory.backend.registry import resolve_backend_type

            return resolve_backend_type(self.anima_dir) != "legacy"
        except Exception:
            # Backend resolution itself defaults to legacy. Match that safe
            # default here without constructing a backend just to skip G.
            return False

    def _load_channel_timeout(self) -> None:
        if self._config_loaded:
            return
        self._config_loaded = True
        try:
            from core.config.models import load_config

            self._channel_timeout_seconds = float(getattr(load_config().priming, "channel_timeout_seconds", 60.0))
        except Exception:
            logger.debug("Failed to load priming channel timeout; using default", exc_info=True)

    async def _run_priming_channel(self, name: str, coro):
        self._load_channel_timeout()
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(coro, timeout=self._channel_timeout_seconds)
            if isinstance(result, tuple):
                result_chars = sum(len(part) for part in result if isinstance(part, str))
            else:
                result_chars = len(result) if isinstance(result, str) else 0
            logger.info(
                "Priming channel %s complete: elapsed=%.3fs chars=%d",
                name,
                time.perf_counter() - started,
                result_chars,
            )
            return result
        except TimeoutError:
            logger.warning(
                "Priming channel %s timed out: elapsed=%.3fs limit=%.1fs; degrading channel only",
                name,
                time.perf_counter() - started,
                self._channel_timeout_seconds,
            )
            return ""
        except asyncio.CancelledError:
            raise

    @staticmethod
    def _extract_summary(content: str, metadata: dict) -> str:
        """Delegate to standalone extract_summary for backward compat."""
        from core.memory.priming.channel_c import extract_summary

        title, _ = extract_summary(content, metadata)
        return title

    @staticmethod
    def _to_read_memory_path(metadata: dict, anima_name: str) -> str:
        """Delegate to standalone to_read_memory_path for backward compat."""
        from core.memory.priming.channel_c import to_read_memory_path

        return to_read_memory_path(metadata, anima_name)

    def _read_shared_channels(self, limit_per_channel: int = 5) -> list:
        """Delegate to standalone read_shared_channels for backward compat."""
        from core.memory.priming.channel_b import read_shared_channels

        return read_shared_channels(self.anima_dir, self.shared_dir, limit_per_channel=limit_per_channel)

    async def _fallback_episodes_and_channels(self) -> str:
        """Delegate to standalone fallback for backward compat."""
        from core.memory.priming.channel_b import fallback_episodes_and_channels

        return await fallback_episodes_and_channels(self.anima_dir, self.shared_dir)

    async def prime_memories(
        self,
        message: str,
        sender_name: str = "human",
        channel: str = "chat",
        intent: str = "",
        recent_human_messages: list[str] | None = None,
        profile: str = "full",
        max_tokens: int | None = None,
        include_related: bool = True,
    ) -> PrimingResult:
        """Prime memories based on incoming message.

        A single ``max_tokens`` budget governs every itemized channel; pointer
        cues are intentionally small so the resident surface stays minimal.
        """
        logger.debug(
            "Priming memories: sender=%s, message_len=%d, channel=%s",
            sender_name,
            len(message),
            channel,
        )

        token_budget = _DEFAULT_MAX_PRIMING_TOKENS if max_tokens is None else max_tokens

        if profile == "compact":
            return await self._prime_compact(
                message, sender_name, channel, intent, token_budget, recent_human_messages, include_related
            )

        logger.debug("Token budget: %d", token_budget)

        effective_message = message
        if not effective_message.strip():
            state_path = self.anima_dir / "state" / "current_state.md"
            try:
                denied_roots = load_denied_roots(self.anima_dir)
                resolved_state_path = state_path.resolve()
                if find_denied_root(resolved_state_path, denied_roots) is None and resolved_state_path.is_file():
                    effective_message = resolved_state_path.read_text(encoding="utf-8")[:300]
            except (OSError, RuntimeError):
                pass

        keywords = self._extract_keywords(message or effective_message)
        knowledge_queries = build_queries(effective_message, keywords, recent_human_messages)
        knowledge_search_cache = _channel_c.KnowledgeSearchCache()

        channel_calls = [
            ("A", self._channel_a_sender_profile(sender_name)),
            ("B", self._channel_b_recent_activity(sender_name, keywords, channel=channel)),
            (
                "C0",
                self._channel_c0_important_knowledge(
                    knowledge_queries,
                    trigger=channel,
                    search_cache=knowledge_search_cache,
                ),
            ),
            (
                "C",
                self._channel_c_related_knowledge(
                    keywords,
                    message=effective_message,
                    recent_human_messages=recent_human_messages,
                    trigger=channel,
                    search_cache=knowledge_search_cache,
                ),
            ),
            ("E", self._channel_e_pending_tasks()),
            ("outbound", self._collect_recent_outbound()),
            (
                "F",
                self._channel_f_episodes(
                    keywords,
                    message=message,
                    recent_human_messages=recent_human_messages,
                    trigger=channel,
                ),
            ),
            (
                "pending_human_notifications",
                self._collect_pending_human_notifications(channel=channel),
            ),
        ]
        graph_context_enabled = self._graph_context_enabled()
        if graph_context_enabled:
            channel_calls.append(("G", self._channel_g_graph_context(effective_message, trigger=channel)))
        else:
            # Legacy has no graph data, so creating/scheduling G only burns a
            # channel slot and reserves budget that can never produce context.
            logger.debug("Priming channel G not scheduled for legacy backend")

        channel_names = [name for name, _ in channel_calls]
        gathered = await asyncio.gather(
            *(self._run_priming_channel(name, coro) for name, coro in channel_calls),
            return_exceptions=True,
        )
        results = dict(zip(channel_names, gathered, strict=True))

        def unpack_itemized(value: object) -> tuple[str, tuple[MemoryItem, ...]]:
            if not isinstance(value, str):
                return "", ()
            return str(value), tuple(getattr(value, "items", ()))

        sender_profile = results["A"] if isinstance(results["A"], str) else ""
        recent_activity, recent_activity_items = unpack_itemized(results["B"])

        important_knowledge, important_items = unpack_itemized(results["C0"])
        channel_c_result = results["C"]
        if isinstance(channel_c_result, tuple):
            related_knowledge, related_items = unpack_itemized(channel_c_result[0])
            related_knowledge_untrusted, untrusted_items = unpack_itemized(channel_c_result[1])
        else:
            related_knowledge = ""
            related_knowledge_untrusted = ""
            related_items = ()
            untrusted_items = ()
        channel_c_related_knowledge = related_knowledge

        pending_tasks, pending_task_items = unpack_itemized(results["E"])
        recent_outbound, outbound_items = unpack_itemized(results["outbound"])
        episodes, episode_items = unpack_itemized(results["F"])
        pending_human_notifications, notification_items = unpack_itemized(results["pending_human_notifications"])
        graph_value = results.get("G", "")
        graph_context = graph_value if isinstance(graph_value, str) else ""

        for name, r in results.items():
            if isinstance(r, Exception):
                logger.warning("Priming channel %s failed: %s", name, r)

        # Channel B carries recent-conversation dates in ``updated``; exclude the
        # same-date episodes from Channel F so recent conversation is not
        # duplicated by the episode channel.
        b_dates = {item.updated[:10] for item in recent_activity_items if item.updated}
        episode_items = tuple(_channel_f.exclude_episodes_for_dates(list(episode_items), b_dates))

        final_items: dict[str, tuple[MemoryItem, ...]] = {}

        def _select(
            source: str,
            items: Sequence[MemoryItem],
            text: str,
            *,
            header: str = "",
            tail: bool = False,
        ) -> str:
            if items:
                selected = select_within_budget(items, token_budget)
                final_items[source] = tuple(selected)
                return render_items(selected, header)
            final_items[source] = ()
            if not text:
                return ""
            return truncate_tail(text, token_budget) if tail else truncate_head(text, token_budget)

        if important_items:
            important_text = _select("important_knowledge", important_items, "", header=_IMPORTANT_HEADER)
        elif important_knowledge:
            important_text = truncate_head(important_knowledge, token_budget)
        else:
            important_text = ""

        medium_text = _select("related_knowledge", related_items, channel_c_related_knowledge)
        related_knowledge_text = (
            f"{important_text}\n\n{medium_text}"
            if important_text and medium_text
            else important_text or medium_text
        )

        untrusted_text = _select("related_knowledge_untrusted", untrusted_items, related_knowledge_untrusted)
        pending_tasks_text = _select("pending_tasks", pending_task_items, pending_tasks)
        recent_outbound_text = _select(
            "recent_outbound", outbound_items, recent_outbound, header=t("priming.outbound_header")
        )
        episodes_text = _select("episodes", episode_items, episodes, tail=True)
        notifications_text = _select(
            "pending_human_notifications", notification_items, pending_human_notifications, header=_NOTIFICATIONS_HEADER
        )
        graph_context_text = truncate_tail(graph_context, token_budget)

        result = PrimingResult(
            sender_profile=truncate_head(sender_profile, token_budget),
            recent_activity=_select("recent_activity", recent_activity_items, recent_activity, tail=True),
            related_knowledge=related_knowledge_text,
            related_knowledge_untrusted=untrusted_text,
            pending_tasks=pending_tasks_text,
            recent_outbound=recent_outbound_text,
            episodes=episodes_text,
            pending_human_notifications=notifications_text,
            graph_context=graph_context_text,
            items=final_items,
        )

        logger.info(
            "Priming complete: %d chars (~%d tokens), sender_prof=%d, activity=%d, "
            "knowledge=%d, episodes=%d, outbound=%d",
            result.total_chars(),
            result.estimated_tokens(),
            len(result.sender_profile),
            len(result.recent_activity),
            len(result.related_knowledge),
            len(result.episodes),
            len(result.recent_outbound),
        )

        return result


    async def _prime_compact(
        self,
        message: str,
        sender_name: str,
        channel: str,
        intent: str,
        token_budget: int,
        recent_human_messages: list[str] | None,
        include_related: bool,
    ) -> PrimingResult:
        """Retrieve only event-relevant sources; preserve notifications independently.

        Resident pointers are explicit opt-ins. General activity, graph and
        episode expansion belong to explicit search or the opt-in full profile.
        """
        started = time.perf_counter()
        calls = [
            ("A", self._channel_a_sender_profile(sender_name)),
            ("E", self._channel_e_pending_tasks()),
            ("C0", self._channel_c0_important_knowledge([], trigger=channel, resident_only=True)),
            ("outbound", self._collect_recent_outbound()),
            ("pending_human_notifications", self._collect_pending_human_notifications(channel=channel)),
        ]
        # Use event/intent contracts, not a new text classifier or model list.
        related = channel in {"chat", "task"} or intent in {"question", "request", "delegation"}
        if include_related and related and message.strip():
            calls.append(
                (
                    "C",
                    self._channel_c_related_knowledge(
                        self._extract_keywords(message),
                        message=message,
                        recent_human_messages=recent_human_messages,
                        trigger=channel,
                    ),
                )
            )
        values = await asyncio.gather(
            *(self._run_priming_channel(name, coro) for name, coro in calls),
            return_exceptions=True,
        )
        results = dict(zip((name for name, _ in calls), values, strict=True))

        def content(name: str) -> str:
            value = results.get(name, "")
            return value if isinstance(value, str) else ""

        def bounded(value: str, budget: int) -> str:
            if isinstance(value, ItemizedMemory):
                return render_items(select_within_budget(value.items, budget), "")
            return truncate_head(value, budget)

        result = PrimingResult(
            sender_profile=truncate_head(content("A"), min(400, token_budget // 4)),
            pending_tasks=bounded(content("E"), min(500, token_budget // 3)),
            resident_knowledge=content("C0"),
            recent_outbound=truncate_tail(content("outbound"), 250),
            # Notification delivery is a separate contract, never dropped to
            # meet a recall optimization budget.
            pending_human_notifications=content("pending_human_notifications"),
        )
        related_value = results.get("C")
        if isinstance(related_value, tuple):
            remaining = max(0, token_budget - result.estimated_tokens())
            trusted, untrusted = related_value
            result.related_knowledge += ("\n" if result.related_knowledge else "") + bounded(trusted, remaining)
            remaining = max(0, token_budget - result.estimated_tokens())
            result.related_knowledge_untrusted = bounded(untrusted, remaining)
        logger.info(
            "Priming compact: channels=%s related_searches=%d elapsed=%.3fs tokens=%d",
            ",".join(results),
            int("C" in results),
            time.perf_counter() - started,
            result.estimated_tokens(),
        )
        return result

    # ── Channel wrappers (delegate to modules; tests may patch these) ────

    async def _channel_a_sender_profile(self, sender_name: str) -> str:
        return await _channel_a.channel_a_sender_profile(self.anima_dir, sender_name)

    async def _channel_b_recent_activity(
        self,
        sender_name: str,
        keywords: list[str],
        *,
        channel: str = "",
    ) -> str:
        return await _channel_b.channel_b_recent_activity(
            self.anima_dir,
            self.shared_dir,
            sender_name,
            keywords,
            channel=channel,
        )

    async def _channel_c0_important_knowledge(
        self,
        queries: list[str] | None = None,
        *,
        trigger: str = "chat",
        resident_only: bool = False,
        search_cache: _channel_c.KnowledgeSearchCache | None = None,
    ) -> str:
        return await _channel_c.channel_c0_important_knowledge(
            self.anima_dir,
            self.knowledge_dir,
            self._get_retriever,
            queries,
            trigger=trigger,
            resident_only=resident_only,
            search_cache=search_cache,
        )

    async def _channel_c_related_knowledge(
        self,
        keywords: list[str],
        message: str = "",
        recent_human_messages: list[str] | None = None,
        trigger: str = "chat",
        search_cache: _channel_c.KnowledgeSearchCache | None = None,
    ) -> tuple[str, str]:
        return await _channel_c.channel_c_related_knowledge(
            self.anima_dir,
            self.knowledge_dir,
            self._get_retriever,
            keywords,
            message=message,
            recent_human_messages=recent_human_messages,
            trigger=trigger,
            search_cache=search_cache,
        )

    async def _channel_e_pending_tasks(self) -> str:
        return await _channel_e.channel_e_pending_tasks(
            self.anima_dir,
            self._get_active_parallel_tasks,
        )

    async def _collect_recent_outbound(self, max_entries: int = 3) -> str:
        return await _outbound.collect_recent_outbound(self.anima_dir, max_entries=max_entries)

    async def _channel_f_episodes(
        self,
        keywords: list[str],
        *,
        message: str = "",
        recent_human_messages: list[str] | None = None,
        trigger: str = "chat",
    ) -> str:
        return await _channel_f.channel_f_episodes(
            self.anima_dir,
            self.episodes_dir,
            self._get_retriever,
            keywords,
            message=message,
            recent_human_messages=recent_human_messages,
            get_memory_backend=self._get_memory_backend,
            trigger=trigger,
        )

    async def _collect_pending_human_notifications(self, *, channel: str = "") -> str:
        return await _outbound.collect_pending_human_notifications(self.anima_dir, channel=channel)

    async def _channel_g_graph_context(self, query: str, *, trigger: str = "chat") -> str:
        backend = self._get_memory_backend()
        if backend is None:
            return ""
        from core.memory.backend.legacy import LegacyRAGBackend

        if isinstance(backend, LegacyRAGBackend):
            logger.debug("Priming channel G skipped for legacy backend")
            return ""
        return await _channel_g.collect_graph_context(
            backend,
            query,
            budget_tokens=_BUDGET_GRAPH_CONTEXT,
            anima_dir=self.anima_dir,
            trigger=trigger,
        )

    def _extract_keywords(self, message: str) -> list[str]:
        """Backward compat: delegate to utils.extract_keywords."""
        return extract_keywords(message, self.knowledge_dir)

    async def _read_old_channels(self) -> str:
        """Backward compat: delegate to channel_b.read_old_channels."""
        return await _channel_b.read_old_channels(self.anima_dir, self.shared_dir)

    @staticmethod
    def _search_and_merge(retriever, queries, anima_name, *, memory_type, top_k, include_shared=False, min_score=None):
        """Backward compat: delegate to utils.search_and_merge."""
        from core.memory.priming.utils import search_and_merge as _search_and_merge

        return _search_and_merge(
            retriever,
            queries,
            anima_name,
            memory_type=memory_type,
            top_k=top_k,
            include_shared=include_shared,
            min_score=min_score,
        )

    # Backward compatibility: static methods for tests that call PrimingEngine._build_dual_queries etc.
    @staticmethod
    def _build_dual_queries(message: str, keywords: list[str]) -> list[str]:
        from core.memory.priming.utils import build_dual_queries

        return build_dual_queries(message, keywords)

    @staticmethod
    def _meets_min_length(token: str) -> bool:
        from core.memory.priming.utils import meets_min_length

        return meets_min_length(token)
