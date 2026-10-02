from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.


"""Filter "did nothing" cron executions out of episode-summary input.

Phase A of daily consolidation feeds activity-log entries to the episode
summariser.  Frequently-triggered LLM/command crons (e.g. 5-minute
polling loops) run dozens of times a day and produce a large fraction of
``cron_executed`` records that report "nothing new happened".  This module
provides a *pure* function, :func:`filter_noop_cron_entries`, that
recognises such executions and returns the entries that should still be
kept, together with a small :class:`NoopStats` summary.

The activity log itself (``activity_log/*.jsonl``) is never modified;
this only decides which entries are passed to the summariser.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from core.time_utils import ensure_aware

# ── External-action tool names ─────────────────────────────────
#
# When an LLM cron calls one of these tools (directly or via an
# ``mcp__aw__``-prefixed name) it has produced a side effect that the
# episode should record, so the cron is not "noop".
_EXTERNAL_ACTION_TOOLS = frozenset(
    {
        "send_message",
        "post_channel",
        "call_human",
        "delegate_task",
        "submit_tasks",
        "write_memory_file",
        "create_task",
        "create_anima",
        "update_task",
        "backlog_task",
        "todo_write",
        "manage_channel",
        "archive_memory_file",
        "archive_skill",
        "create_skill",
        "delete_skill",
        "restore_skill",
        "block_skill",
        "unblock_skill",
        "trust_skill",
        "set_skill_lifecycle",
        "promote_procedure_to_skill",
        "curate_skills",
        "grant_workspace_access",
        "enable_subordinate",
        "disable_subordinate",
        "set_subordinate_model",
        "set_subordinate_background_model",
        "restart_subordinate",
        "audit_subordinate",
        "ping_subordinate",
        "report_knowledge_outcome",
        "report_procedure_outcome",
        "vault_store",
    }
)

# Command-line verbs that cause an external side effect when invoked
# via ``animaworks-tool <tool> <verb> ...`` (case-insensitive).
_EXTERNAL_BASH_RE = re.compile(
    r"animaworks-tool\s+[^\s]+\s+(?:send|post|reply|create|update|delete|add|remove)\b",
    re.IGNORECASE,
)


@dataclass
class NoopStats:
    """Counters describing what :func:`filter_noop_cron_entries` removed."""

    entries_total: int = 0
    llm_excluded: int = 0
    command_excluded: int = 0
    tool_entries_excluded: int = 0


def _parse_ts(ts: str | None) -> datetime | None:
    """Parse an ISO timestamp to an aware datetime, or ``None`` if invalid."""
    if not ts:
        return None
    try:
        return ensure_aware(datetime.fromisoformat(ts))
    except (ValueError, TypeError):
        return None


def _is_command_cron(entry: Any) -> bool:
    """Whether *entry* is a command-type (non-LLM) cron execution."""
    if getattr(entry, "type", None) != "cron_executed":
        return False
    meta = getattr(entry, "meta", None) or {}
    return "exit_code" in meta and "command" in meta


def _is_llm_cron(entry: Any) -> bool:
    """Whether *entry* is an LLM-backed cron execution (has a duration)."""
    if getattr(entry, "type", None) != "cron_executed":
        return False
    meta = getattr(entry, "meta", None) or {}
    duration = meta.get("duration_ms")
    return isinstance(duration, (int, float)) and duration and "status" in meta


def _tool_has_external_action(entry: Any) -> bool:
    """Whether a ``tool_use`` entry performs an external, side-effecting action."""
    tool = getattr(entry, "tool", None) or ""
    base_tool = tool
    if base_tool.startswith("mcp__aw__"):
        base_tool = base_tool[len("mcp__aw__") :]
    if base_tool in _EXTERNAL_ACTION_TOOLS:
        return True

    command = getattr(entry, "content", None) or ""
    if not command:
        args = getattr(entry, "meta", None) or {}
        if isinstance(args.get("args"), dict):
            command = args["args"].get("command") or ""
    return bool(_EXTERNAL_BASH_RE.search(command))


def _llm_cron_is_noop(
    entries: list[Any],
    timestamps: list[datetime | None],
    llm_crons: list[tuple[int, datetime, datetime]],
    idx: int,
    window_start: datetime,
    window_end: datetime,
) -> bool:
    """Return whether LLM cron *idx* "did nothing" within its time window.

    All of the following must hold:
    - ``meta.status == "completed"``
    - the window ``[ts - duration_ms, ts]`` overlaps no other LLM cron window
    - no non-tool entry (message, memory write, task update, heartbeat,
      inbox/task execution, ...) falls inside the window
    - no ``tool_use`` inside the window performs an external action
    """
    entry = entries[idx]
    meta = getattr(entry, "meta", None) or {}
    if meta.get("status") != "completed":
        return False

    # Overlap with another LLM cron window → not noop (be safe).
    for other_idx, other_start, other_end in llm_crons:
        if other_idx == idx:
            continue
        if window_start <= other_end and other_start <= window_end:
            return False

    for other_idx, other in enumerate(entries):
        if other_idx == idx:
            continue
        ts = timestamps[other_idx]
        if ts is None or not (window_start <= ts <= window_end):
            continue
        other_type = getattr(other, "type", None)
        if other_type == "tool_use":
            if _tool_has_external_action(other):
                return False
            continue
        if other_type == "tool_result":
            continue
        if _is_command_cron(other):
            # A command cron inside the window is not "something happened".
            continue
        return False
    return True


def filter_noop_cron_entries(entries: Iterable[Any]) -> tuple[list[Any], NoopStats]:
    """Return entries to keep after removing "did nothing" cron executions.

    Applies the Phase A noop-cron filter described in the consolidation
    plan: command-type crons that exited 0 are removed, and LLM crons
    whose execution window contained no meaningful activity are removed
    together with their own in-window tool entries.

    Args:
        entries: Activity entries (objects with ``ts``, ``type``,
            ``content``, ``meta``, ``tool`` attributes).

    Returns:
        A ``(kept_entries, stats)`` pair.  The activity log is untouched.
    """
    all_entries = list(entries)
    stats = NoopStats(entries_total=len(all_entries))
    excluded: set[int] = set()
    timestamps = [_parse_ts(getattr(entry, "ts", None)) for entry in all_entries]

    llm_crons: list[tuple[int, datetime, datetime]] = []
    for idx, entry in enumerate(all_entries):
        if _is_command_cron(entry):
            meta = getattr(entry, "meta", None) or {}
            if meta.get("exit_code") == 0:
                excluded.add(idx)
                stats.command_excluded += 1
            continue
        if _is_llm_cron(entry):
            end = timestamps[idx]
            if end is None:
                continue
            start = end - timedelta(milliseconds=entry.meta["duration_ms"])
            llm_crons.append((idx, start, end))

    for idx, start, end in llm_crons:
        if not _llm_cron_is_noop(all_entries, timestamps, llm_crons, idx, start, end):
            continue
        if idx in excluded:
            continue
        excluded.add(idx)
        stats.llm_excluded += 1
        for tool_idx, tool_entry in enumerate(all_entries):
            if tool_idx in excluded:
                continue
            tool_type = getattr(tool_entry, "type", None)
            if tool_type not in ("tool_use", "tool_result"):
                continue
            ts = timestamps[tool_idx]
            if ts is not None and start <= ts <= end:
                excluded.add(tool_idx)
                stats.tool_entries_excluded += 1

    return [entry for idx, entry in enumerate(all_entries) if idx not in excluded], stats
