from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Channel C: Related knowledge and important knowledge search."""

import asyncio
import json
import logging
import re
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from core.file_access_policy import load_denied_roots, memory_source_is_allowed
from core.memory.priming.constants import _BUDGET_IMPORTANT_KNOWLEDGE
from core.memory.priming.items import ItemizedMemory, MemoryItem, render_items, select_within_budget
from core.memory.priming.utils import build_queries, build_unified_searcher, normalize_trigger
from core.memory.retrieval.unified_search import UnifiedMemorySearch
from core.memory.search_metadata import format_result_metadata_line
from core.prompt.tokens import estimate_tokens

if TYPE_CHECKING:
    from core.memory.rag.retriever import MemoryRetriever

logger = logging.getLogger("animaworks.priming")


def _single_line(text: str, limit: int = 160) -> str:
    """Collapse prompt cue text to one bounded line."""
    collapsed = " ".join(str(text or "").split())
    return collapsed[:limit]


def _quote_path(path: str) -> str:
    """Return a JSON string literal for read_memory_file path examples."""
    return json.dumps(path, ensure_ascii=False)


def extract_summary(content: str, metadata: dict) -> tuple[str, str]:
    """Extract title and body summary from an [IMPORTANT] search result.

    Returns:
        (title, body_summary) where body_summary is the first meaningful
        line after the H1 heading, truncated to 100 chars. Empty string
        if no body is available.
    """
    title = ""
    body = ""

    fm_summary = metadata.get("summary")
    if fm_summary:
        return (str(fm_summary).strip(), "")

    match = re.search(r"^#{1,6}\s+(.+)$", content, re.MULTILINE)
    if match:
        title = match.group(1).strip()
        after_h1 = content[match.end() :].lstrip("\n")
        for line in after_h1.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                body = stripped[:100]
                break
    else:
        source = metadata.get("source_file", "")
        if source:
            title = Path(source).stem.replace("-", " ").replace("_", " ")

    return (title, body)


def _usable_summary_body(body: str) -> str:
    """Reject structural Markdown lines that do not summarize a document."""
    stripped = body.strip()
    if stripped.startswith("|") or re.fullmatch(r"[-|:\s]+", stripped):
        return ""
    if re.fullmatch(r"#+", stripped):
        return ""
    return stripped


def _timestamp_rank(value: str) -> float:
    """Convert an ISO timestamp into a sortable numeric rank."""
    if not value:
        return 0.0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _path_from_doc_id(doc_id: str, memory_type: str = "knowledge") -> str:
    """Best-effort conversion from retriever doc_id to read_memory_file path."""
    if not doc_id:
        return ""
    doc_path = str(doc_id).split("#", 1)[0]
    for marker in ("companies/", "common_knowledge/", "knowledge/", "episodes/"):
        if marker in doc_path:
            return marker + doc_path.split(marker, 1)[1]
    marker = f"{memory_type}/"
    if marker in doc_path:
        return marker + doc_path.split(marker, 1)[1]
    if doc_path.endswith(".md"):
        return f"{memory_type}/{Path(doc_path).name}"
    return ""


def to_read_memory_path(metadata: dict, anima_name: str, doc_id: str = "") -> str:
    """Convert chunk metadata to read_memory_file path."""
    source = metadata.get("source_file", "") or _path_from_doc_id(doc_id)
    if not source:
        return ""
    if metadata.get("anima") == "shared":
        # companies/ paths are directly readable via read_memory_file; prefixing
        # common_knowledge/ would make them unresolvable
        if source.startswith(("common_knowledge/", "companies/")):
            return source
        return f"common_knowledge/{source}"
    return source


def format_pointer_result(
    *,
    index: int,
    label: str,
    score: float,
    content: str,
    metadata: dict,
    path: str,
) -> str:
    """Format a retrieval result as a pointer cue instead of raw payload."""
    title, body = extract_summary(content, metadata)
    summary = title or Path(path).stem.replace("-", " ").replace("_", " ")
    if body:
        summary = f"{summary} - {body}" if summary else body
    summary = _single_line(summary)
    metadata_line = format_result_metadata_line({**metadata, "source_file": metadata.get("source_file") or path})
    metadata_block = f"{metadata_line}\n" if metadata_line else ""
    return (
        f"--- Result {index} [{label}] (score: {score:.3f}) ---\n"
        f"{metadata_block}"
        f"{summary}\n"
        f"  -> read_memory_file(path={_quote_path(path)})\n"
    )


def _build_unified_searcher(
    anima_dir: Path,
    get_retriever: Callable[[], MemoryRetriever | None],
) -> UnifiedMemorySearch:
    """Build UnifiedMemorySearch, preserving injected retriever state for tests/runtime caches.

    Thin wrapper over the shared helper that binds this module's ``UnifiedMemorySearch``
    reference so test-time patches on ``channel_c.UnifiedMemorySearch`` keep working.
    """
    return build_unified_searcher(anima_dir, get_retriever, UnifiedMemorySearch)


async def channel_c0_important_knowledge(
    anima_dir: Path,
    knowledge_dir: Path,
    get_retriever: Callable[[], MemoryRetriever | None],
) -> str:
    """Channel C0: Always-prime [IMPORTANT] chunks (summary pointers only)."""
    if not knowledge_dir.is_dir():
        return ""
    try:
        denied_roots = load_denied_roots(anima_dir)
        retriever = await asyncio.to_thread(get_retriever)
        if retriever is None:
            return ""
        anima_name = anima_dir.name
        results = await asyncio.to_thread(
            retriever.get_important_chunks,
            anima_name,
            include_shared=True,
        )
        if not results:
            return ""
        newest_by_path: dict[str, MemoryItem] = {}
        for r in results:
            meta = r.document.metadata
            doc_id = str(getattr(r.document, "id", "") or getattr(r, "doc_id", "") or "")
            rel_path = to_read_memory_path(meta, anima_name, doc_id)
            if not rel_path or not memory_source_is_allowed(anima_dir, rel_path, denied_roots):
                continue
            content = r.document.content
            title, body = extract_summary(content, meta)
            body = _usable_summary_body(body)
            if body:
                metadata_line = format_result_metadata_line(
                    {**meta, "source_file": meta.get("source_file") or rel_path}
                )
                heading = f"📌 {_single_line(title)} — {_single_line(body, 100)}"
                if metadata_line:
                    line = f"{heading}\n  {metadata_line}\n  → read_memory_file(path={_quote_path(rel_path)})"
                else:
                    line = f"{heading}\n  → read_memory_file(path={_quote_path(rel_path)})"
            else:
                metadata_line = format_result_metadata_line(
                    {**meta, "source_file": meta.get("source_file") or rel_path}
                )
                if metadata_line:
                    line = f"📌 {_single_line(title)}\n  {metadata_line}\n  → read_memory_file(path={_quote_path(rel_path)})"
                else:
                    line = f"📌 {_single_line(title)} → read_memory_file(path={_quote_path(rel_path)})"
            updated = str(meta.get("updated_at") or meta.get("updated") or meta.get("created_at") or "")
            item = MemoryItem(
                source="important_knowledge",
                key=rel_path,
                text=line,
                ref=rel_path,
                updated=updated,
                rank=_timestamp_rank(updated),
            )
            previous = newest_by_path.get(rel_path)
            if previous is None or item.updated > previous.updated:
                newest_by_path[rel_path] = item

        header = "### [IMPORTANT] Knowledge (summary pointers)"
        available = _BUDGET_IMPORTANT_KNOWLEDGE - estimate_tokens(header)
        if available <= 0:
            return ""
        # Freshness, not line length, determines which important pointers survive.
        selected = select_within_budget(newest_by_path.values(), available)
        while selected and estimate_tokens(render_items(selected, header)) > _BUDGET_IMPORTANT_KNOWLEDGE:
            selected.pop()
        if not selected:
            return ""
        return ItemizedMemory(render_items(selected, header), selected)
    except Exception as e:
        logger.debug("Channel C0: get_important_chunks failed: %s", e)
        return ""


async def channel_c_related_knowledge(
    anima_dir: Path,
    knowledge_dir: Path,
    get_retriever: Callable[[], MemoryRetriever | None],
    keywords: list[str],
    message: str = "",
    recent_human_messages: list[str] | None = None,
    trigger: str = "chat",
) -> tuple[str, str]:
    """Channel C: Related knowledge search through unified Legacy retrieval.

    Searches both personal knowledge and shared common_knowledge,
    merging results by score.

    ``trigger`` selects the retrieval policy (rerank/pool/scopes); it is
    normalized to a ``TRIGGER_POLICIES`` key before use.

    Returns a ``(medium_text, untrusted_text)`` tuple where results
    are split by their provenance-derived trust level.
    """
    if not knowledge_dir.is_dir():
        logger.debug("Channel C: No knowledge dir")
        return ("", "")

    try:
        denied_roots = load_denied_roots(anima_dir)
        queries = build_queries(message, keywords, recent_human_messages)
        if not queries:
            logger.debug("Channel C: No keywords and no message")
            return ("", "")
        anima_name = anima_dir.name

        _min_score: float | None = None
        try:
            from core.config.models import load_config as _load_cfg

            _min_score = _load_cfg().rag.min_retrieval_score
        except Exception:
            logger.debug("Failed to load rag.min_retrieval_score from config, using default")

        searcher = await asyncio.to_thread(_build_unified_searcher, anima_dir, get_retriever)
        results = await asyncio.to_thread(
            searcher.search_many,
            queries,
            scope="common_knowledge",
            limit=5,
            trigger=normalize_trigger(trigger),
            min_score=float(_min_score) if _min_score is not None else 0.0,
        )
        if bool(searcher.last_search_meta.get("abstain", False)):
            logger.debug("Channel C: unified search abstained")
            return ("", "")

        if results:
            from core.execution._sanitize import ORIGIN_UNKNOWN, resolve_trust

            medium_parts: list[str] = []
            untrusted_parts: list[str] = []
            display_index = 1

            for result in results:
                metadata = _metadata_from_unified_result(result)
                chunk_origin = metadata.get("origin", "")
                chunk_trust = resolve_trust(chunk_origin or ORIGIN_UNKNOWN)
                source_label = metadata.get("anima", anima_name)
                label = "shared" if source_label == "shared" else "personal"
                rel_path = to_read_memory_path(metadata, anima_name, str(result.get("doc_id", "")))
                if not rel_path:
                    logger.debug("Channel C: skipping result without readable path: %s", result.get("doc_id", ""))
                    continue
                if not memory_source_is_allowed(anima_dir, rel_path, denied_roots):
                    logger.debug("Channel C: skipping result from denied or ambiguous source: %s", rel_path)
                    continue
                line = format_pointer_result(
                    index=display_index,
                    label=label,
                    score=float(result.get("score", 0.0) or 0.0),
                    content=str(result.get("content", "") or ""),
                    metadata=metadata,
                    path=rel_path,
                )
                display_index += 1
                if chunk_trust == "untrusted":
                    untrusted_parts.append(line)
                else:
                    medium_parts.append(line)

            medium_output = "\n".join(medium_parts)
            untrusted_output = "\n".join(untrusted_parts)

            logger.debug(
                "Channel C: Vector search returned %d results (medium=%d, untrusted=%d)",
                len(results),
                len(medium_parts),
                len(untrusted_parts),
            )
            return (medium_output, untrusted_output)
        else:
            logger.debug("Channel C: Vector search found no results")
            return ("", "")

    except Exception as e:
        logger.warning("Channel C: Vector search failed: %s", e)
        return ("", "")


def _metadata_from_unified_result(result: dict) -> dict:
    metadata = {
        key: value
        for key, value in result.items()
        if key not in ("content", "score") and isinstance(value, (str, int, float, bool, list))
    }
    if "source_file" not in metadata and result.get("source"):
        metadata["source_file"] = result["source"]
    return metadata
