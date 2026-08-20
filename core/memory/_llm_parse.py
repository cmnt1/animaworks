# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Shared LLM-output parsing helpers for the memory pipeline.

Memory paths parse LLM output in several places. Historically each rolled its
own markdown-fence stripping (language-tag dependent), ``json.loads``, and a
Japanese-only heading pattern, and failures tended to be *silent* (empty list
/ not written).

This module centralises the multi-stage defense recommended for ``memory``:

  1. Language-agnostic outer code-fence stripping (````` ```json``,
     `` ```markdown``, any tag, or a bare fence).
  2. ``json.loads``.
  3. ``json_repair`` for broken-looking JSON (trailing commas, unquoted keys).
  4. A warning log and ``None`` / marker return so callers can detect a
     zero-item result instead of silently dropping memory.

It also carries the single source of truth for locale-aware section/field
headings (ja + en), so the parsers below all accept both template sets and a
change on one side alone can't silently drift the other into a mismatch.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ── Code-fence stripping ────────────────────────────────────────────────


def strip_code_fence(text: str) -> str:
    """Strip one outer Markdown code-fence wrapper (language-agnostic).

    Removes a single leading fence line (````` ```lang``) and a single
    trailing fence line (````` `````) around the whole response, so any
    language tag (``json``, ``markdown``, ``md``, …) or a bare fence is
    accepted. Intentional interior code blocks are preserved.

    Args:
        text: Raw LLM output.

    Returns:
        Cleaned text with the outer wrapper fence removed.
    """
    if not text:
        return text
    s = text.strip()
    if not s.startswith("```"):
        return s
    nl = s.find("\n")
    if nl == -1:
        # The entire (non-empty) line is an open fence; nothing else left.
        return ""
    body = s[nl + 1 :].rstrip()
    if body.endswith("```"):
        body = body[:-3].rstrip()
    return body


# Language-agnostic fence search for extracting a fenced JSON block that may
# be embedded in surrounding prose (falls back when the whole output is not a
# single wrapped block).
_FENCE_BLOCK_RE = re.compile(r"```[a-zA-Z0-9_\-]*\s*\n(.*?)```", re.DOTALL)


def extract_fenced_block(text: str) -> str | None:
    """Return the content of the first fenced code block, if any.

    Unlike :func:`strip_code_fence` (which expects a whole-value wrapper),
    this finds a fence anywhere in the text.  Returns ``None`` when no
    fence is present.
    """
    if not text:
        return None
    m = _FENCE_BLOCK_RE.search(text.strip())
    if m:
        return m.group(1).strip()
    return None


# ── Robust JSON loading ────────────────────────────────────────────────


def load_json(text: str | None, *, context: str = "LLM output") -> Any:
    """Best-effort JSON parsing with multi-stage recovery.

    Tries ``json.loads`` (after stripping any outer code fence), then
    ``json_repair`` for broken-looking JSON.  Logs a warning and returns
    ``None`` only when both fail, so callers can detect a zero-item result
    instead of a silent drop.

    Args:
        text: Raw LLM output (possibly fenced / broken JSON).
        context: Label included in the warning log to identify the caller.

    Returns:
        Parsed value, or ``None`` when unparseable.
    """
    if text is None or not str(text).strip():
        logger.warning("Empty %s (nothing to parse)", context)
        return None

    body = strip_code_fence(str(text))
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError):
        pass

    try:
        from json_repair import repair_json

        repaired = repair_json(body)
        if repaired is not None:
            return json.loads(str(repaired))
    except Exception:
        logger.debug("json_repair failed for %s", context, exc_info=True)

    logger.warning(
        "Failed to parse %s as JSON (%.80s); returning empty result",
        context,
        body,
    )
    return None


# ── Locale-aware heading / field tables (single source of truth) ──────

# Alternative regex fragments for the same logical section, covering the
# ja template headings and the en (and ko) template headings.
_SECTION_ALTERNATIVES = {
    "knowledge": ("knowledge抽出", r"knowledge\s*extraction"),
    "procedure": ("procedure抽出", r"procedure\s*extraction"),
}

# "nothing here" markers across locales.
NONE_MARKERS = (
    "(なし)",
    "(none)",
    "(None)",
    "(없음)",
    "(N/A)",
    "(n/a)",
    "なし",
    "없음",
    "none",
    "None",
)


def _alt(parts: tuple[str, ...]) -> str:
    return "(?:" + "|".join(parts) + ")"


def _section_pattern(key: str) -> str:
    return _alt(_SECTION_ALTERNATIVES[key])


# Item field labels used by classification / procedure_from_resolved.
KNOWLEDGE_FIELDS = {
    "filename": _alt(("ファイル名", "Filename")),
    "content": _alt(("内容", "Content")),
}
PROCEDURE_FIELDS = {
    "filename": _alt(("ファイル名", "Filename")),
    "description": "description",
    "tags": "tags",
    "content": _alt(("内容", "Content")),
}

# Section / sub-section headings used by the session summary template.
SESSION_HEADINGS = {
    "episode": _alt(("エピソード要約", "Episode Summary")),
    "state_change": _alt(("ステート変更", "State Changes")),
    "resolved": _alt(("解決済み", "Resolved")),
    "new_tasks": _alt(("新規タスク", "New Tasks")),
    "current_state": _alt(("現在の状態", "Current State")),
}
# Special values treated as "no content" in session summary lists.
SESSION_NONE_VALUES = ("なし", "none", "None", "(なし)", "(none)", "(없음)")


def is_none_marker(text: str) -> bool:
    """Return True if a section body is only a "no items" marker."""
    stripped = text.strip()
    if stripped in NONE_MARKERS:
        return True
    # ASCII variants are compared case-insensitively (CJK markers are exact).
    lowered = stripped.lower()
    return lowered in {"(none)", "none", "(n/a)", "(없음)"}
