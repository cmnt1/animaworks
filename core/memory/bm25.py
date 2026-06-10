from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""BM25 keyword search over activity_log JSONL files.

Indexes recent activity entries and ranks them against a query using
``rank_bm25.BM25Okapi`` when available, with a token-overlap fallback.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from core.memory._io import atomic_write_text
from core.time_utils import today_local

logger = logging.getLogger("animaworks.memory")

try:
    from rank_bm25 import BM25Okapi

    _HAS_BM25 = True
except ImportError:
    _HAS_BM25 = False

# ── Constants ───────────────────────────────────────────────

_SEARCHABLE_TYPES: frozenset[str] = frozenset(
    {
        "tool_result",
        "message_received",
        "response_sent",
        "message_sent",
        "human_notify",
    }
)

_EXCLUDED_TOOL_PREFIXES: tuple[str, ...] = ("mcp__aw__",)

_EXCLUDED_TOOLS: frozenset[str] = frozenset(
    {
        "ToolSearch",
        "read_memory_file",
        "search_memory",
        "write_memory_file",
        "post_channel",
        "send_message",
        "call_human",
        "update_task",
        "archive_memory_file",
    }
)

_MIN_CONTENT_LENGTH = 100

_STOPWORDS: frozenset[str] = frozenset(
    {
        "the",
        "and",
        "for",
        "are",
        "this",
        "that",
        "with",
        "from",
        "have",
        "has",
        "was",
        "were",
        "will",
        "been",
        "not",
        "but",
        "they",
        "their",
        "what",
        "which",
        "when",
        "where",
        "who",
        "how",
        "can",
        "all",
        "each",
        "its",
        "than",
        "other",
        "into",
        "could",
        "your",
        "about",
        "would",
        "there",
        "these",
        "some",
        "them",
        "then",
        "also",
    }
)

_CJK_RANGES: tuple[tuple[int, int], ...] = (
    (0x4E00, 0x9FFF),
    (0x3040, 0x309F),
    (0x30A0, 0x30FF),
    (0xAC00, 0xD7AF),
    (0x0E00, 0x0E7F),
)

_WORD_RE = re.compile(r"[\w]+", re.UNICODE)
LONGTERM_BM25_INDEX_FILE = "bm25_longterm_index.json"
LONGTERM_BM25_MEMORY_TYPES: tuple[str, ...] = ("knowledge", "episodes", "procedures")


@dataclass(frozen=True)
class LongTermBM25BuildResult:
    """Summary of a long-term BM25 index rebuild."""

    documents: int
    path: Path


# ── Tokenizer ───────────────────────────────────────────────


def _char_in_cjk_ranges(ch: str) -> bool:
    o = ord(ch)
    return any(lo <= o <= hi for lo, hi in _CJK_RANGES)


def _token_is_cjk_class(tok: str) -> bool:
    return bool(tok) and all(_char_in_cjk_ranges(c) for c in tok)


def tokenize(text: str) -> list[str]:
    """Split *text* into filtered lowercase tokens for BM25 indexing."""
    out: list[str] = []
    for m in _WORD_RE.finditer(text):
        raw = m.group(0)
        t = raw.lower()
        if t in _STOPWORDS:
            continue
        if _token_is_cjk_class(t) or len(t) >= 3:
            out.append(t)
    return out


# ── Activity log loading & filtering ────────────────────────


def _entry_tool_name(entry: dict[str, Any]) -> str:
    tool = entry.get("tool") or ""
    meta = entry.get("meta")
    if isinstance(meta, dict):
        tool = tool or meta.get("tool_name") or ""
    return str(tool) if tool else ""


def _should_index_entry(entry: dict[str, Any]) -> bool:
    etype = entry.get("type")
    if etype not in _SEARCHABLE_TYPES:
        return False
    if etype == "tool_result":
        tool = _entry_tool_name(entry)
        if tool in _EXCLUDED_TOOLS:
            return False
        if any(tool.startswith(p) for p in _EXCLUDED_TOOL_PREFIXES):
            return False
        content = entry.get("content") or ""
        if len(content) < _MIN_CONTENT_LENGTH:
            return False
    return True


def _activity_log_dates(days: int) -> list[date]:
    today = today_local()
    return [today - timedelta(days=i) for i in range(days)]


def _load_activity_entries(anima_dir: Path, days: int) -> list[tuple[str, dict[str, Any]]]:
    base = anima_dir / "activity_log"
    rows: list[tuple[str, dict[str, Any]]] = []
    for d in _activity_log_dates(days):
        date_str = d.isoformat()
        path = base / f"{date_str}.jsonl"
        if not path.is_file():
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    rows.append((date_str, obj))
    return rows


