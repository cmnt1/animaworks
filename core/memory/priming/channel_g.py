from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Channel G: Relevant atomic facts from the unified memory search."""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from core.config.file_access_policy import load_denied_roots, memory_source_is_allowed
from core.i18n import t
from core.memory.priming.utils import (
    build_unified_searcher,
    get_min_retrieval_score,
    normalize_trigger,
    truncate_head,
)
from core.memory.retrieval.unified_search import UnifiedMemorySearch

logger = logging.getLogger("animaworks.priming")

_MAX_FACT_CHARS = 240


def _source_from_result(result: dict[str, Any]) -> str:
    """Return the most specific source identifier available on a search row."""
    source = result.get("source_file") or result.get("source_path") or result.get("source") or ""
    if source:
        return str(source)
    doc_id = str(result.get("doc_id", "") or "")
    return doc_id.split("#", 1)[0]


async def collect_recent_facts(
    anima_dir: Path,
    get_retriever: Callable[[], Any | None],
    queries: list[str],
    *,
    budget_tokens: int = 500,
    trigger: str = "chat",
    min_score: float | None = None,
) -> str:
    """Search atomic facts and return bounded, readable priming context.

    Search results use the same unified retriever and score floor as Channel C.
    Sources hidden by the Anima's denied-root policy are never returned.
    """
    effective_queries = [str(query).strip() for query in (queries or []) if str(query).strip()]
    if not effective_queries or budget_tokens <= 0:
        return ""

    try:
        denied_roots = load_denied_roots(anima_dir)
        resolved_min_score = get_min_retrieval_score() if min_score is None else float(min_score)
        searcher = await asyncio.to_thread(
            build_unified_searcher,
            anima_dir,
            get_retriever,
            UnifiedMemorySearch,
        )
        results = await asyncio.to_thread(
            searcher.search_many,
            effective_queries,
            scope="facts",
            limit=10,
            trigger=normalize_trigger(trigger),
            min_score=resolved_min_score,
        )
        if bool(searcher.last_search_meta.get("abstain", False)):
            logger.debug("Channel G: unified fact search abstained")
            return ""

        fact_lines: list[str] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            source = _source_from_result(result)
            if not memory_source_is_allowed(anima_dir, source, denied_roots):
                logger.debug("Channel G: skipping fact from denied source: %s", source)
                continue

            fact = str(result.get("content", "") or "").strip()
            if not fact:
                continue
            if len(fact) > _MAX_FACT_CHARS:
                # Facts merged as COMPLEMENT can grow without bound; one must
                # not take the whole budget.
                fact = fact[: _MAX_FACT_CHARS - 1] + "…"
            relation = " ".join(
                str(result.get(key, "") or "")
                for key in ("source_entity", "edge_type", "target_entity")
                if result.get(key)
            )
            prefix = f"[{relation}] " if relation else ""
            fact_lines.append(f"- {prefix}{fact}")

        if not fact_lines:
            return ""

        text = "\n".join((t("priming.recent_facts_header"), *fact_lines))
        # Rows arrive best match first; keep the header and the top facts.
        return truncate_head(text, budget_tokens)
    except Exception:
        logger.debug("Channel G: recent fact search failed", exc_info=True)
        return ""
