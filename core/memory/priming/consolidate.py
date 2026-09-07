from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Cross-channel consolidation for itemized priming memories."""

import logging
import re
from dataclasses import replace
from difflib import SequenceMatcher

from core.i18n import t
from core.memory.priming.items import MemoryItem, render_items
from core.memory.priming.result import PrimingResult

logger = logging.getLogger("animaworks.priming")

_TIME_RE = re.compile(r"\[\d{2}:\d{2}\]")
_WHITESPACE_RE = re.compile(r"\s+")
_HEADERS = {
    "important_knowledge": "### [IMPORTANT] Knowledge (summary pointers)",
    "recent_activity": "",
    "episodes": "",
    "pending_tasks": "",
    "recent_outbound": "",
    "pending_human_notifications": "## Pending Human Notifications (last 24h)",
}
_DIRECT_FIELDS = frozenset(
    {
        "recent_activity",
        "episodes",
        "pending_tasks",
        "recent_outbound",
        "pending_human_notifications",
    }
)


def _normalized_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", _TIME_RE.sub("", text)).strip()


def _same_long_text(left: str, right: str) -> bool:
    """Return whether normalized texts share an identical 60-char body."""
    if len(left) < 60 or len(right) < 60:
        return False
    return SequenceMatcher(None, left, right, autojunk=False).find_longest_match().size >= 60


def consolidate_items(result: PrimingResult) -> PrimingResult:
    """Drop duplicate/obsolete items and rebuild their channel strings."""
    flattened = [item for channel_items in result.items.values() for item in channel_items]
    normalized_texts = [_normalized_text(item.text) for item in flattened]
    latest_by_key: dict[str, int] = {}
    latest_important_by_ref: dict[str, int] = {}
    for index, item in enumerate(flattened):
        effective_key = item.key or normalized_texts[index]
        current_index = latest_by_key.get(effective_key)
        if current_index is None or item.updated > flattened[current_index].updated:
            latest_by_key[effective_key] = index
        if item.source == "important_knowledge" and item.ref:
            current_ref_index = latest_important_by_ref.get(item.ref)
            if current_ref_index is None or item.updated > flattened[current_ref_index].updated:
                latest_important_by_ref[item.ref] = index

    kept: list[MemoryItem] = []
    normalized_kept: list[str] = []
    dropped: list[MemoryItem] = []

    for index, item in enumerate(flattened):
        effective_key = item.key or normalized_texts[index]
        if latest_by_key.get(effective_key) != index:
            dropped.append(item)
            continue
        if item.source == "important_knowledge" and item.ref and latest_important_by_ref.get(item.ref) != index:
            dropped.append(item)
            continue
        normalized = normalized_texts[index]
        if any(_same_long_text(normalized, previous) for previous in normalized_kept):
            dropped.append(item)
            continue
        kept.append(item)
        normalized_kept.append(normalized)

    consolidated: dict[str, tuple[MemoryItem, ...]] = {}
    for source in result.items:
        consolidated[source] = tuple(item for item in kept if item.source == source)

    updates: dict[str, object] = {"items": consolidated}
    for source in _DIRECT_FIELDS:
        if source in result.items:
            header = t("priming.outbound_header") if source == "recent_outbound" else _HEADERS[source]
            updates[source] = render_items(consolidated.get(source, ()), header)

    if "important_knowledge" in result.items:
        important = render_items(
            consolidated.get("important_knowledge", ()),
            _HEADERS["important_knowledge"],
        )
        related = result.related_knowledge
        updates["related_knowledge"] = f"{important}\n\n{related}" if important and related else important or related

    for item in dropped:
        logger.debug(
            "Priming consolidation dropped item: source=%s key=%s ref=%s",
            item.source,
            item.key,
            item.ref,
        )
    logger.info("Priming consolidation: kept=%d dropped=%d", len(kept), len(dropped))
    return replace(result, **updates)
