from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Pure helpers for splitting long text into atomic-fact-extraction chunks.

Used by consolidation so that very large merged episode summaries are not
sent to the LLM in a single call (which could run out of output tokens or
time out). Chunking is purely character based; boundaries are preferred at
markdown heading lines, then blank lines, then plain newlines, falling
back to a hard cut at the size limit.
"""

import re

_HEADING_BOUNDARY_RE = re.compile(r"\n#")
_BLANK_LINE_BOUNDARY_RE = re.compile(r"\n\n")


def split_text_for_fact_extraction(text: str, max_chars: int) -> list[str]:
    """Split ``text`` into chunks each at most ``max_chars`` characters.

    Boundaries are chosen, in priority order, at heading lines (lines
    starting with ``#``), blank lines, then newlines; when none are found
    the text is cut at ``max_chars``. Concatenating the returned chunks
    reproduces the original text exactly.

    ``max_chars <= 0`` disables splitting (returns ``[text]``). Empty text
    returns an empty list.
    """
    if max_chars <= 0:
        return [text]
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    total = len(text)
    while start < total:
        end = start + max_chars
        if end >= total:
            chunks.append(text[start:])
            break
        boundary = _find_break_boundary(text, start, end)
        if boundary <= start:
            boundary = end
        chunks.append(text[start:boundary])
        start = boundary
    return chunks


def _find_break_boundary(text: str, start: int, end: int) -> int:
    """Return the best break position within ``text[start:end]``.

    Prefers (in order) the last heading-line boundary, the last blank-line
    boundary, and the last newline boundary. Returns ``end`` when no
    boundary is found before the limit.
    """
    region = text[start:end]
    # Only accept boundaries in the back half so a heading near the start of
    # the window cannot produce a run of tiny chunks.
    min_offset = len(region) // 2

    # 1) Heading line: end the chunk right before a '#'-prefixed line.
    match = None
    for m in reversed(list(_HEADING_BOUNDARY_RE.finditer(region))):
        if m.start() >= min_offset:
            match = m
        break
    if match is not None:
        return start + match.start() + 1

    # 2) Blank line: end right after an empty line.
    match = None
    for m in reversed(list(_BLANK_LINE_BOUNDARY_RE.finditer(region))):
        if m.start() >= min_offset:
            match = m
        break
    if match is not None:
        return start + match.start() + 2

    # 3) Plain newline.
    idx = region.rfind("\n")
    if idx >= min_offset:
        return start + idx + 1

    return end