def _fallback_scores(corpus_tokens: list[list[str]], query_tokens: list[str]) -> list[float]:
    if not query_tokens:
        return [0.0] * len(corpus_tokens)
    qset = set(query_tokens)
    scores: list[float] = []
    for doc_tokens in corpus_tokens:
        if not doc_tokens:
            scores.append(0.0)
            continue
        doc_set = set(doc_tokens)
        matched = len(qset & doc_set)
        scores.append(matched / max(1, len(doc_tokens)))
    return scores


def _bm25_scores(corpus_tokens: list[list[str]], query_tokens: list[str]) -> list[float]:
    if _HAS_BM25:
        bm25 = BM25Okapi(corpus_tokens)
        raw = bm25.get_scores(query_tokens)
        return [float(x) for x in raw]
    return _fallback_scores(corpus_tokens, query_tokens)


# ── Long-term memory BM25 index ────────────────────────────


def longterm_bm25_index_path(anima_dir: Path) -> Path:
    """Return the persisted long-term BM25 index path for one anima."""
    return anima_dir / "state" / LONGTERM_BM25_INDEX_FILE


def rebuild_longterm_bm25_index(
    anima_dir: Path,
    *,
    memory_types: tuple[str, ...] = LONGTERM_BM25_MEMORY_TYPES,
) -> LongTermBM25BuildResult:
    """Persist a tokenized BM25 corpus for knowledge/episodes/procedures."""
    docs: list[dict[str, Any]] = []
    for memory_type in memory_types:
        base_dir = anima_dir / memory_type
        if not base_dir.is_dir():
            continue
        for path in sorted(base_dir.rglob("*.md")):
            docs.extend(_bm25_docs_for_file(anima_dir, path, memory_type))

    payload = {
        "schema_version": 1,
        "memory_types": list(memory_types),
        "documents": docs,
    }
    index_path = longterm_bm25_index_path(anima_dir)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(index_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    logger.info("Rebuilt long-term BM25 index for %s: documents=%d", anima_dir.name, len(docs))
    return LongTermBM25BuildResult(documents=len(docs), path=index_path)


def search_longterm_memory_bm25(
    anima_dir: Path,
    query: str,
    *,
    memory_types: tuple[str, ...],
    top_k: int = 10,
    offset: int = 0,
    rebuild_if_missing: bool = True,
) -> list[dict[str, Any]]:
    """Search persisted long-term memory BM25 chunks."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    payload = _load_longterm_bm25_payload(anima_dir)
    if payload is None and rebuild_if_missing:
        try:
            rebuild_longterm_bm25_index(anima_dir)
        except Exception:
            logger.debug("Long-term BM25 rebuild failed for %s", anima_dir, exc_info=True)
        payload = _load_longterm_bm25_payload(anima_dir)
    if payload is None:
        return []

    wanted = set(memory_types)
    docs = [
        doc
        for doc in payload.get("documents", [])
        if isinstance(doc, dict) and str(doc.get("memory_type", "")) in wanted and doc.get("tokens")
    ]
    if not docs:
        return []

    corpus_tokens = [list(map(str, doc.get("tokens", []))) for doc in docs]
    scores = _bm25_scores(corpus_tokens, query_tokens)
    query_set = set(query_tokens)
    ranked: list[tuple[int, float]] = []
    for idx, score in enumerate(scores):
        doc_tokens = set(corpus_tokens[idx])
        if score <= 0.0 and not (query_set & doc_tokens):
            continue
        ranked.append((idx, float(score)))
    ranked.sort(key=lambda item: item[1], reverse=True)

    search_method = "bm25" if _HAS_BM25 else "keyword_fallback"
    results: list[dict[str, Any]] = []
    for idx, score in ranked[offset : offset + top_k]:
        doc = docs[idx]
        row = {
            "doc_id": str(doc.get("doc_id", "")),
            "source_file": str(doc.get("source_file", "")),
            "content": str(doc.get("content", ""))[:2000],
            "score": score,
            "chunk_index": int(doc.get("chunk_index", 0) or 0),
            "total_chunks": int(doc.get("total_chunks", 1) or 1),
            "memory_type": str(doc.get("memory_type", "")),
            "search_method": search_method,
        }
        metadata = doc.get("metadata", {})
        if isinstance(metadata, dict):
            for key, value in metadata.items():
                if key not in row:
                    row[key] = value
        results.append(row)
    return results


def _load_longterm_bm25_payload(anima_dir: Path) -> dict[str, Any] | None:
    path = longterm_bm25_index_path(anima_dir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.debug("Failed to load long-term BM25 index %s", path, exc_info=True)
        return None
    return payload if isinstance(payload, dict) else None


def _bm25_docs_for_file(anima_dir: Path, path: Path, memory_type: str) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    frontmatter, body = _split_frontmatter(raw)
    if memory_type == "knowledge" and str(frontmatter.get("valid_until", "") or "").strip():
        return []
    chunks = _chunk_markdown(body)
    if not chunks:
        return []
    total = len(chunks)
    docs: list[dict[str, Any]] = []
    for idx, content in enumerate(chunks):
        tokens = tokenize(content)
        if not tokens:
            continue
        source_file = str(path.relative_to(anima_dir))
        metadata = _file_metadata(path, memory_type, source_file, idx, total, content, frontmatter)
        docs.append(
            {
                "doc_id": f"{anima_dir.name}/{source_file}#{idx}",
                "source_file": source_file,
                "content": content,
                "tokens": tokens,
                "chunk_index": idx,
                "total_chunks": total,
                "memory_type": memory_type,
                "metadata": metadata,
            }
        )
    return docs


def _split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    try:
        from core.memory.frontmatter import parse_frontmatter, strip_frontmatter

        meta, _ = parse_frontmatter(raw)
        return meta, strip_frontmatter(raw).strip()
    except Exception:
        return {}, raw.strip()


def _chunk_markdown(content: str) -> list[str]:
    content = content.strip()
    if not content:
        return []
    sections = re.split(r"\n(##\s+.+)", f"\n{content}")
    chunks: list[str] = []
    preamble = sections[0].strip()
    if preamble and len(preamble) > 50:
        chunks.append(preamble)
    for i in range(1, len(sections), 2):
        if i + 1 >= len(sections):
            continue
        section = f"{sections[i].strip()}\n\n{sections[i + 1].strip()}".strip()
        if section:
            chunks.append(section)
    if not chunks:
        chunks.append(content)
    return chunks


def _file_metadata(
    path: Path,
    memory_type: str,
    source_file: str,
    chunk_index: int,
    total_chunks: int,
    content: str,
    frontmatter: dict[str, Any],
) -> dict[str, Any]:
    try:
        updated_at = path.stat().st_mtime
    except OSError:
        updated_at = 0.0
    metadata: dict[str, Any] = {
        "source_file": source_file,
        "memory_type": memory_type,
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "updated_at": datetime_from_timestamp(updated_at),
        "importance": "important" if "[IMPORTANT]" in content or "[重要]" in content else "normal",
        "access_count": 0,
        "retrieved_count": 0,
        "used_count": 0,
        "last_accessed_at": "",
        "last_retrieved_at": "",
        "last_used_at": "",
    }
    for key in ("valid_until", "origin", "confidence", "created_at", "updated_at", "valid_from", "summary"):
        value = frontmatter.get(key)
        if value not in (None, ""):
            metadata[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return metadata


def datetime_from_timestamp(value: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(value, tz=UTC).isoformat()


# ── Public API ──────────────────────────────────────────────


def search_activity_log(
    anima_dir: Path,
    query: str,
    *,
    days: int = 3,
    top_k: int = 10,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """BM25 search over recent ``activity_log`` JSONL entries."""
    try:
        if not query.strip():
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        rows = _load_activity_entries(anima_dir, days)
        corpus_tokens: list[list[str]] = []
        kept: list[tuple[str, dict[str, Any]]] = []
        for date_str, entry in rows:
            if not _should_index_entry(entry):
                continue
            content = entry.get("content") or ""
            doc_tokens = tokenize(content)
            if not doc_tokens:
                continue
            corpus_tokens.append(doc_tokens)
            kept.append((date_str, entry))

        if not corpus_tokens:
            return []

        scores = _bm25_scores(corpus_tokens, query_tokens)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        window = order[offset : offset + top_k]

        search_method = "bm25" if _HAS_BM25 else "keyword_fallback"
        results: list[dict[str, Any]] = []
        for i in window:
            date_str, entry = kept[i]
            entry_content = entry.get("content") or ""
            etype = entry.get("type")
            entry_type = str(etype) if etype is not None else ""
            results.append(
                {
                    "source_file": f"activity_log/{date_str}.jsonl",
                    "content": entry_content[:2000],
                    "score": scores[i],
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "memory_type": "activity_log",
                    "search_method": search_method,
                    "ts": entry.get("ts"),
                    "tool": _entry_tool_name(entry),
                    "entry_type": entry_type,
                }
            )
        return results
    except Exception as exc:
        logger.debug("search_activity_log failed: %s", exc, exc_info=True)
        return []


def reciprocal_rank_fusion(*ranked_lists: list[dict[str, Any]], k: int = 60) -> list[dict[str, Any]]:
    """Merge ranked result lists with reciprocal rank fusion (RRF)."""
    from core.memory.retrieval.rrf import reciprocal_rank_fusion as _rrf

    return _rrf(*ranked_lists, k=k)
