from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""PrimingEngine - orchestrator for priming channels A, B, C, E, F, and G."""

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

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
from core.memory.priming.constants import _DEFAULT_MAX_PRIMING_TOKENS
from core.memory.priming.items import ItemizedMemory, MemoryItem, render_items, select_within_budget
from core.memory.priming.result import PrimingResult
from core.memory.priming.utils import RetrieverCache, build_queries, extract_keywords, truncate_head, truncate_tail
from core.text.tokens import estimate_tokens

logger = logging.getLogger("animaworks.priming")

_BUDGET_SENDER_PROFILE = 400
_BUDGET_PENDING_TASKS = 500
_BUDGET_RECENT_OUTBOUND = 250
_COMPACT_BACKGROUND_TRIGGERS = frozenset({"heartbeat", "inbox", "cron"})


class PrimingEngine:
    """Automatic memory priming engine.

    Executes parallel memory retrieval:
      A. Sender profile (direct file read)
      B. Recent activity (unified activity log, replaces old episodes + channels)
      C. Related knowledge (dense vector search)
      G. Recent facts (dense vector search over atomic facts)
      E. Pending tasks (persistent task queue summary)
      F. Episodes (dense vector search over episode memory)
    """

    def __init__(
        self,
        anima_dir: Path,
        shared_dir: Path | None = None,
    ) -> None:
        self.anima_dir = anima_dir
        self.shared_dir = shared_dir
        self.episodes_dir = anima_dir / "episodes"
        self.knowledge_dir = anima_dir / "knowledge"
        self._retriever_cache = RetrieverCache()
        self._retriever: Any | None = None
        self._config_loaded = False
        self._channel_timeout_seconds = 60.0

    def _get_or_create_retriever(self):
        """Get or create a retriever instance from the RetrieverCache."""
        if self._retriever is not None:
            return self._retriever
        return self._retriever_cache.get_or_create(self.anima_dir, self.knowledge_dir)

    def _get_retriever(self):
        """Delegate to _get_or_create_retriever (tests may patch either)."""
        return self._get_or_create_retriever()

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

    async def prime_memories(
        self,
        message: str,
        sender_name: str = "human",
        channel: str = "chat",
        intent: str = "",
        recent_human_messages: list[str] | None = None,
        max_tokens: int | None = None,
        include_related: bool = True,
    ) -> PrimingResult:
        """Prime memories based on incoming message.

        The compact path bounds itemized channel output by ``max_tokens``;
        pending human notifications are retained separately.
        """
        logger.debug(
            "Priming memories: sender=%s, message_len=%d, channel=%s",
            sender_name,
            len(message),
            channel,
        )

        token_budget = _DEFAULT_MAX_PRIMING_TOKENS if max_tokens is None else max_tokens
        return await self._prime_compact(
            message, sender_name, channel, intent, token_budget, recent_human_messages, include_related
        )

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

        Resident pointers are explicit opt-ins. Background triggers may also
        receive bounded recent activity plus configured knowledge and episode
        recall; broader graph expansion is not part of automatic priming.
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
        background_settings = self._compact_background_recall_settings(channel)
        has_query = bool(message.strip())
        should_search_related = (
            include_related
            and has_query
            and (
                related
                or (
                    background_settings is not None
                    and (
                        background_settings.related_knowledge_max_items > 0
                        and background_settings.related_knowledge_max_tokens > 0
                    )
                )
            )
        )
        if should_search_related:
            keywords = self._extract_keywords(message)
            calls.append(
                (
                    "C",
                    self._channel_c_related_knowledge(
                        keywords,
                        message=message,
                        recent_human_messages=recent_human_messages,
                        trigger=channel,
                    ),
                )
            )
            recent_facts_enabled, recent_facts_max_tokens = self._recent_facts_settings()
            if recent_facts_enabled and recent_facts_max_tokens > 0:
                calls.append(
                    (
                        "G",
                        self._channel_g_recent_facts(
                            build_queries(message, keywords, recent_human_messages),
                            budget_tokens=recent_facts_max_tokens,
                            trigger=channel,
                        ),
                    )
                )
        if (
            background_settings is not None
            and background_settings.recent_activity_max_items > 0
            and background_settings.recent_activity_max_tokens > 0
        ):
            calls.append(
                (
                    "B",
                    self._channel_b_recent_activity(
                        sender_name,
                        self._extract_keywords(message),
                        channel=channel,
                    ),
                )
            )
        if (
            include_related
            and has_query
            and background_settings is not None
            and background_settings.episodes_max_items > 0
            and background_settings.episodes_max_tokens > 0
        ):
            calls.append(
                (
                    "F",
                    self._channel_f_episodes(
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

        def bounded_items(
            value: str,
            budget: int,
            max_items: int | None = None,
            *,
            newest_first: bool = False,
        ) -> tuple[str, int]:
            if isinstance(value, ItemizedMemory):
                if newest_first:
                    items = sorted(value.items, key=lambda item: (item.updated, item.rank), reverse=True)
                else:
                    items = sorted(value.items, key=lambda item: (item.rank, item.updated), reverse=True)
                if max_items is not None:
                    items = items[:max_items]
                if newest_first:
                    selected: list[MemoryItem] = []
                    for item in items:
                        candidate = render_items((*selected, item), "")
                        if estimate_tokens(candidate) <= budget:
                            selected.append(item)
                else:
                    selected = select_within_budget(items, budget)
                return render_items(selected, ""), len(selected)
            text = truncate_head(value, budget)
            return text, int(bool(text.strip()))

        def bounded(value: str, budget: int) -> str:
            return bounded_items(value, budget)[0]

        result = PrimingResult(
            sender_profile=truncate_head(content("A"), min(_BUDGET_SENDER_PROFILE, token_budget // 4)),
            pending_tasks=bounded(content("E"), min(_BUDGET_PENDING_TASKS, token_budget // 3)),
            resident_knowledge=content("C0"),
            recent_outbound=truncate_tail(content("outbound"), _BUDGET_RECENT_OUTBOUND),
            # Notification delivery is a separate contract, never dropped to
            # meet a recall optimization budget.
            pending_human_notifications=content("pending_human_notifications"),
        )
        activity_value = results.get("B")
        if isinstance(activity_value, str) and background_settings is not None:
            remaining = max(0, token_budget - result.estimated_tokens())
            result.recent_activity = bounded_items(
                activity_value,
                min(remaining, background_settings.recent_activity_max_tokens),
                background_settings.recent_activity_max_items,
                newest_first=True,
            )[0]

        related_value = results.get("C")
        if isinstance(related_value, tuple):
            remaining = max(0, token_budget - result.estimated_tokens())
            is_background_recall = background_settings is not None
            related_max_items = background_settings.related_knowledge_max_items if is_background_recall else None
            related_max_tokens = background_settings.related_knowledge_max_tokens if is_background_recall else remaining
            related_budget = min(remaining, related_max_tokens)
            trusted, untrusted = related_value
            trusted_text, trusted_count = bounded_items(trusted, related_budget, related_max_items)
            result.related_knowledge += ("\n" if result.related_knowledge else "") + trusted_text
            remaining = max(0, token_budget - result.estimated_tokens())
            if is_background_recall:
                related_budget = min(
                    max(0, related_max_tokens - estimate_tokens(trusted_text)),
                    remaining,
                )
                remaining_items = max(0, related_max_items - trusted_count)
            else:
                related_budget = remaining
                remaining_items = None
            untrusted_text, _ = bounded_items(untrusted, related_budget, remaining_items)
            result.related_knowledge_untrusted = untrusted_text

        episodes_value = results.get("F")
        if isinstance(episodes_value, str) and background_settings is not None:
            remaining = max(0, token_budget - result.estimated_tokens())
            result.episodes = bounded_items(
                episodes_value,
                min(remaining, background_settings.episodes_max_tokens),
                background_settings.episodes_max_items,
            )[0]

        # Channel G owns a dedicated budget outside the shared compact recall
        # budget; assigning it last prevents it from displacing Channel C or
        # changing the established trimming order for other channels.
        result.recent_facts = content("G")
        logger.info(
            "Priming compact: channels=%s related_searches=%d activity_chars=%d elapsed=%.3fs tokens=%d",
            ",".join(results),
            int("C" in results),
            len(result.recent_activity),
            time.perf_counter() - started,
            result.estimated_tokens(),
        )
        return result

    def _compact_background_recall_settings(self, channel: str):
        """Return configured compact recall limits for a background trigger."""
        if channel not in _COMPACT_BACKGROUND_TRIGGERS:
            return None

        from core.config.schemas import PrimingConfig

        defaults = PrimingConfig()
        try:
            from core.config.models import load_config

            priming = load_config().priming
        except Exception:
            logger.debug("Failed to load compact background recall config; using defaults", exc_info=True)
            priming = defaults

        if not bool(getattr(priming, "compact_background_recall_enabled", True)):
            return None
        return getattr(priming, "compact_background_recall", defaults.compact_background_recall)

    def _recent_facts_settings(self) -> tuple[bool, int]:
        """Return whether Channel G is enabled and its dedicated token budget."""
        from core.config.schemas import PrimingConfig

        defaults = PrimingConfig()
        try:
            from core.config.models import load_config

            priming = load_config().priming
        except Exception:
            logger.debug("Failed to load recent facts priming config; using defaults", exc_info=True)
            priming = defaults

        enabled = bool(getattr(priming, "recent_facts_enabled", defaults.recent_facts_enabled))
        raw_budget = getattr(priming, "recent_facts_max_tokens", defaults.recent_facts_max_tokens)
        try:
            budget = max(0, int(raw_budget))
        except (TypeError, ValueError):
            budget = defaults.recent_facts_max_tokens
        return enabled, budget

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
            trigger=trigger,
        )

    async def _channel_g_recent_facts(
        self,
        queries: list[str],
        *,
        budget_tokens: int = 500,
        trigger: str = "chat",
    ) -> str:
        return await _channel_g.collect_recent_facts(
            self.anima_dir,
            self._get_retriever,
            queries,
            budget_tokens=budget_tokens,
            trigger=trigger,
        )

    async def _collect_pending_human_notifications(self, *, channel: str = "") -> str:
        return await _outbound.collect_pending_human_notifications(self.anima_dir, channel=channel)

    def _extract_keywords(self, message: str) -> list[str]:
        """Backward compat: delegate to utils.extract_keywords."""
        return extract_keywords(message, self.knowledge_dir)
