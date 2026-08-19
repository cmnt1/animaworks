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
import math
import os
import re
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from core.memory._io import atomic_write_text
from core.memory.rag.exclusion import is_archive_path
from core.time_utils import ensure_aware, get_app_timezone, today_local

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

_TOKEN_RE = re.compile(
    r"[A-Za-z0-9_]+|[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0e00-\u0e7fー]+|[^\W\d_]+",
    re.UNICODE,
)

LONGTERM_BM25_INDEX_FILE = "bm25_longterm_index.json"
LONGTERM_BM25_DELTA_FILE = "bm25_longterm_delta.json"
LONGTERM_BM25_DIRTY_FILE = "bm25_longterm_index.dirty"
LONGTERM_BM25_REBUILD_MARKER_FILE = "bm25_longterm_index.rebuild"
LONGTERM_BM25_REBUILD_COOLDOWN_SECONDS = 600.0
LONGTERM_BM25_REBUILD_LOCK_STALE_SECONDS = 1800.0
LONGTERM_BM25_MEMORY_TYPES: tuple[str, ...] = ("knowledge", "episodes", "procedures")
LONGTERM_BM25_SCHEMA_VERSION = 4
_LONGTERM_BM25_CACHE: dict[Path, tuple[int, int, dict[str, Any]]] = {}
_LONGTERM_BM25_DELTA_CACHE: dict[Path, tuple[int, int, dict[str, Any]]] = {}
_LONGTERM_MERGED_CACHE: dict[tuple[Path, tuple[int, int, int, int]], dict[str, Any]] = {}
_LONGTERM_QUERY_CACHE: dict[
    tuple[Path, tuple[int, ...], tuple[str, ...]],
    tuple[list[dict[str, Any]], tuple[tuple[int, float], ...]],
] = {}


@dataclass(frozen=True)
class LongTermBM25BuildResult:
    """Summary of a long-term BM25 index rebuild."""

    documents: int
    path: Path


# ── Tokenizer ───────────────────────────────────────────────


def tokenize(text: str) -> list[str]:
    """Split *text* into filtered lowercase tokens for BM25 indexing."""
    out: list[str] = []
    for match in _TOKEN_RE.finditer(text):
        raw = match.group(0)
        t = raw.lower()
        if t in _STOPWORDS:
            continue
        if not raw.isascii() or len(t) >= 3:
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


# Tokenized activity corpus cache. Re-tokenizing thousands of JSONL entries on
# every query cost ~5s per search on busy animas (2026-08-13 profile).
# Keyed by anima dir + days; invalidated when any day file's (mtime, size) moves.
_ACTIVITY_CORPUS_CACHE: dict[
    tuple[str, int],
    tuple[tuple[tuple[str, int, int, int], ...], list[list[str]], list[tuple[str, dict[str, Any]]]],
] = {}


def _activity_files_signature(anima_dir: Path, days: int) -> tuple[tuple[str, int, int, int], ...]:
    base = anima_dir / "activity_log"
    sig: list[tuple[str, int, int, int]] = []
    for d in _activity_log_dates(days):
        path = base / f"{d.isoformat()}.jsonl"
        try:
            stat = path.stat()
        except OSError:
            continue
        sig.append((d.isoformat(), stat.st_mtime_ns, stat.st_size, stat.st_ino))
    return tuple(sig)


