from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Channel F: Episode memory search (vector search)."""

import logging
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from core.memory.priming.utils import build_queries, search_and_merge
from core.time_utils import now_local

logger = logging.getLogger(__name__)


async def channel_f_episodes(
    anima_dir: Path,
    episodes_dir: Path,
    get_retriever: Callable[..., Any],
    keywords: list[str],
    *,
    message: str = "",
    recent_human_messages: list[str] | None = None,
    get_memory_backend: Callable[[], Any] | None = None,
) -> str:
    """Channel F: Episode memory search (vector search).

    Searches episodes/ via dense vector retrieval to surface
    semantically relevant past experiences.  Complements Channel B
    (recent activity timeline) by looking further back in time and
    ranking by semantic similarity rather than recency alone.

    When the active memory backend is Neo4j, uses ``retrieve()`` with a
    7-day ``time_start`` window so recent episodes are preferred.
    """
    try:
        queries = build_queries(message, keywords, recent_human_messages)
        if not queries:
            return ""
        anima_name = anima_dir.name

        _min_score: float | None = None
        try:
            from core.config.models import load_config as _load_cfg

            _min_score = _load_cfg().rag.min_retrieval_score
        except Exception:
            logger.debug("Failed to load rag.min_retrieval_score from config, using default")

        if get_memory_backend is not None:
            backend = get_memory_backend()
            if backend is not None:
                from core.memory.backend.neo4j_graph import Neo4jGraphBackend

                if isinstance(backend, Neo4jGraphBackend):
                    time_start = (now_local() - timedelta(days=7)).isoformat()
                    best: dict[str, Any] = {}
                    min_score_val = float(_min_score) if _min_score is not None else 0.0
                    for query in queries:
                        merged_batch = await backend.retrieve(
                            query,
                            scope="episode",
                            limit=5,
                            min_score=min_score_val,
                            time_start=time_start,
                        )
                        for m in merged_batch:
                            existing = best.get(m.source)
                            if existing is None or m.score > existing.score:
                                best[m.source] = m
                    merged = sorted(best.values(), key=lambda m: m.score, reverse=True)[:5]
                    if not merged:
                        return ""
                    try:
                        await backend.record_access(merged)
                    except Exception:
                        logger.debug("Channel F: record_access skipped", exc_info=True)

                    parts: list[str] = []
                    for i, mem in enumerate(merged):
                        meta = mem.metadata if isinstance(mem.metadata, dict) else {}
                        source = meta.get("source_file", mem.source)
                        parts.append(
                            f"--- Episode {i + 1} (score: {mem.score:.3f}, source: {source}) ---\n{mem.content}\n",
                        )

                    logger.debug(
                        "Channel F: Neo4j episode search returned %d results",
                        len(merged),
                    )
                    return "\n".join(parts)

        if not episodes_dir.is_dir():
            return ""

        retriever = get_retriever()
        if retriever is None:
            return ""

        results = search_and_merge(
            retriever,
            queries,
            anima_name,
            memory_type="episodes",
            top_k=5,
            min_score=_min_score,
        )

        if not results:
            return ""

        retriever.record_access(results, anima_name)

        parts = []
        for i, result in enumerate(results):
            source = result.metadata.get("source_file", result.doc_id)
            parts.append(f"--- Episode {i + 1} (score: {result.score:.3f}, source: {source}) ---\n{result.content}\n")

        logger.debug(
            "Channel F: Episode search returned %d results",
            len(results),
        )
        return "\n".join(parts)

    except Exception as e:
        logger.warning("Channel F: Episode search failed: %s", e)
        return ""
