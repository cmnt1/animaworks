from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Shared interpretation helpers for activity-log entries.

Centralises the *parsing* of activity entries so callers (priming,
conversation view, timeline, compaction, audit, search, health,
distillation) need not re-implement it: reading (:func:`iter_entries`),
display text (:func:`entry_text`), conversation role
(:func:`entry_role`), ``tool_use``⇄``tool_result`` pairing
(:func:`pair_tool_events`), truncation (:func:`clip`) and the canonical
event-type sets (:data:`EVENT_SETS`).  Priming rendering lives in
:class:`PrimingMixin`.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.i18n import t
from core.memory.activity.models import (
    CHARS_PER_TOKEN,
    ActivityEntry,
    EntryGroup,
    dm_label,
    find_tool_result_fallback,
    get_peer,
    get_task_name,
    set_source_lines,
    time_diff,
)


class EntryRole:
    """Canonical conversation roles used across activity consumers."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


#: Recurring “which event types count” sets shared by consumers.
EVENT_SETS: dict[str, frozenset[str]] = {
    # Timeline-view / audit-style report set (excludes raw tool pairs).
    "audit": frozenset(
        {
            "heartbeat_end",
            "heartbeat_reflection",
            "response_sent",
            "cron_executed",
            "tool_use",
            "message_sent",
            "task_exec_end",
            "issue_resolved",
            "error",
        }
    ),
    # Conversation-view set: everything rendered as a timeline message.
    "chat": frozenset(
        {
            "message_received",
            "message_sent",
            "response_sent",
            "tool_use",
            "tool_result",
            "heartbeat_start",
            "heartbeat_end",
            "cron_executed",
            "task_exec_start",
            "task_exec_end",
            "error",
            "human_notify",
            "human_reply",
        }
    ),
    # Idle-compaction context set (session summary extraction).
    "compaction": frozenset(
        {
            "message_received",
            "response_sent",
            "tool_use",
            "tool_result",
        }
    ),
}


def _field(entry: ActivityEntry | dict[str, Any], name: str) -> str:
    """Return entry field *name* as a string (works for dicts too)."""
    if isinstance(entry, dict):
        return entry.get(name) or ""
    return getattr(entry, name) or ""


def entry_text(
    entry: ActivityEntry | dict[str, Any],
    prefer: str = "content",
) -> str:
    """Display text of *entry* (content preferred; pass ``prefer="summary"`` for the reverse)."""
    content = _field(entry, "content")
    summary = _field(entry, "summary")
    if prefer == "summary":
        return summary or content
    return content or summary


def entry_role(entry: ActivityEntry, self_name: str = "") -> str | None:
    """Conversation role of *entry* (user/assistant/system/tool), or ``None``."""
    etype = entry.type

    if etype in ("response_sent", "message_sent", "dm_sent"):
        return EntryRole.ASSISTANT
    if etype in ("message_received", "dm_received"):
        if entry.meta.get("from_type") == "anima":
            return EntryRole.ASSISTANT
        if self_name and (entry.from_person or "") == self_name:
            return EntryRole.ASSISTANT
        return EntryRole.USER
    if etype == "human_reply":
        return EntryRole.USER
    if etype == "human_notify":
        return EntryRole.SYSTEM
    if etype in (
        "heartbeat_start",
        "heartbeat_end",
        "cron_executed",
        "task_exec_start",
        "task_exec_end",
        "error",
    ):
        return EntryRole.SYSTEM
    if etype in ("tool_use", "tool_result"):
        return EntryRole.TOOL
    return None


def clip(text: str, limit: int) -> str:
    """Truncate *text* to *limit* chars (matching the inline ``text[:limit]`` pattern)."""
    if limit <= 0:
        return ""
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit]


@dataclass
class ToolExchange:
    """A ``tool_use`` entry and its matched ``tool_result`` (if any)."""

    tool_use: ActivityEntry
    result: ActivityEntry | None


def pair_tool_events(entries: list[ActivityEntry]) -> list[ToolExchange]:
    """Pair each ``tool_use`` entry with its ``tool_result`` (by id, else proximity)."""
    result_by_id: dict[str, ActivityEntry] = {}
    for e in entries:
        if e.type == "tool_result":
            tid = e.meta.get("tool_use_id", "")
            if tid:
                result_by_id[tid] = e

    exchanges: list[ToolExchange] = []
    for e in entries:
        if e.type != "tool_use":
            continue
        tid = e.meta.get("tool_use_id", "")
        result = result_by_id.get(tid) if tid else None
        if not result:
            result = find_tool_result_fallback(entries, e)
        exchanges.append(ToolExchange(tool_use=e, result=result))
    return exchanges


def iter_entries(
    anima_dir: Path,
    *,
    days: int = 2,
    since: datetime | None = None,
    types: list[str] | None = None,
    involving: str | None = None,
    limit: int = 10000,
) -> Iterator[ActivityEntry]:
    """Yield chronological activity entries through :class:`ActivityLogger`.

    Centralises JSONL reading so callers need not open ``activity_log/*.jsonl``
    themselves.  Args mirror :meth:`ActivityLogger.recent`.
    """
    from core.memory.activity.logger import ActivityLogger

    logger = ActivityLogger(anima_dir)
    entries = logger.recent(
        days=days,
        types=types,
        involving=involving,
        limit=limit,
    )
    if since is not None:
        entries = [e for e in entries if _ts_ge(e.ts, since)]
    yield from entries


def _ts_ge(ts: str, since: datetime) -> bool:
    try:
        from core.time_utils import ensure_aware

        val = datetime.fromisoformat(ts)
        if val.tzinfo is None and since.tzinfo is not None:
            val = val.replace(tzinfo=since.tzinfo)
        return ensure_aware(val) >= ensure_aware(since)
    except Exception:
        return False


# ── Priming formatting ──────────────────────────────────────


class PrimingMixin:
    """Mixin providing priming format methods for ActivityLogger."""

    def format_for_priming(
        self,
        entries: list[ActivityEntry],
        budget_tokens: int = 1300,
        content_trim: int = 200,
    ) -> str:
        """Render activity entries as a compact, budget-limited timeline."""
        if not entries:
            return ""

        groups = self._group_entries(entries)
        max_chars = budget_tokens * CHARS_PER_TOKEN
        lines: list[str] = []
        total_chars = 0

        for group in reversed(groups):
            formatted = self._format_group(group, content_trim=content_trim)
            if total_chars + len(formatted) + 1 > max_chars:
                break
            lines.append(formatted)
            total_chars += len(formatted) + 1

        if not lines:
            return ""

        lines.reverse()
        return "\n".join(lines)

    @staticmethod
    def _format_entry(entry: ActivityEntry, content_trim: int = 200) -> str:
        """Format a single entry as a concise timeline line."""
        ts = entry.ts[11:16] if len(entry.ts) >= 16 else entry.ts

        if entry.type == "heartbeat_end":
            reflection_line = PrimingMixin._format_heartbeat_reflection(entry, ts)
            if reflection_line:
                return reflection_line
        if entry.type == "tool_result":
            return PrimingMixin._format_tool_result_entry(entry, ts)
        if entry.type == "human_notify":
            return PrimingMixin._format_human_notify_entry(entry, ts)

        text = entry_text(entry, prefer="summary")

        if content_trim > 0 and len(text) > content_trim:
            date_str = entry.ts[:10] if len(entry.ts) >= 10 else "unknown"
            pointer = f"\n  -> activity_log/{date_str}.jsonl"
            trim_window = text[:content_trim]
            last_boundary = max(
                trim_window.rfind("\u3002"),
                trim_window.rfind("\n"),
                trim_window.rfind(". "),
            )
            if last_boundary > content_trim * 0.5:
                text = trim_window[: last_boundary + 1] + pointer
            else:
                text = trim_window[: max(1, content_trim - 20)] + "..." + pointer

        type_map: dict[str, str] = {
            "message_received": "MSG<",
            "message_sent": "MSG>",
            "response_sent": "RESP>",
            "channel_read": "CH.R",
            "channel_post": "CH.W",
            "dm_received": "MSG<",
            "dm_sent": "MSG>",
            "human_notify": "NTFY",
            "tool_use": "TOOL",
            "tool_result": "TRES",
            "heartbeat_start": "HB",
            "heartbeat_end": "HB",
            "cron_executed": "CRON",
            "memory_write": "MEM",
            "error": "ERR",
            "issue_resolved": "RSLV",
            "task_created": "TSK+",
            "task_updated": "TSK~",
        }
        icon = type_map.get(entry.type, "•")

        context_parts: list[str] = []
        if entry.from_person:
            context_parts.append(f"from:{entry.from_person}")
        if entry.to_person:
            context_parts.append(f"to:{entry.to_person}")
        if entry.channel:
            context_parts.append(f"#{entry.channel}")
        if entry.tool:
            context_parts.append(f"tool:{entry.tool}")
        if entry.via:
            context_parts.append(f"via:{entry.via}")

        ctx = f"({', '.join(context_parts)})" if context_parts else ""
        return f"[{ts}] {icon} {entry.type}{ctx}: {text}"

    @staticmethod
    def _format_human_notify_entry(entry: ActivityEntry, ts: str) -> str:
        """Format human notifications as pointers, not duplicated bodies."""
        subject = str(entry.meta.get("subject") or entry.summary or "").strip()
        if not subject:
            for line in (entry.content or "").splitlines():
                candidate = line.strip().lstrip("#").strip()
                if candidate:
                    subject = candidate
                    break
        if not subject:
            subject = "human notification"
        if len(subject) > 120:
            subject = subject[:117] + "..."

        date_str = entry.ts[:10] if len(entry.ts) >= 10 else "unknown"
        pointer = f"activity_log/{date_str}.jsonl"
        if entry._line_number > 0:
            pointer += f"#L{entry._line_number}"

        via = f"(via:{entry.via})" if entry.via else ""
        return f"[{ts}] NTFY human_notify{via}: {subject} -> {pointer}"

    @staticmethod
    def _format_tool_result_entry(entry: ActivityEntry, ts: str) -> str:
        """Format ``tool_result`` as a compact meta-only line."""
        tool = entry.tool or "unknown"
        meta = entry.meta or {}
        status = meta.get("result_status", "ok")
        result_bytes = meta.get("result_bytes", 0)
        result_count = meta.get("result_count")

        if result_bytes >= 1024:
            size_str = f"{result_bytes / 1024:.1f}KB"
        else:
            size_str = f"{result_bytes}B"

        parts = []
        if result_count is not None:
            parts.append(t("activity.items_count", count=result_count))
        parts.append(size_str)

        detail = f" ({', '.join(parts)})" if parts else ""

        if status == "fail":
            err_hint = (entry.content or "")[:60]
            return f"[{ts}] TRES {tool} → fail: {err_hint}"
        return f"[{ts}] TRES {tool} → ok{detail}"

    @staticmethod
    def _format_heartbeat_reflection(entry: ActivityEntry, ts: str) -> str:
        """Extract a ``[REFLECTION]`` block from heartbeat_end and format it."""
        text = entry.summary or entry.content or ""
        match = re.search(r"\[REFLECTION\](.*?)\[/REFLECTION\]", text, re.DOTALL)
        if not match:
            return ""
        reflection = match.group(1).strip().replace("\n", " ")
        if not reflection:
            return ""
        if len(reflection) > 100:
            reflection = reflection[:97] + "..."
        label = t("activity.heartbeat_reflection")
        return f"[{ts}] {label}: {reflection}"

    # ── Grouping ─────────────────────────────────────────────

    @staticmethod
    def _group_entries(
        entries: list[ActivityEntry],
        time_gap_minutes: int = 30,
    ) -> list[EntryGroup]:
        """Group related entries (DM/HB/cron/channel) for compact display."""
        groups: list[EntryGroup] = []
        current_group: EntryGroup | None = None
        gap_seconds = time_gap_minutes * 60

        for entry in entries:
            entry_type = entry.type

            _is_dm_event = entry_type in ("dm_sent", "dm_received", "message_sent")
            if entry_type == "message_received":
                _is_dm_event = entry.meta.get("from_type") == "anima"
            if _is_dm_event:
                peer = entry.to_person if entry_type in ("dm_sent", "message_sent") else entry.from_person
                if (
                    current_group
                    and current_group.type == "dm"
                    and get_peer(current_group) == peer
                    and time_diff(current_group.end_ts, entry.ts) <= gap_seconds
                ):
                    current_group.entries.append(entry)
                    current_group.end_ts = entry.ts
                    continue
                if current_group:
                    groups.append(current_group)
                current_group = EntryGroup(
                    type="dm",
                    start_ts=entry.ts,
                    end_ts=entry.ts,
                    entries=[entry],
                    label=dm_label(peer, entry),
                    source_lines="",
                )
                continue

            if entry_type in ("heartbeat_start", "heartbeat_end"):
                if current_group and current_group.type == "hb":
                    current_group.entries.append(entry)
                    current_group.end_ts = entry.ts
                    continue
                if current_group:
                    groups.append(current_group)
                current_group = EntryGroup(
                    type="hb",
                    start_ts=entry.ts,
                    end_ts=entry.ts,
                    entries=[entry],
                    label="",
                    source_lines="",
                )
                continue

            if entry_type == "cron_executed":
                task_name = entry.meta.get("task_name", "")
                if current_group and current_group.type == "cron" and get_task_name(current_group) == task_name:
                    current_group.entries.append(entry)
                    current_group.end_ts = entry.ts
                    continue
                if current_group:
                    groups.append(current_group)
                current_group = EntryGroup(
                    type="cron",
                    start_ts=entry.ts,
                    end_ts=entry.ts,
                    entries=[entry],
                    label=task_name,
                    source_lines="",
                )
                continue

            if entry_type in ("channel_post", "channel_read"):
                ch_name = entry.channel or ""
                if (
                    current_group
                    and current_group.type == "channel"
                    and current_group.label == ch_name
                    and time_diff(current_group.end_ts, entry.ts) <= gap_seconds
                ):
                    current_group.entries.append(entry)
                    current_group.end_ts = entry.ts
                    continue
                if current_group:
                    groups.append(current_group)
                current_group = EntryGroup(
                    type="channel",
                    start_ts=entry.ts,
                    end_ts=entry.ts,
                    entries=[entry],
                    label=ch_name,
                    source_lines="",
                )
                continue

            if current_group:
                groups.append(current_group)
                current_group = None
            groups.append(
                EntryGroup(
                    type="single",
                    start_ts=entry.ts,
                    end_ts=entry.ts,
                    entries=[entry],
                    label="",
                    source_lines="",
                )
            )

        if current_group:
            groups.append(current_group)

        for group in groups:
            set_source_lines(group)

        return groups

    @staticmethod
    def _format_group(group: EntryGroup, content_trim: int = 200) -> str:
        """Format a group of entries for priming display."""
        start_time = group.start_ts[11:16] if len(group.start_ts) >= 16 else group.start_ts
        end_time = group.end_ts[11:16] if len(group.end_ts) >= 16 else group.end_ts

        time_range = f"[{start_time}-{end_time}]" if start_time != end_time else f"[{start_time}]"

        if group.type == "dm":
            peer = get_peer(group)
            lines = [f"{time_range} DM {peer}:"]
            for e in group.entries:
                direction = "MSG<" if e.type in ("dm_received", "message_received") else "MSG>"
                text = entry_text(e, prefer="summary")[:100]
                lines.append(f"  {direction} {text}")
            if group.source_lines:
                lines.append(f"  -> {group.source_lines}")
            return "\n".join(lines)

        if group.type == "hb":
            for e in group.entries:
                if e.type == "heartbeat_end":
                    ts = e.ts[11:16] if len(e.ts) >= 16 else e.ts
                    reflection = PrimingMixin._format_heartbeat_reflection(e, ts)
                    if reflection:
                        return reflection
                    hb_summary = entry_text(e, prefer="summary")[:50]
                    if hb_summary:
                        return f"{time_range} HB: {hb_summary}"
            return f"{time_range} HB"

        if group.type == "cron":
            exit_code = group.entries[0].meta.get("exit_code", "")
            exit_info = f": exit={exit_code}" if exit_code != "" else ""
            header = f"{time_range} CRON {group.label}{exit_info}"
            lines = [header]
            if group.source_lines:
                lines.append(f"  -> {group.source_lines}")
            return "\n".join(lines)

        if group.type == "channel":
            ch_name = group.label or "?"
            count = len(group.entries)
            snippets: list[str] = []
            for e in group.entries:
                who = e.from_person or "?"
                text = entry_text(e, prefer="summary")[:50].replace("\n", " ")
                snippets.append(f"{who}→{text}")
            body = ", ".join(snippets)
            lines = [f"{time_range} #{ch_name} ({t('activity.items_count', count=count)}): {body}"]
            if group.source_lines:
                lines.append(f"  -> {group.source_lines}")
            return "\n".join(lines)

        return PrimingMixin._format_entry(group.entries[0], content_trim=content_trim)
