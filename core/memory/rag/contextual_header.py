from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Contextual chunk headers for memory indexing.

Prefixes episode / knowledge chunks with a one-line context header so that
date, file title, and heading path participate in embeddings and BM25 tokens.

Format: ``[<date> | <file title> > <heading path>]``
Missing parts are omitted (e.g. no date → ``[<title> > <heading>]``).
"""

import re
from pathlib import Path
from typing import Any

# Memory types that receive contextual headers on chunk content.
CONTEXTUAL_HEADER_MEMORY_TYPES: frozenset[str] = frozenset(
    {
        "episodes",
        "knowledge",
        "common_knowledge",
    }
)

_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")
_ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_H1_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
# Heading path uses ##+ only; H1 is reserved for file title resolution.
_HEADING_LINE_RE = re.compile(r"^(#{2,6})\s+(.+)$")

# Frontmatter keys checked (in order) when filename has no date prefix.
_FRONTMATTER_DATE_KEYS: tuple[str, ...] = (
    "date",
    "created_at",
    "created",
    "valid_from",
)


def resolve_chunk_date(
    file_path: Path,
    frontmatter: dict[str, Any] | None = None,
) -> str | None:
    """Resolve a ``YYYY-MM-DD`` date for the contextual header.

    Order: filename stem prefix → frontmatter date fields → None.
    """
    match = _DATE_PREFIX_RE.match(file_path.stem)
    if match:
        return match.group(1)

    fm = frontmatter or {}
    for key in _FRONTMATTER_DATE_KEYS:
        raw = fm.get(key)
        if raw is None:
            continue
        text = str(raw).strip()
        if not text:
            continue
        dm = _ISO_DATE_RE.search(text)
        if dm:
            return dm.group(1)
    return None


def resolve_file_title(
    file_path: Path,
    body: str,
    frontmatter: dict[str, Any] | None = None,
) -> str:
    """Resolve file title: frontmatter ``title`` → H1 → filename stem."""
    fm = frontmatter or {}
    title = fm.get("title")
    if title is not None and str(title).strip():
        return str(title).strip()

    h1 = _H1_RE.search(body or "")
    if h1:
        return h1.group(1).strip()

    return file_path.stem


def extract_heading_path(chunk_content: str) -> str | None:
    """Return the chunk's belonging heading text (``##``+), or None.

    Uses the first heading line in the chunk. Nested headings deeper in the
    body are not part of the path (chunk ownership is the section heading).
    """
    if not chunk_content:
        return None
    for line in chunk_content.strip().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = _HEADING_LINE_RE.match(stripped)
        if match:
            return match.group(2).strip()
        # First non-empty line is not a section heading.
        return None
    return None


def build_contextual_chunk_header(
    *,
    date: str | None,
    file_title: str,
    heading_path: str | None = None,
) -> str:
    """Build a one-line contextual header in bracket form."""
    title = (file_title or "").strip() or "untitled"
    heading = (heading_path or "").strip()
    if heading:
        title_part = f"{title} > {heading}"
    else:
        title_part = title

    date_s = (date or "").strip()
    if date_s:
        return f"[{date_s} | {title_part}]"
    return f"[{title_part}]"


def apply_contextual_header(
    chunk_content: str,
    *,
    file_path: Path,
    body: str,
    memory_type: str,
    frontmatter: dict[str, Any] | None = None,
    heading_path: str | None = None,
) -> str:
    """Prefix *chunk_content* with a contextual header when applicable.

    Args:
        chunk_content: Raw chunk body (without header).
        file_path: Source file path (for date prefix / stem title).
        body: Full file body after frontmatter strip (for H1 title).
        memory_type: Memory type; only CONTEXTUAL_HEADER_MEMORY_TYPES are wrapped.
        frontmatter: Parsed frontmatter dict.
        heading_path: Optional explicit heading path; when None, extracted from
            *chunk_content*.

    Returns:
        Header-prefixed content, or original content for non-target types.
    """
    if memory_type not in CONTEXTUAL_HEADER_MEMORY_TYPES:
        return chunk_content

    date = resolve_chunk_date(file_path, frontmatter)
    title = resolve_file_title(file_path, body, frontmatter)
    if heading_path is None:
        heading_path = extract_heading_path(chunk_content)
    header = build_contextual_chunk_header(
        date=date,
        file_title=title,
        heading_path=heading_path,
    )
    return f"{header}\n{chunk_content}"
