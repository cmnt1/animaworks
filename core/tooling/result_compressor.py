from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Tool result compression for token savings.

Applies tool-specific compression rules to reduce token consumption
when feeding tool results back to the LLM. Inspired by RTK's approach
of command-specific filters with safe fallback.
"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Minimum fraction of original content to preserve (safety floor)
_MIN_PRESERVE_RATIO = 0.20


def compress_tool_result(tool_name: str, result: str) -> tuple[str, int]:
    """Compress a tool result string based on tool-specific rules.

    Returns (compressed_result, bytes_saved). Never raises — falls back
    to the original result on any error.
    """
    if not result:
        return result, 0

    original_size = len(result.encode("utf-8"))
    min_size = int(original_size * _MIN_PRESERVE_RATIO)

    try:
        compressor = _COMPRESSORS.get(tool_name)
        if compressor is None:
            # Try prefix match for tools like gmail_inbox, github_issues, etc.
            for prefix, fn in _PREFIX_COMPRESSORS.items():
                if tool_name.startswith(prefix):
                    compressor = fn
                    break

        if compressor is None:
            # Generic JSON compression for unknown tools
            compressed = _compress_generic_json(result)
        else:
            compressed = compressor(result)

        if compressed is None or compressed == result:
            return result, 0

        compressed_size = len(compressed.encode("utf-8"))

        # Safety floor: never compress below minimum
        if compressed_size < min_size:
            return result, 0

        saved = original_size - compressed_size
        if saved <= 0:
            return result, 0

        logger.debug(
            "Compressed %s: %d → %d bytes (-%d%%)",
            tool_name,
            original_size,
            compressed_size,
            int(saved * 100 / original_size),
        )
        return compressed, saved

    except Exception:
        logger.debug("Compression failed for %s, using original", tool_name, exc_info=True)
        return result, 0


# ── Tool-specific compressors ────────────────────────────────


def _compress_web_search(result: str) -> str | None:
    """Compress web search results: strip HTML, limit snippets."""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", result)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Remove common boilerplate patterns
    text = re.sub(
        r"(?:Cookie|Privacy|Terms of Service|Accept All).*?(?:\.|$)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return text if text != result else None


def _compress_x_search(result: str) -> str | None:
    """Compress X/Twitter search results."""
    return _compress_web_search(result)


def _compress_gmail(result: str) -> str | None:
    """Compress Gmail results: summarize headers, strip quotes/signatures."""
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return _strip_email_quotes(result)

    if isinstance(data, list):
        compressed = []
        for item in data:
            if isinstance(item, dict):
                compressed.append(_summarize_email(item))
            else:
                compressed.append(item)
        return json.dumps(compressed, ensure_ascii=False, indent=1)
    elif isinstance(data, dict):
        return json.dumps(_summarize_email(data), ensure_ascii=False, indent=1)
    return None


def _summarize_email(email: dict[str, Any]) -> dict[str, Any]:
    """Extract key fields from an email dict."""
    summary: dict[str, Any] = {}
    for key in ("from", "to", "subject", "date", "id", "message_id", "snippet"):
        if key in email:
            summary[key] = email[key]
    body = email.get("body", "")
    if isinstance(body, str) and len(body) > 1000:
        body = _strip_email_quotes(body[:1000]) + "\n[...]"
    if body:
        summary["body"] = body
    return summary


def _strip_email_quotes(text: str) -> str:
    """Remove quoted email chains and signatures."""
    # Remove lines starting with > (quoted text)
    lines = text.split("\n")
    filtered = []
    sig_found = False
    for line in lines:
        if line.strip().startswith(">"):
            continue
        if re.match(r"^[-_]{2,}\s*$", line.strip()):
            sig_found = True
        if sig_found:
            continue
        if re.match(r"^On .+ wrote:$", line.strip()):
            break
        filtered.append(line)
    return "\n".join(filtered)


def _compress_github(result: str) -> str | None:
    """Compress GitHub results: simplify metadata, trim diffs."""
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        # Plain text diff — compress unchanged lines
        return _compress_diff_text(result)

    if isinstance(data, dict):
        return json.dumps(
            _strip_null_fields(data),
            ensure_ascii=False,
            indent=1,
        )
    elif isinstance(data, list):
        # Limit array length
        truncated = data[:50] if len(data) > 50 else data
        cleaned = [_strip_null_fields(item) if isinstance(item, dict) else item for item in truncated]
        result_str = json.dumps(cleaned, ensure_ascii=False, indent=1)
        if len(data) > 50:
            result_str += f"\n[... {len(data) - 50} more items truncated]"
        return result_str
    return None


def _compress_diff_text(text: str) -> str | None:
    """Compress unified diff by collapsing unchanged context."""
    lines = text.split("\n")
    if not any(line.startswith(("+++", "---", "@@")) for line in lines[:20]):
        return None  # Not a diff

    compressed: list[str] = []
    context_count = 0
    for line in lines:
        if line.startswith(("+", "-", "@@", "diff ", "index ")):
            if context_count > 6:
                compressed.append(f"  [...{context_count - 6} unchanged lines...]")
            context_count = 0
            compressed.append(line)
        else:
            context_count += 1
            if context_count <= 3:
                compressed.append(line)

    if context_count > 6:
        compressed.append(f"  [...{context_count - 6} unchanged lines...]")

    result = "\n".join(compressed)
    return result if result != text else None


def _compress_aws(result: str) -> str | None:
    """Compress AWS results: limit arrays, strip null fields."""
    return _compress_generic_json(result)


def _compress_generic_json(result: str) -> str | None:
    """Generic JSON compression: strip nulls, limit arrays, compact."""
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return None

    cleaned = _deep_clean_json(data)
    compressed = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))

    return compressed if compressed != result else None


def _deep_clean_json(obj: Any, depth: int = 0, max_depth: int = 8) -> Any:
    """Recursively clean JSON: remove nulls/empty, limit arrays, cap depth."""
    if depth >= max_depth:
        if isinstance(obj, (dict, list)):
            return "[...]"
        return obj

    if isinstance(obj, dict):
        return {
            k: _deep_clean_json(v, depth + 1, max_depth)
            for k, v in obj.items()
            if v is not None and v != "" and v != []
        }
    elif isinstance(obj, list):
        cleaned = [_deep_clean_json(item, depth + 1, max_depth) for item in obj[:30]]
        if len(obj) > 30:
            cleaned.append(f"... {len(obj) - 30} more items")
        return cleaned
    return obj


def _strip_null_fields(d: dict[str, Any]) -> dict[str, Any]:
    """Remove None/empty values from a dict (shallow)."""
    return {k: v for k, v in d.items() if v is not None and v != "" and v != []}


# ── Compressor registry ──────────────────────────────────────

_COMPRESSORS: dict[str, Any] = {
    "web_search": _compress_web_search,
    "x_search": _compress_x_search,
}

_PREFIX_COMPRESSORS: dict[str, Any] = {
    "gmail": _compress_gmail,
    "github": _compress_github,
    "aws": _compress_aws,
}
