# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Markdown-to-Chatwork format conversion utilities."""

from __future__ import annotations

import re


def clean_chatwork_tags(text: str) -> str:
    """Remove Chatwork special tags to make text more readable."""
    text = re.sub(r"\[To:\d+\][^\n]*\n?", "", text)
    text = re.sub(r"\[toall\]", "", text)
    text = re.sub(r"\[info\].*?\[/info\]", "[info block]", text, flags=re.DOTALL)
    text = re.sub(r"\[/?[a-z_]+\]", "", text)
    return text.strip()


def md_to_chatwork(text: str) -> str:
    """Convert standard Markdown to Chatwork format.

    Protects existing Chatwork tags, code blocks, and inline code via placeholders,
    then applies Markdown-to-Chatwork conversions, and finally restores placeholders.
    """
    if not text:
        return ""

    text = text.replace("\x00", "")

    _placeholders: list[str] = []

    def _save(matched_text: str) -> str:
        _placeholders.append(matched_text)
        return f"\x00PH{len(_placeholders) - 1}\x00"

    def _save_code_block(match: re.Match[str]) -> str:
        full = match.group(0)
        lines = full.split("\n")
        if len(lines) >= 2:
            start = 1
            if len(lines) >= 3 and re.match(r"^[a-zA-Z0-9+#-]+$", lines[1].strip()):
                start = 2
            content = "\n".join(lines[start:-1])
        else:
            content = full.replace("```", "").strip()
        converted = f"[code]{content}[/code]"
        _placeholders.append(converted)
        return f"\x00PH{len(_placeholders) - 1}\x00"

    # ── Protect existing CW tags (as-is) ──
    text = re.sub(r"\[info\].*?\[/info\]", lambda m: _save(m.group(0)), text, flags=re.DOTALL)
    text = re.sub(r"\[code\].*?\[/code\]", lambda m: _save(m.group(0)), text, flags=re.DOTALL)
    text = re.sub(r"\[qt\].*?\[/qt\]", lambda m: _save(m.group(0)), text, flags=re.DOTALL)
    text = re.sub(r"\[url[^\]]*\].*?\[/url\]", lambda m: _save(m.group(0)), text, flags=re.DOTALL)
    text = re.sub(r"\[hr\]", lambda m: _save(m.group(0)), text)
    text = re.sub(r"\[To:\d+\]", lambda m: _save(m.group(0)), text)
    text = re.sub(r"\[rp[^\]]*\]", lambda m: _save(m.group(0)), text)
    text = re.sub(r"\[picon:\d+\]", lambda m: _save(m.group(0)), text)
    text = re.sub(r"\[pname:\d+\]", lambda m: _save(m.group(0)), text)
    text = re.sub(r"\[piconname:\d+\]", lambda m: _save(m.group(0)), text)
    text = re.sub(r"\[toall\]", lambda m: _save(m.group(0)), text)

    # ── Protect fenced code blocks → [code]...[/code] ──
    text = re.sub(r"```[\s\S]*?```", _save_code_block, text)

    # ── Protect inline code ──
    text = re.sub(r"`[^`]+`", lambda m: _save(m.group(0)), text)

    # ── Images: ![alt](url) → url ──
    text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\2", text)

    # ── Links: [text](url) → text ( url ) ──
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 ( \2 )", text)

    # ── Headers: # Heading → [info][title]Heading[/title][/info] ──
    text = re.sub(
        r"^#{1,6}\s+(.+)$",
        r"[info][title]\1[/title][/info]",
        text,
        flags=re.MULTILINE,
    )

    # ── Bold+Italic: ***text*** → text only ──
    text = re.sub(r"\*{3}(.+?)\*{3}", r"\1", text)

    # ── Bold: **text** → text only ──
    text = re.sub(r"\*{2}(.+?)\*{2}", r"\1", text)

    # ── Italic: *text* → text only (avoid "* " bullet) ──
    text = re.sub(r"(?<![*])\*(?![* ])(.+?)(?<![* ])\*(?![*])", r"\1", text)

    # ── Strikethrough: ~~text~~ → text only ──
    text = re.sub(r"~~(.+?)~~", r"\1", text)

    # ── Horizontal rules: --- / *** / ___ (3+ chars) → [hr] ──
    text = re.sub(r"^[-*_]{3,}\s*$", "[hr]", text, flags=re.MULTILINE)

    # ── Blockquotes: consecutive "> " lines → [qt]...[/qt] ──
    lines = text.split("\n")
    out_lines: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("> "):
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith("> "):
                quote_lines.append(re.sub(r"^>\s*", "", lines[i].strip()))
                i += 1
            combined = "\n".join(quote_lines)
            out_lines.append(f"[qt]{combined}[/qt]")
            continue
        out_lines.append(line)
        i += 1
    text = "\n".join(out_lines)

    # ── MD tables → list format ──
    lines = text.split("\n")
    out_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if re.match(r"^\|.+\|$", line.strip()):
            header_line = line
            header_cells = [c.strip() for c in header_line.split("|")[1:-1]]
            if not header_cells:
                out_lines.append(header_line)
                i += 1
                continue
            if i + 1 >= len(lines) or not re.match(r"^\|[-|\s:]+\|$", lines[i + 1].strip()):
                out_lines.append(header_line)
                i += 1
                continue
            i += 2
            has_data = False
            while i < len(lines) and re.match(r"^\|.+\|$", lines[i].strip()):
                row_line = lines[i]
                if re.match(r"^\|[-|\s:]+\|$", row_line.strip()):
                    i += 1
                    continue
                cells = [c.strip() for c in row_line.split("|")[1:-1]]
                if cells:
                    parts = [f"{h}: {v}" for h, v in zip(header_cells, cells, strict=False)]
                    out_lines.append("• " + " | ".join(parts))
                    has_data = True
                i += 1
            if not has_data:
                out_lines.append(header_line)
            continue
        out_lines.append(line)
        i += 1
    text = "\n".join(out_lines)

    # ── Restore placeholders ──
    for idx, ph in enumerate(_placeholders):
        text = text.replace(f"\x00PH{idx}\x00", ph)

    return text