def _activity_corpus_cached(anima_dir: Path, days: int) -> tuple[list[list[str]], list[tuple[str, dict[str, Any]]]]:
    key = (str(anima_dir), days)
    signature = _activity_files_signature(anima_dir, days)
    cached = _ACTIVITY_CORPUS_CACHE.get(key)
    if cached is not None and cached[0] == signature:
        return cached[1], cached[2]

    if cached is not None:
        previous = {date_str: (mtime, size, inode) for date_str, mtime, size, inode in cached[0]}
        changed = [row for row in signature if previous.get(row[0]) != row[1:]]
        if len(changed) == 1:
            date_str, _mtime, size, inode = changed[0]
            old = previous.get(date_str)
            if old is not None and old[1] > 0 and old[2] == inode and size > old[1]:
                path = anima_dir / "activity_log" / f"{date_str}.jsonl"
                try:
                    with path.open("rb") as f:
                        f.seek(old[1] - 1)
                        if f.read(1) == b"\n":
                            appended = f.read(size - old[1]).decode("utf-8")
                        else:
                            appended = ""
                except (OSError, UnicodeError):
                    appended = ""
                if appended:
                    corpus_tokens = list(cached[1])
                    kept = list(cached[2])
                    for line in appended.splitlines():
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(entry, dict) or not _should_index_entry(entry):
                            continue
                        doc_tokens = tokenize(entry.get("content") or "")
                        if doc_tokens:
                            corpus_tokens.append(doc_tokens)
                            kept.append((date_str, entry))
                    _ACTIVITY_CORPUS_CACHE[key] = (signature, corpus_tokens, kept)
                    return corpus_tokens, kept

    corpus_tokens: list[list[str]] = []
    kept: list[tuple[str, dict[str, Any]]] = []
    for date_str, entry in _load_activity_entries(anima_dir, days):
        if not _should_index_entry(entry):
            continue
        doc_tokens = tokenize(entry.get("content") or "")
        if not doc_tokens:
            continue
        corpus_tokens.append(doc_tokens)
        kept.append((date_str, entry))
    _ACTIVITY_CORPUS_CACHE[key] = (signature, corpus_tokens, kept)
    # ponytail: unbounded only by anima count x days variants; tiny in practice.
    return corpus_tokens, kept


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


def longterm_bm25_dirty_path(anima_dir: Path) -> Path:
    """Return the dirty marker path for the long-term BM25 index."""
    return anima_dir / "state" / LONGTERM_BM25_DIRTY_FILE


def longterm_bm25_delta_path(anima_dir: Path) -> Path:
    """Return the atomic source-delta store path for one anima."""
    return anima_dir / "state" / LONGTERM_BM25_DELTA_FILE


@contextmanager
def _longterm_delta_lock(anima_dir: Path):
    """Serialize read-modify-write updates to the source delta store."""
    from core.platform.locks import file_lock

    path = longterm_bm25_delta_path(anima_dir).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle, file_lock(handle, exclusive=True):
        yield


