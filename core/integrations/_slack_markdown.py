# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Slack markdown conversion and formatting utilities."""

from __future__ import annotations

import re
from datetime import datetime

from core.integrations._slack_client import JST


def format_slack_ts(ts: str) -> str:
    """Convert a Slack timestamp (e.g. '1707123456.789012') to JST datetime string."""
    try:
        epoch = float(ts)
        dt = datetime.fromtimestamp(epoch, tz=JST)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return ts


def md_to_slack_mrkdwn(text: str) -> str:
    """Convert standard Markdown to Slack mrkdwn format.

    Handles:
    - **bold** → *bold*
    - *italic* → _italic_
    - ***bold italic*** → *_bold italic_*
    - ~~strikethrough~~ → ~strikethrough~
    - [text](url) → <url|text>
    - ![alt](url) → <url>
    - # Heading → *Heading*
    - Bullet lists (- / *) → • item
    - Horizontal rules (---) → ───────────────
    - Code blocks and inline code are preserved as-is.
    """
    if not text:
        return ""

    # ── Protect code blocks / inline code from conversion ──
    _placeholders: list[str] = []

    def _save(matched_text: str) -> str:
        _placeholders.append(matched_text)
        return f"\x00PH{len(_placeholders) - 1}\x00"

    # Fenced code blocks (``` ... ```)
    text = re.sub(r"```[\s\S]*?```", lambda m: _save(m.group(0)), text)
    # Inline code (` ... `)
    text = re.sub(r"`[^`]+`", lambda m: _save(m.group(0)), text)

    # ── Images: ![alt](url) → <url> ──
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"<\2>", text)

    # ── Links: [text](url) → <url|text> ──
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<\2|\1>", text)

    # ── Headers: # Heading → *Heading* (protect from italic pass) ──
    text = re.sub(
        r"^#{1,6}\s+(.+)$",
        lambda m: _save(f"*{m.group(1)}*"),
        text,
        flags=re.MULTILINE,
    )

    # ── Bold+Italic: ***text*** → *_text_* ──
    text = re.sub(
        r"\*{3}(.+?)\*{3}",
        lambda m: _save(f"*_{m.group(1)}_*"),
        text,
    )

    # ── Bold: **text** → *text* (protect from italic pass) ──
    text = re.sub(
        r"\*{2}(.+?)\*{2}",
        lambda m: _save(f"*{m.group(1)}*"),
        text,
    )

    # ── Italic: *text* → _text_ ──
    # Avoid matching ** (already handled) and "* " (bullet list).
    text = re.sub(r"(?<![*])\*(?![* ])(.+?)(?<![* ])\*(?![*])", r"_\1_", text)

    # ── Strikethrough: ~~text~~ → ~text~ ──
    text = re.sub(r"~~(.+?)~~", r"~\1~", text)

    # ── Bullet lists: - item / * item → • item ──
    text = re.sub(r"^(\s*)[-*]\s+", r"\1• ", text, flags=re.MULTILINE)

    # ── Horizontal rules: --- / *** / ___ → ─────────────── ──
    text = re.sub(r"^[-*_]{3,}\s*$", "───────────────", text, flags=re.MULTILINE)

    # ── Restore placeholders ──
    for i, ph in enumerate(_placeholders):
        text = text.replace(f"\x00PH{i}\x00", ph)

    return text


def taskboard_md_to_slack(md_text: str) -> str:
    """Convert task-board.md to Slack-optimised mrkdwn.

    Markdown tables are converted to bullet-list format for readability
    in Slack.  Sections after "✅ 今週完了" are replaced with a short
    footer pointing readers to the source file.
    """
    lines = md_text.strip().split("\n")
    out: list[str] = []
    in_completed = False

    i = 0
    while i < len(lines):
        line = lines[i]

        if "✅ 今週完了" in line or "✅ Completed" in line:
            in_completed = True
            i += 1
            continue
        if in_completed:
            i += 1
            continue

        # Table separator rows
        if re.match(r"^\|[-|\s:]+\|$", line.strip()):
            i += 1
            continue

        # Table header rows
        if re.match(r"^\|\s*#\s*\|", line.strip()) or re.match(r"^\|\s*(タスク|Task)\s*\|", line.strip()):
            i += 1
            continue
        if re.match(r"^\|\s*(KR|#)\s*\|", line.strip()):
            i += 1
            continue

        # Table data rows → bullet items
        if line.strip().startswith("|") and line.strip().endswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            cells = [c for c in cells if c and c != "—"]
            if cells:
                tag = cells[0]
                rest = cells[1:]
                if len(rest) >= 2:
                    task = rest[0]
                    owner = rest[1]
                    extras = [x for x in rest[2:] if x]
                    suffix = ""
                    if extras:
                        suffix = " | " + " | ".join(extras)
                    out.append(f"  • {tag}: {task}（{owner}）{suffix}")
                else:
                    out.append(f"  • {' | '.join(cells)}")
            i += 1
            continue

        # Horizontal rules
        if re.match(r"^-{3,}\s*$", line.strip()):
            out.append("")
            i += 1
            continue

        # Section headers
        m = re.match(r"^#{1,3}\s+(.+)$", line)
        if m:
            out.append(f"*{m.group(1)}*")
            i += 1
            continue

        converted = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)
        out.append(converted)
        i += 1

    out.append("")
    out.append("_Full board: `shared/task-board.md`_")
    return "\n".join(out)


def clean_slack_markup(text: str, cache: dict | None = None) -> str:
    """Convert Slack markup to readable plain text.

    - <@U123ABC> -> @display_name (resolved via cache if available)
    - <#C123ABC|channel-name> -> #channel-name
    - <#C123ABC> -> #C123ABC
    - <https://example.com|Example> -> Example (https://example.com)
    - <https://example.com> -> https://example.com
    - &amp; -> &, &lt; -> <, &gt; -> >
    """
    if not text:
        return ""

    # User mentions: <@U0TEST000001>
    def replace_user_mention(m):
        user_id = m.group(1)
        if cache and user_id in cache:
            return f"@{cache[user_id]}"
        return f"@{user_id}"

    text = re.sub(r"<@(U[A-Z0-9]+)>", replace_user_mention, text)

    # Channel references: <#C123|name> or <#C123>
    def replace_channel_ref(m):
        channel_id = m.group(1)
        name = m.group(2)
        if name:
            return f"#{name}"
        return f"#{channel_id}"

    text = re.sub(r"<#(C[A-Z0-9]+)(?:\|([^>]*))?>", replace_channel_ref, text)

    # URL links: <URL|label> or <URL>
    def replace_url(m):
        url = m.group(1)
        label = m.group(2)
        if label:
            return f"{label} ({url})"
        return url

    text = re.sub(r"<(https?://[^|>]+)(?:\|([^>]*))?>", replace_url, text)

    # Remaining <...> tags (mailto, etc.)
    text = re.sub(r"<([^>]+)>", r"\1", text)

    # HTML entities
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")

    return text


def truncate(s: str, length: int = 80) -> str:
    """Truncate a string, replacing newlines with spaces."""
    s = s.replace("\n", " ").strip()
    return s[:length] + "..." if len(s) > length else s
