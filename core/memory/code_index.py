from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Incremental BM25 index for tracked project source files."""

import json
import os
import re
import subprocess
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.memory._io import atomic_write_text
from core.memory.bm25 import _HAS_BM25, _bm25_scores, tokenize

_MAX_FILE_BYTES = 1024 * 1024
_CHUNK_LINES = 200
_CHUNK_OVERLAP = 50
_SCAN_DEBOUNCE_SECONDS = 60.0
_SCHEMA_VERSION = 1


def search_code(
    anima_dir: Path,
    project: str,
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]] | str:
    """Search tracked files in a registered project's repository."""
    if re.fullmatch(r"[A-Za-z0-9_-]+", project) is None:
        return "Error: invalid project name"
    repo = _resolve_repo(Path(anima_dir), project)
    if isinstance(repo, str):
        return repo

    index_path = Path(anima_dir) / "state" / f"code_bm25_{project}.json"
    payload = _load_index(index_path, project, repo)
    if _scan_due(payload):
        scanned = _scan(repo, project, payload)
        if isinstance(scanned, str):
            return scanned
        payload = scanned
        atomic_write_text(index_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    query_tokens = tokenize(query)
    if not query_tokens or limit <= 0:
        return []
    documents = [
        doc
        for record in payload.get("files", {}).values()
        if isinstance(record, dict)
        for doc in record.get("documents", [])
        if isinstance(doc, dict) and set(query_tokens) & set(doc.get("tokens", []))
    ]
    if not documents:
        return []

    corpus = [list(map(str, doc.get("tokens", []))) for doc in documents]
    scores = _bm25_scores(corpus, query_tokens)
    ranked = sorted(range(len(documents)), key=lambda i: scores[i], reverse=True)[:limit]
    last_scan = str(payload.get("last_scan", ""))
    return [
        {
            "source_file": documents[i]["source_file"],
            "content": documents[i]["content"],
            "score": scores[i],
            "chunk_index": documents[i]["chunk_index"],
            "total_chunks": documents[i]["total_chunks"],
            "memory_type": "code",
            "search_method": "bm25" if _HAS_BM25 else "keyword_fallback",
            "last_scan": last_scan,
        }
        for i in ranked
    ]


def _resolve_repo(anima_dir: Path, project: str) -> Path | str:
    try:
        projects = json.loads((anima_dir / "projects.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"Error: cannot read projects.json: {exc}"
    entry = projects.get(project) if isinstance(projects, dict) else None
    repo_value = entry.get("repo") if isinstance(entry, dict) else None
    if not isinstance(repo_value, str) or not repo_value:
        return f"Error: project '{project}' is not registered in projects.json"
    repo = Path(repo_value)
    if not repo.is_absolute() or not repo.is_dir() or not os.access(repo, os.R_OK | os.X_OK):
        return f"Error: repository for project '{project}' is not readable: {repo}"
    return repo.resolve()


def _load_index(path: Path, project: str, repo: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != _SCHEMA_VERSION
        or payload.get("project") != project
        or payload.get("repo") != str(repo)
        or not isinstance(payload.get("files"), dict)
    ):
        return {
            "schema_version": _SCHEMA_VERSION,
            "project": project,
            "repo": str(repo),
            "files": {},
        }
    return payload


def _scan_due(payload: dict[str, Any]) -> bool:
    last_scan = payload.get("last_scan")
    if not isinstance(last_scan, str):
        return True
    try:
        scanned_at = datetime.fromisoformat(last_scan)
        return (datetime.now(UTC) - scanned_at).total_seconds() >= _SCAN_DEBOUNCE_SECONDS
    except (TypeError, ValueError):
        return True


def _tracked_files(repo: Path) -> list[str] | str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z"],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"Error: failed to list tracked files in {repo}: {exc}"
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        return f"Error: failed to list tracked files in {repo}: {detail or 'git ls-files failed'}"
    return [os.fsdecode(item) for item in result.stdout.split(b"\0") if item]


def _scan(repo: Path, project: str, payload: dict[str, Any]) -> dict[str, Any] | str:
    tracked = _tracked_files(repo)
    if isinstance(tracked, str):
        return tracked
    old_files = payload.get("files", {})
    files: dict[str, Any] = {}
    for relative in tracked:
        path = repo / relative
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(repo) or not resolved.is_file():
                continue
            stat = resolved.stat()
        except OSError:
            continue
        if stat.st_size > _MAX_FILE_BYTES:
            continue
        previous = old_files.get(relative)
        if (
            isinstance(previous, dict)
            and previous.get("mtime_ns") == stat.st_mtime_ns
            and previous.get("size") == stat.st_size
        ):
            files[relative] = previous
            continue
        try:
            raw = resolved.read_bytes()
        except OSError:
            continue
        if b"\0" in raw:
            continue
        documents = _documents(project, relative, raw.decode("utf-8", errors="replace").splitlines())
        files[relative] = {
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            "documents": documents,
        }
    return {
        "schema_version": _SCHEMA_VERSION,
        "project": project,
        "repo": str(repo),
        "last_scan": datetime.now(UTC).isoformat(),
        "files": files,
    }


def _documents(project: str, relative: str, lines: list[str]) -> list[dict[str, Any]]:
    chunks = list(_line_chunks(lines))
    total = len(chunks)
    documents: list[dict[str, Any]] = []
    for index, (start, end, content) in enumerate(chunks):
        tokens = tokenize(content)
        if not tokens:
            continue
        documents.append(
            {
                "source_file": f"code:{project}/{relative}#L{start}-L{end}",
                "content": content,
                "tokens": tokens,
                "chunk_index": index,
                "total_chunks": total,
            }
        )
    return documents


def _line_chunks(lines: list[str]) -> Iterable[tuple[int, int, str]]:
    if not lines:
        return
    step = _CHUNK_LINES - _CHUNK_OVERLAP
    start = 0
    while start < len(lines):
        end = min(start + _CHUNK_LINES, len(lines))
        yield start + 1, end, "\n".join(lines[start:end])
        if end == len(lines):
            break
        start += step