def _json_dumps(value: Any) -> str:
    try:
        import orjson

        return orjson.dumps(value).decode("utf-8")
    except ImportError:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_bytes()
        try:
            import orjson

            value = orjson.loads(raw)
        except ImportError:
            value = json.loads(raw)
    except (OSError, ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def update_longterm_bm25_source(anima_dir: Path, source_file: str) -> Path:
    """Atomically replace or tombstone one long-term source in the live delta."""
    source_file = source_file.replace("\\", "/").lstrip("/")
    memory_type = source_file.partition("/")[0]
    if memory_type not in LONGTERM_BM25_MEMORY_TYPES or not source_file.endswith(".md"):
        raise ValueError(f"Unsupported long-term memory source: {source_file}")
    path = anima_dir / source_file
    try:
        resolved = path.resolve()
        inside = resolved.is_relative_to(anima_dir.resolve())
    except OSError:
        inside = False
    if not inside:
        raise ValueError(f"Source resolves outside anima directory: {source_file}")

    delta_path = longterm_bm25_delta_path(anima_dir)
    with _longterm_delta_lock(anima_dir):
        docs = (
            _bm25_docs_for_file(anima_dir, resolved, memory_type)
            if resolved.is_file() and not is_archive_path(resolved, root=anima_dir / memory_type)
            else []
        )
        try:
            source_stat = resolved.stat()
            source_signature = [source_stat.st_mtime_ns, source_stat.st_size]
        except OSError:
            source_signature = None
        payload = _load_json_object(delta_path) or {}
        sources = payload.get("sources")
        if not isinstance(sources, dict):
            sources = {}
        sources[source_file] = {
            "documents": docs,
            "tombstone": not docs,
            "source_signature": source_signature,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        atomic_write_text(
            delta_path,
            _json_dumps({"schema_version": LONGTERM_BM25_SCHEMA_VERSION, "sources": sources}) + "\n",
        )
    _LONGTERM_BM25_DELTA_CACHE.pop(delta_path, None)
    _LONGTERM_MERGED_CACHE.clear()
    _LONGTERM_QUERY_CACHE.clear()
    mark_longterm_bm25_dirty(anima_dir, reason=f"source_update:{source_file}")
    return delta_path


def _sync_longterm_bm25_sources(anima_dir: Path, base: dict[str, Any] | None) -> None:
    """Stat live Markdown sources and delta-index only paths whose signature changed."""
    if base is None:
        return
    indexed: dict[str, tuple[int, int]] = {}
    for doc in (base or {}).get("documents", []):
        if not isinstance(doc, dict):
            continue
        source = str(doc.get("source_file", ""))
        try:
            indexed[source] = (int(doc.get("source_mtime_ns") or -1), int(doc.get("source_size") or -1))
        except (TypeError, ValueError):
            indexed[source] = (-1, -1)
    delta = _load_longterm_bm25_delta(anima_dir)
    sources = delta.get("sources") if delta else None
    if isinstance(sources, dict):
        for source, value in sources.items():
            documents = value.get("documents", []) if isinstance(value, dict) else []
            doc = next((item for item in documents if isinstance(item, dict)), None)
            if doc is not None:
                indexed[str(source)] = (int(doc.get("source_mtime_ns") or -1), int(doc.get("source_size") or -1))
            elif isinstance(value, dict) and value.get("tombstone"):
                signature = value.get("source_signature")
                if isinstance(signature, list) and len(signature) == 2:
                    indexed[str(source)] = (int(signature[0]), int(signature[1]))
                else:
                    indexed.pop(str(source), None)

    live: dict[str, tuple[int, int]] = {}
    for memory_type in LONGTERM_BM25_MEMORY_TYPES:
        root = anima_dir / memory_type
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            if is_archive_path(path, root=root):
                continue
            try:
                stat = path.stat()
                live[path.relative_to(anima_dir).as_posix()] = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                continue
    for source in sorted(live.keys() | indexed.keys()):
        if live.get(source) != indexed.get(source):
            update_longterm_bm25_source(anima_dir, source)


def mark_longterm_bm25_dirty(anima_dir: Path, *, reason: str = "") -> Path:
    """Mark the persisted long-term BM25 index as stale without rebuilding it."""
    path = longterm_bm25_dirty_path(anima_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "dirty_at": datetime.now(UTC).isoformat(),
        "reason": reason,
    }
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return path


def clear_longterm_bm25_dirty(anima_dir: Path) -> None:
    """Clear the long-term BM25 dirty marker if it exists."""
    try:
        longterm_bm25_dirty_path(anima_dir).unlink()
    except FileNotFoundError:
        pass
    except OSError:
        logger.debug("Failed to clear long-term BM25 dirty marker for %s", anima_dir, exc_info=True)


def is_longterm_bm25_dirty(anima_dir: Path) -> bool:
    """Return True when writes have marked the persisted BM25 index stale."""
    return longterm_bm25_dirty_path(anima_dir).is_file()


def longterm_bm25_rebuild_marker_path(anima_dir: Path) -> Path:
    """Return the cooldown marker path recording the last rebuild attempt."""
    return anima_dir / "state" / LONGTERM_BM25_REBUILD_MARKER_FILE


def maybe_rebuild_dirty_longterm_bm25(
    anima_dir: Path,
    *,
    cooldown_seconds: float = LONGTERM_BM25_REBUILD_COOLDOWN_SECONDS,
) -> bool:
    """Rebuild the long-term BM25 index on-demand when it is marked dirty.

    Consumes the dirty marker that writes leave behind (F14). A rebuild runs
    only when the index is dirty and at least ``cooldown_seconds`` have elapsed
    since the last attempt. The attempt time is persisted as a marker file's
    mtime so the cooldown survives process restarts and so repeated failures do
    not trigger a rebuild on every search. On success the dirty marker is
    cleared by ``rebuild_longterm_bm25_index``; on failure it is left in place
    for a retry after the next cooldown window.

    Returns True when a rebuild was attempted.
    """
    if not is_longterm_bm25_dirty(anima_dir):
        return False
    if _load_longterm_bm25_delta(anima_dir) is not None:
        return False
    marker = longterm_bm25_rebuild_marker_path(anima_dir)
    now = time.time()
    try:
        last_attempt = marker.stat().st_mtime
    except OSError:
        last_attempt = None
    if last_attempt is not None and (now - last_attempt) < cooldown_seconds:
        return False
    # Single-flight: concurrent searches must not stack heavy rebuilds. The
    # O_EXCL lock file admits one rebuilder; others keep serving the stale
    # index. A lock left behind by a crashed process is stolen after
    # LONGTERM_BM25_REBUILD_LOCK_STALE_SECONDS.
    lock_path = marker.with_name(marker.name + ".lock")
    lock_fd = _acquire_rebuild_lock(lock_path, now)
    if lock_fd is None:
        return False
    try:
        # Record the attempt before rebuilding so a failing rebuild still
        # respects the cooldown instead of retrying on every subsequent search.
        try:
            marker.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(marker, f"{now}\n")
        except OSError:
            logger.debug("Failed to write BM25 rebuild cooldown marker for %s", anima_dir, exc_info=True)
        try:
            rebuild_longterm_bm25_index(anima_dir)
        except Exception:
            logger.warning("On-demand long-term BM25 rebuild failed for %s", anima_dir.name, exc_info=True)
        return True
    finally:
        os.close(lock_fd)
        lock_path.unlink(missing_ok=True)


def _acquire_rebuild_lock(lock_path: Path, now: float) -> int | None:
    """Acquire the single-flight rebuild lock; return an fd or None."""
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        try:
            if (now - lock_path.stat().st_mtime) < LONGTERM_BM25_REBUILD_LOCK_STALE_SECONDS:
                return None
            lock_path.unlink()
            return os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            return None
    except OSError:
        logger.debug("Failed to acquire BM25 rebuild lock at %s", lock_path, exc_info=True)
        return None


def rebuild_longterm_bm25_index(
    anima_dir: Path,
    *,
    memory_types: tuple[str, ...] = LONGTERM_BM25_MEMORY_TYPES,
) -> LongTermBM25BuildResult:
    """Persist a tokenized BM25 corpus for knowledge/episodes/procedures."""
    with _longterm_delta_lock(anima_dir):
        docs: list[dict[str, Any]] = []
        for memory_type in memory_types:
            base_dir = anima_dir / memory_type
            if not base_dir.is_dir():
                continue
            for path in sorted(base_dir.rglob("*.md")):
                if is_archive_path(path, root=base_dir):
                    continue
                docs.extend(_bm25_docs_for_file(anima_dir, path, memory_type))

        document_frequency: Counter[str] = Counter()
        total_doc_len = 0
        for doc in docs:
            tokens = list(map(str, doc.get("tokens", [])))
            total_doc_len += len(tokens)
            document_frequency.update(set(tokens))

        payload = {
            "schema_version": LONGTERM_BM25_SCHEMA_VERSION,
            "memory_types": list(memory_types),
            "document_count": len(docs),
            "avgdl": total_doc_len / len(docs) if docs else 0.0,
            "document_frequency": dict(document_frequency),
            "documents": docs,
        }
        index_path = longterm_bm25_index_path(anima_dir)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(index_path, _json_dumps(payload) + "\n")
        delta_path = longterm_bm25_delta_path(anima_dir)
        delta_path.unlink(missing_ok=True)
        _LONGTERM_BM25_DELTA_CACHE.pop(delta_path, None)
        _LONGTERM_BM25_CACHE.pop(index_path, None)
        _LONGTERM_MERGED_CACHE.clear()
        _LONGTERM_QUERY_CACHE.clear()
        clear_longterm_bm25_dirty(anima_dir)
    logger.info("Rebuilt long-term BM25 index for %s: documents=%d", anima_dir.name, len(docs))
    return LongTermBM25BuildResult(documents=len(docs), path=index_path)


def search_longterm_memory_bm25(
    anima_dir: Path,
    query: str,
    *,
    memory_types: tuple[str, ...],
    top_k: int = 10,
    offset: int = 0,
    rebuild_if_missing: bool = False,
    validate_sources: bool = True,
) -> list[dict[str, Any]]:
    """Search persisted long-term memory BM25 chunks."""
    search_started = time.perf_counter()
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    load_started = time.perf_counter()
    base_payload = _load_longterm_bm25_payload(anima_dir)
    load_elapsed = time.perf_counter() - load_started
    sync_started = time.perf_counter()
    if validate_sources:
        _sync_longterm_bm25_sources(anima_dir, base_payload)
    sync_elapsed = time.perf_counter() - sync_started
    merge_started = time.perf_counter()
    payload = _merged_longterm_bm25_payload(anima_dir, base_payload)
    merge_elapsed = time.perf_counter() - merge_started
    logger.info(
        "Long-term BM25 prepare: anima=%s query_chars=%d load=%.3fs sync=%.3fs merge=%.3fs "
        "validate_sources=%s available=%s",
        anima_dir.name,
        len(query),
        load_elapsed,
        sync_elapsed,
        merge_elapsed,
        validate_sources,
        payload is not None,
    )
    if base_payload is not None and int(base_payload.get("schema_version") or 0) != LONGTERM_BM25_SCHEMA_VERSION:
        mark_longterm_bm25_dirty(anima_dir, reason="schema_upgrade")
    if payload is None and rebuild_if_missing:
        try:
            rebuild_longterm_bm25_index(anima_dir)
        except Exception:
            logger.debug("Long-term BM25 rebuild failed for %s", anima_dir, exc_info=True)
        base_payload = _load_longterm_bm25_payload(anima_dir)
        payload = _merged_longterm_bm25_payload(anima_dir, base_payload)
    if payload is None:
        return []

    wanted = set(memory_types)
    all_docs = [doc for doc in payload.get("documents", []) if isinstance(doc, dict) and doc.get("tokens")]
    docs = [doc for doc in all_docs if str(doc.get("memory_type", "")) in wanted]
    if not docs:
        return []

    index_path = longterm_bm25_index_path(anima_dir)
    signature_parts: list[int] = []
    for path in (index_path, longterm_bm25_delta_path(anima_dir)):
        try:
            stat = path.stat()
            signature_parts.extend((stat.st_mtime_ns, stat.st_size))
        except OSError:
            signature_parts.extend((0, 0))
    signature = tuple(signature_parts)
    validation_started = time.perf_counter()
    logger.info(
        "Long-term BM25 validation: anima=%s types=%s elapsed=%.3fs needed=%s sources=%d",
        anima_dir.name,
        ",".join(sorted(wanted)),
        time.perf_counter() - validation_started,
        False,
        0,
    )

    query_key = (
        index_path,
        signature,
        tuple(query_tokens),
    )
    cached_query = _LONGTERM_QUERY_CACHE.get(query_key)
    score_started = time.perf_counter()
    score_cached = cached_query is not None
    if cached_query is None:
        corpus_tokens = [doc.get("tokens", []) for doc in all_docs]
        scores = _longterm_bm25_scores(all_docs, corpus_tokens, query_tokens, payload)
        ranked_list = [(idx, float(score)) for idx, score in enumerate(scores) if score > 0.0]
        ranked_list.sort(key=lambda item: item[1], reverse=True)
        cached_query = (all_docs, tuple(ranked_list))
        if len(_LONGTERM_QUERY_CACHE) >= 64:
            _LONGTERM_QUERY_CACHE.pop(next(iter(_LONGTERM_QUERY_CACHE)))
        _LONGTERM_QUERY_CACHE[query_key] = cached_query
    ranked_docs, ranked = cached_query
    logger.info(
        "Long-term BM25 score: anima=%s tokens=%d docs=%d elapsed=%.3fs cached=%s hits=%d",
        anima_dir.name,
        len(query_tokens),
        len(all_docs),
        time.perf_counter() - score_started,
        score_cached,
        len(ranked),
    )

    search_method = "bm25"
    results: list[dict[str, Any]] = []
    source_cache: dict[str, tuple[int, int, set[tuple[int, str]]]] = {}
    skipped_valid = 0
    for idx, score in ranked:
        doc = ranked_docs[idx]
        if str(doc.get("memory_type", "")) not in wanted:
            continue
        if validate_sources and not _longterm_doc_matches_current_source(anima_dir, doc, source_cache):
            continue
        if skipped_valid < offset:
            skipped_valid += 1
            continue
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
        if len(results) >= top_k:
            break
    logger.info(
        "Long-term BM25 complete: anima=%s elapsed=%.3fs results=%d",
        anima_dir.name,
        time.perf_counter() - search_started,
        len(results),
    )
    return results


def _load_longterm_bm25_payload(anima_dir: Path) -> dict[str, Any] | None:
    path = longterm_bm25_index_path(anima_dir)
    if not path.is_file():
        return None
    try:
        stat = path.stat()
    except OSError:
        return None
    cached = _LONGTERM_BM25_CACHE.get(path)
    if cached is not None and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        return cached[2]
    payload = _load_json_object(path)
    if payload is None:
        logger.debug("Failed to load long-term BM25 index %s", path, exc_info=True)
        return None
    _LONGTERM_BM25_CACHE[path] = (stat.st_mtime_ns, stat.st_size, payload)
    return payload


def _load_longterm_bm25_delta(anima_dir: Path) -> dict[str, Any] | None:
    path = longterm_bm25_delta_path(anima_dir)
    try:
        stat = path.stat()
    except OSError:
        return None
    cached = _LONGTERM_BM25_DELTA_CACHE.get(path)
    if cached is not None and cached[:2] == (stat.st_mtime_ns, stat.st_size):
        return cached[2]
    payload = _load_json_object(path)
    if payload is None or int(payload.get("schema_version") or 0) != LONGTERM_BM25_SCHEMA_VERSION:
        return None
    _LONGTERM_BM25_DELTA_CACHE[path] = (stat.st_mtime_ns, stat.st_size, payload)
    return payload


def _merged_longterm_bm25_payload(anima_dir: Path, base: dict[str, Any] | None) -> dict[str, Any] | None:
    """Overlay source replacements/tombstones and rebuild only cheap corpus stats."""
    signatures: list[int] = []
    for path in (longterm_bm25_index_path(anima_dir), longterm_bm25_delta_path(anima_dir)):
        try:
            stat = path.stat()
            signatures.extend((stat.st_mtime_ns, stat.st_size))
        except OSError:
            signatures.extend((0, 0))
    cache_key = (anima_dir, tuple(signatures))
    cached = _LONGTERM_MERGED_CACHE.get(cache_key)
    if cached is not None:
        return cached
    base_version = int((base or {}).get("schema_version") or 0)
    base_usable = base_version in {LONGTERM_BM25_SCHEMA_VERSION - 1, LONGTERM_BM25_SCHEMA_VERSION}
    delta = _load_longterm_bm25_delta(anima_dir)
    if base_usable and delta is None:
        return base
    docs = [doc for doc in (base or {}).get("documents", []) if isinstance(doc, dict)] if base_usable else []
    sources = delta.get("sources") if delta else None
    if isinstance(sources, dict):
        replaced = set(map(str, sources))
        docs = [doc for doc in docs if str(doc.get("source_file", "")) not in replaced]
        for value in sources.values():
            if not isinstance(value, dict) or value.get("tombstone"):
                continue
            docs.extend(doc for doc in value.get("documents", []) if isinstance(doc, dict))
    if not base_usable and not docs:
        return None
    corpus_tokens = [list(map(str, doc.get("tokens", []))) for doc in docs]
    payload = {
        "schema_version": LONGTERM_BM25_SCHEMA_VERSION,
        "document_count": len(docs),
        "avgdl": sum(map(len, corpus_tokens)) / len(docs) if docs else 0.0,
        "document_frequency": _document_frequency(corpus_tokens),
        "documents": docs,
    }
    if len(_LONGTERM_MERGED_CACHE) >= 8:
        _LONGTERM_MERGED_CACHE.pop(next(iter(_LONGTERM_MERGED_CACHE)))
    _LONGTERM_MERGED_CACHE[cache_key] = payload
    return payload


def _longterm_bm25_scores(
    docs: list[dict[str, Any]],
    corpus_tokens: list[list[str]],
    query_tokens: list[str],
    payload: dict[str, Any],
) -> list[float]:
    """Score long-term docs from persisted BM25 stats without rebuilding BM25Okapi."""
    if not docs or not query_tokens:
        return [0.0] * len(docs)
    document_count = int(payload.get("document_count") or len(docs))
    avgdl = float(payload.get("avgdl") or 0.0)
    if avgdl <= 0.0:
        avgdl = sum(len(tokens) for tokens in corpus_tokens) / max(1, len(corpus_tokens))
    df_raw = payload.get("document_frequency")
    document_frequency = dict(df_raw) if isinstance(df_raw, dict) else _document_frequency(corpus_tokens)

    k1 = 1.5
    b = 0.75
    scores: list[float] = []
    for doc, tokens in zip(docs, corpus_tokens, strict=False):
        doc_len = float(doc.get("doc_len") or len(tokens) or 1)
        counts_raw = doc.get("token_counts")
        token_counts = counts_raw if isinstance(counts_raw, dict) else Counter(tokens)
        score = 0.0
        for term in query_tokens:
            tf = float(token_counts.get(term, 0.0) or 0.0)
            if tf <= 0.0:
                continue
            df = max(0.0, float(document_frequency.get(term, 0.0) or 0.0))
            idf = math.log(1.0 + (document_count - df + 0.5) / (df + 0.5))
            denom = tf + k1 * (1.0 - b + b * (doc_len / max(avgdl, 1e-9)))
            score += idf * ((tf * (k1 + 1.0)) / denom)
        scores.append(score)
    return scores


def _document_frequency(corpus_tokens: list[list[str]]) -> dict[str, int]:
    df: Counter[str] = Counter()
    for tokens in corpus_tokens:
        df.update(set(tokens))
    return dict(df)


def _bm25_docs_for_file(anima_dir: Path, path: Path, memory_type: str) -> list[dict[str, Any]]:
    try:
        from core.memory.rag.indexer import MemoryIndexer

        if MemoryIndexer.is_ragignored(path):
            return []
    except Exception:
        logger.debug("Failed to evaluate .ragignore for BM25 file %s", path, exc_info=True)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    try:
        stat = path.stat()
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
        # Contextual headers for episodes/knowledge so date/title tokens are searchable.
        if memory_type in ("knowledge", "episodes"):
            try:
                from core.memory.rag.contextual_header import apply_contextual_header

                content = apply_contextual_header(
                    content,
                    file_path=path,
                    body=body,
                    memory_type=memory_type,
                    frontmatter=frontmatter,
                )
            except Exception:
                logger.debug("Failed to apply contextual header for BM25 file %s", path, exc_info=True)
        tokens = tokenize(content)
        if not tokens:
            continue
        token_counts = Counter(tokens)
        source_file = path.relative_to(anima_dir).as_posix()
        metadata = _file_metadata(path, memory_type, source_file, idx, total, content, frontmatter)
        docs.append(
            {
                "doc_id": f"{anima_dir.name}/{source_file}#{idx}",
                "source_file": source_file,
                "content": content,
                "tokens": tokens,
                "token_counts": dict(token_counts),
                "doc_len": len(tokens),
                "source_mtime_ns": stat.st_mtime_ns,
                "source_size": stat.st_size,
                "chunk_index": idx,
                "total_chunks": total,
                "memory_type": memory_type,
                "metadata": metadata,
            }
        )
    return docs


def _longterm_doc_matches_current_source(
    anima_dir: Path,
    doc: dict[str, Any],
    cache: dict[str, tuple[int, int, set[tuple[int, str]]]],
) -> bool:
    """Validate an indexed source using filesystem metadata only."""
    source_file = str(doc.get("source_file", "") or "")
    memory_type = str(doc.get("memory_type", "") or "")
    if memory_type not in LONGTERM_BM25_MEMORY_TYPES or not source_file.startswith(f"{memory_type}/"):
        return False
    try:
        indexed_mtime_ns = int(doc.get("source_mtime_ns") or -1)
        indexed_size = int(doc.get("source_size") or -1)
    except (TypeError, ValueError):
        indexed_mtime_ns = -1
        indexed_size = -1
    cached_source = cache.get(source_file)
    if cached_source is None:
        path = anima_dir / source_file
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(anima_dir.resolve()) or not resolved.is_file():
                return False
            stat = resolved.stat()
        except OSError:
            return False
        try:
            from core.memory.rag.indexer import MemoryIndexer

            if MemoryIndexer.is_ragignored(resolved):
                return False
        except Exception:
            logger.debug("Failed to evaluate .ragignore for BM25 file %s", resolved, exc_info=True)
        cached_source = (stat.st_mtime_ns, stat.st_size, set())
        cache[source_file] = cached_source
    return (indexed_mtime_ns, indexed_size) == cached_source[:2]


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


def _parse_search_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ensure_aware(parsed).astimezone(UTC)


def _activity_entry_time(date_str: str, entry: dict[str, Any]) -> datetime:
    parsed = _parse_search_time(str(entry.get("ts") or ""))
    if parsed is not None:
        return parsed
    return (
        datetime.fromisoformat(date_str)
        .replace(tzinfo=get_app_timezone(), hour=23, minute=59, second=59, microsecond=999999)
        .astimezone(UTC)
    )


def search_activity_log(
    anima_dir: Path,
    query: str,
    *,
    days: int = 3,
    top_k: int = 10,
    offset: int = 0,
    time_start: str | None = None,
    time_end: str | None = None,
) -> list[dict[str, Any]]:
    """BM25 search over recent ``activity_log`` JSONL entries."""
    try:
        if not query.strip():
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        start = _parse_search_time(time_start)
        end = _parse_search_time(time_end)
        if start is not None and end is not None and start > end:
            start, end = end, start

        corpus_tokens, kept = _activity_corpus_cached(anima_dir, days)
        if not corpus_tokens:
            return []

        scores = _bm25_scores(corpus_tokens, query_tokens)
        query_set = set(query_tokens)
        order = [
            i
            for i, doc_tokens in enumerate(corpus_tokens)
            if query_set.intersection(doc_tokens)
            and (start is None or _activity_entry_time(*kept[i]) >= start)
            and (end is None or _activity_entry_time(*kept[i]) <= end)
        ]
        order.sort(key=lambda i: scores[i], reverse=True)
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
