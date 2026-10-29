"""Markdown section splitting for stable heading-level translation reuse."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    """A source section preserved as an indivisible translation unit."""

    text: str
    kind: str = "markdown"


_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+", re.MULTILINE)
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _frontmatter_end(lines: list[str]) -> int | None:
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") in {"---", "..."}:
            return index + 1
    return None


def split_markdown(text: str) -> list[Segment]:
    """Split frontmatter and Markdown at ATX headings outside fenced blocks."""
    if not text:
        return []

    lines = text.splitlines(keepends=True)
    segments: list[Segment] = []
    frontmatter_end = _frontmatter_end(lines)
    start_line = 0
    if frontmatter_end is not None:
        segments.append(Segment("".join(lines[:frontmatter_end]), "frontmatter"))
        start_line = frontmatter_end

    body_lines = lines[start_line:]
    section_starts: list[int] = []
    fence_char: str | None = None
    fence_length = 0

    for index, line in enumerate(body_lines):
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            fence = fence_match.group(1)
            char = fence[0]
            if fence_char is None:
                fence_char = char
                fence_length = len(fence)
            elif char == fence_char and len(fence) >= fence_length:
                fence_char = None
                fence_length = 0
            continue
        if fence_char is None and _HEADING_RE.match(line):
            section_starts.append(index)

    boundaries = [0, *section_starts, len(body_lines)]
    for left, right in zip(boundaries, boundaries[1:], strict=False):
        chunk = "".join(body_lines[left:right])
        if chunk:
            segments.append(Segment(chunk, "markdown"))

    return segments


def join_segments(segments: list[Segment] | tuple[Segment, ...]) -> str:
    """Reassemble segments without altering their original boundaries."""
    return "".join(segment.text for segment in segments)
