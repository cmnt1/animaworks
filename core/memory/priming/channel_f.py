from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Channel F: Episode memory search (vector search)."""

import asyncio
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.config.file_access_policy import load_denied_roots, memory_source_is_allowed
from core.memory.priming.items import ItemizedMemory, MemoryItem, render_items
from core.memory.priming.utils import build_queries, build_unified_searcher, normalize_trigger
from core.memory.rag.indexer import MemoryIndexer
from core.memory.retrieval.unified_search import UnifiedMemorySearch

logger = logging.getLogger(__name__)


def _single_line(text: str, limit: int = 160) -> str:
    """Collapse prompt cue text to one bounded line."""
    collapsed = " ".join(str(text or "").split())
    return collapsed[:limit]


def to_episode_memory_path(source: str) -> str:
    """Normalize retriever/backend source to a read_memory_file episode path."""
    if not source:
        return ""
    source_path = str(source).split("#", 1)[0]
    marker = "episodes/"
    if marker in source_path:
        return marker + source_path.split(marker, 1)[1]
    if source_path.endswith(".md"):
        return f"episodes/{Path(source_path).name}"
    return ""


def extract_episode_summary(content: str, source: str) -> str:
    """Return a short cue for an episode without injecting the full episode body."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return _single_line(stripped.lstrip("#").strip(), 60)
    path = to_episode_memory_path(source)
    if path:
        return _single_line(Path(path).stem.replace("-", " ").replace("_", " "), 60)
    return "Related episode memory"


def _episode_updated(metadata: dict, path: str) -> str:
    """Use explicit metadata or the episode filename as a freshness key."""
    updated = str(metadata.get("updated_at") or metadata.get("updated") or metadata.get("created_at") or "")
    if updated:
        return updated
    match = re.search(r"\d{4}-\d{2}-\d{2}", path)
    return match.group(0) if match else ""


def format_episode_pointer(
    *,
    index: int,
    score: float,
    source: str,
    content: str,
    path: str,
    show_body: bool = False,
    low_confidence: bool = False,
) -> str:
    """Format an episode result as a pointer cue instead of raw payload.

    ``show_body`` (top 1-2 results) also emits up to 600 chars of the
    episode body as recent conversation, followed by the pointer line.
    ``low_confidence`` suffixes the pointer with ``[low-confidence]``.
    """
    summary = extract_episode_summary(content, source)
    marker = " [low-confidence]" if low_confidence else ""
    pointer = f"📌 [{score:.2f}] {path} — {summary}{marker}"
    if not show_body:
        return pointer
    body = _single_line(content, 600)
    if body and body != summary:
        return f"{body}\n{pointer}"
    return pointer


def episode_date(path: str) -> str:
    """Return the YYYY-MM-DD date embedded in an episode path (or "")."""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path)
    return match.group(1) if match else ""


def exclude_episodes_for_dates(items: list, dates: set[str]) -> list:
    """Drop episode items whose date also appears in ``dates`` (from Channel B)."""
    if not dates:
        return items
    return [item for item in items if episode_date(str(item.ref)) not in dates]


async def channel_f_episodes(
    anima_dir: Path,
    episodes_dir: Path,
    get_retriever: Callable[..., Any],
    keywords: list[str],
    *,
    message: str = "",
    recent_human_messages: list[str] | None = None,
    trigger: str = "chat",
) -> str:
    """Channel F: Episode memory search (vector search).

    Searches episodes/ via dense vector retrieval to surface
    semantically relevant past experiences.  Complements Channel B
    (recent activity timeline) by looking further back in time and
    ranking by semantic similarity rather than recency alone.

    ``trigger`` selects the retrieval policy (rerank/pool/scopes); it is
    normalized to a ``TRIGGER_POLICIES`` key before use.
    """
    try:
        denied_roots = load_denied_roots(anima_dir)
        queries = build_queries(message, keywords, recent_human_messages)[:1]
        if not queries:
            return ""

        _min_score: float | None = None
        try:
            from core.config.models import load_config as _load_cfg

            _min_score = _load_cfg().rag.min_retrieval_score
        except Exception:
            logger.debug("Failed to load rag.min_retrieval_score from config, using default")

        if not episodes_dir.is_dir():
            return ""

        searcher = await asyncio.to_thread(build_unified_searcher, anima_dir, get_retriever, UnifiedMemorySearch)
        results = await asyncio.to_thread(
            searcher.search_many,
            queries,
            scope="episodes",
            limit=5,
            trigger=normalize_trigger(trigger),
            min_score=float(_min_score) if _min_score is not None else 0.0,
            pipeline_settings={"rerank_candidate_pool": 10},
            skip_bm25_validation=True,
        )
        if bool(searcher.last_search_meta.get("abstain", False)):
            logger.debug("Channel F: unified search abstained")
            return ""

        low_confidence = bool(searcher.last_search_meta.get("low_confidence", False))

        if not results:
            return ""

        results = sorted(
            results,
            key=lambda result: float(result.get("score", 0.0) or 0.0),
            reverse=True,
        )
        parts = []
        items = []
        for position, result in enumerate(results):
            source = str(result.get("source_file", "") or result.get("doc_id", "") or "")
            path = to_episode_memory_path(source)
            if not path:
                logger.debug("Channel F: skipping episode without readable path: %s", result.get("doc_id", ""))
                continue
            if MemoryIndexer.is_ragignored(anima_dir / path):
                logger.debug("Channel F: skipping excluded episode: %s", path)
                continue
            if not memory_source_is_allowed(anima_dir, path, denied_roots):
                logger.debug("Channel F: skipping episode from denied source: %s", path)
                continue
            text = format_episode_pointer(
                index=position + 1,
                score=float(result.get("score", 0.0) or 0.0),
                source=source,
                content=str(result.get("content", "") or ""),
                path=path,
                show_body=position < 2,
                low_confidence=low_confidence,
            )
            parts.append(text)
            metadata = result if isinstance(result, dict) else {}
            items.append(
                MemoryItem(
                    source="episodes",
                    key=path
                    or f"{_episode_updated(metadata, path)}|{extract_episode_summary(str(result.get('content', '') or ''), source)}",
                    text=text,
                    ref=path,
                    updated=_episode_updated(metadata, path),
                    rank=float(result.get("score", 0.0) or 0.0),
                )
            )

        logger.debug(
            "Channel F: Episode search returned %d results",
            len(results),
        )
        return ItemizedMemory(render_items(items, ""), items) if items else ""

    except Exception as e:
        logger.warning("Channel F: Episode search failed: %s", e)
        return ""
