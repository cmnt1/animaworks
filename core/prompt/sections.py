from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Section loading and DK entry summary extraction for prompt building."""

from core.paths import load_prompt

_SUMMARY_MAX_CHARS = 200


def _parse_kv_template(raw: str) -> dict[str, str]:
    """Parse ``[key]: value`` lines from a template string.

    Only the first ``]: `` occurrence per line is used as delimiter,
    so values may safely contain ``]: ``.
    """
    result: dict[str, str] = {}
    for line in raw.strip().splitlines():
        if not line.startswith("["):
            continue
        bracket_end = line.find("]")
        if bracket_end < 0:
            continue
        sep = line.find("]: ", bracket_end)
        if sep < 0:
            continue
        key = line[1:bracket_end]
        value = line[sep + 3 :]
        result[key] = value
    return result


def _load_section_strings(locale: str | None = None) -> dict[str, str]:
    """Load section headers and labels from template."""
    try:
        raw = load_prompt("builder/sections", locale=locale)
    except FileNotFoundError:
        return {}
    return _parse_kv_template(raw)


def _load_fallback_strings(locale: str | None = None) -> dict[str, str]:
    """Load fallback/placeholder texts from template."""
    try:
        raw = load_prompt("builder/fallbacks", locale=locale)
    except FileNotFoundError:
        return {}
    return _parse_kv_template(raw)


def _extract_entry_summary(entry: dict) -> str:
    """Extract a 1-line summary for a DK entry.

    Priority: frontmatter ``description`` → first ATX heading →
    first non-empty, non-heading line → file name with hyphens replaced.
    Result is capped at :data:`_SUMMARY_MAX_CHARS`.
    """
    desc = (entry.get("description") or "").strip()
    if desc:
        return desc[:_SUMMARY_MAX_CHARS]
    content = entry.get("content") or ""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                return heading[:_SUMMARY_MAX_CHARS]
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
            return stripped[:_SUMMARY_MAX_CHARS]
    return (entry.get("name") or "").replace("-", " ").replace("_", " ")
