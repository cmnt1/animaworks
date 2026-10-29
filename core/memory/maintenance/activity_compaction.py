from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Deterministic compaction for daily episode-summary activity input.

The transformations here are intentionally mechanical: they operate only on
activity metadata and text already present in the local activity log. They do
not call an LLM or modify the source log.
"""

import re
from bisect import bisect_left
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

ActivityInputProfile = Literal["full", "compact", "compact_v2"]
# Profiles a date can be recorded with. ``compact`` is frozen so dates already
# summarised with it keep their checkpoint hashes; new dates requesting
# ``compact`` get the current compact version.
INPUT_PROFILES: tuple[str, ...] = ("full", "compact", "compact_v2")
CURRENT_COMPACT_PROFILE = "compact_v2"
_BASH_TOOLS = frozenset({"Bash"})


def is_compact_profile(profile: str) -> bool:
    return profile in ("compact", "compact_v2")


@dataclass(frozen=True)
class ActivityCompactionSettings:
    """Settings controlling the compact daily-episode input profile."""

    profile: ActivityInputProfile = "compact"
    cron_digest_min_runs: int = 6
    cron_digest_max_notable_runs: int = 5
    tool_use_max_bytes: int = 300
    error_tail_bytes: int = 300
    bash_tool_use_max_bytes: int = 120

    def tool_use_bytes_for(self, entry: Any) -> int:
        """Body-size limit for a tool_use entry under this profile."""
        if self.profile == "compact_v2" and str(getattr(entry, "tool", "") or "") in _BASH_TOOLS:
            return min(self.tool_use_max_bytes, self.bash_tool_use_max_bytes)
        return self.tool_use_max_bytes

    @classmethod
    def from_config(cls, consolidation_cfg: Any, defaults: Any | None = None) -> ActivityCompactionSettings:
        """Build compaction settings from ConsolidationConfig-like objects."""

        def value(config_name: str, default_value: Any) -> Any:
            fallback = getattr(defaults, config_name, default_value) if defaults is not None else default_value
            return getattr(consolidation_cfg, config_name, fallback)

        profile = value("episode_summary_input_profile", "compact")
        if profile not in INPUT_PROFILES:
            profile = "compact"
        return cls(
            profile=profile,
            cron_digest_min_runs=max(1, int(value("episode_summary_cron_digest_min_runs", 6))),
            cron_digest_max_notable_runs=max(0, int(value("episode_summary_cron_digest_max_notable_runs", 5))),
            tool_use_max_bytes=max(0, int(value("episode_summary_tool_use_max_bytes", 300))),
            error_tail_bytes=max(0, int(value("episode_summary_error_tail_bytes", 300))),
            bash_tool_use_max_bytes=max(0, int(value("episode_summary_bash_tool_use_max_bytes", 120))),
        )


@dataclass(frozen=True)
class ActivityCompactionStats:
    """Input/output sizes and counts for one compacted entry sequence."""

    bytes_before: int = 0
    bytes_after: int = 0
    cron_digests: int = 0
    cron_runs_folded: int = 0
    tool_results_one_lined: int = 0
    duplicate_commands_folded: int = 0


@dataclass(frozen=True)
class _RenderedLine:
    """A synthetic one-line activity entry inserted by compaction."""

    ts: str
    text: str


# These records remain byte-for-byte formatted by the existing full formatter,
# even when they are inside a cron run that is otherwise digested.
_PRESERVED_EVENT_TYPES = frozenset(
    {
        "message_sent",
        "message_received",
        "response_sent",
        "human_notify",
        "heartbeat_reflection",
        "memory_write",
        "error",
        "task_exec_end",
    }
)
_COMPLETED_TASK_STATUSES = frozenset({"done", "completed", "closed", "resolved", "success", "succeeded", "finished"})
_NOTABLE_CRON_EVENT_TYPES = frozenset({"message_sent", "human_notify", "response_sent", "error"})
_PATH_TOKEN_RE = re.compile(r"(?:\.\.?/)?[\w./-]+", re.UNICODE)


def compact_activity_entries(
    entries: list[Any],
    *,
    settings: ActivityCompactionSettings,
    format_full: Callable[[Any], str],
    format_tool_use: Callable[[Any], str],
) -> tuple[list[tuple[str, str]], ActivityCompactionStats]:
    """Compact entries and return ``(date-hour/text lines, statistics)``.

    ``format_full`` must be the existing, unmodified formatter. It is used for
    the byte baseline and for entries that the compact profile does not alter.
    ``format_tool_use`` applies the configured body-size limit.
    """
    bytes_before = _rendered_size(format_full(entry) for entry in entries)
    cron_items, cron_digests, cron_runs_folded = _fold_cron_runs(entries, settings)
    command_items, duplicate_commands_folded = _fold_repeated_tool_uses(cron_items)

    rendered: list[tuple[str, str]] = []
    tool_results_one_lined = 0
    for item in command_items:
        if isinstance(item, _RenderedLine):
            ts = item.ts
            text = item.text
        else:
            ts = str(getattr(item, "ts", "") or "")
            event_type = getattr(item, "type", "")
            if event_type == "tool_result":
                text = _format_tool_result(item, settings.error_tail_bytes)
                tool_results_one_lined += 1
            elif event_type == "tool_use":
                text = format_tool_use(item)
            else:
                text = format_full(item)
        hour_key = ts[:13] if len(ts) >= 13 else "0000-00-00T00"
        rendered.append((hour_key, text))

    bytes_after = _rendered_size(text for _, text in rendered)
    return rendered, ActivityCompactionStats(
        bytes_before=bytes_before,
        bytes_after=bytes_after,
        cron_digests=cron_digests,
        cron_runs_folded=cron_runs_folded,
        tool_results_one_lined=tool_results_one_lined,
        duplicate_commands_folded=duplicate_commands_folded,
    )


def count_rendered_activity_entries(chunks: list[str]) -> int:
    """Count formatted activity-entry headers across already-split chunks."""
    return sum(len(re.findall(r"(?m)^\[[^\]\n]+\] ", chunk)) for chunk in chunks)


def _rendered_size(lines: Iterable[str]) -> int:
    """Return UTF-8 bytes including the newlines used between activity lines."""
    return sum(len(line.encode("utf-8")) + 1 for line in lines)


def _fold_cron_runs(
    entries: list[Any],
    settings: ActivityCompactionSettings,
) -> tuple[list[Any | _RenderedLine], int, int]:
    """Replace high-frequency cron runs with a digest and selected full runs."""
    anchors_by_name: dict[tuple[str, str], list[int]] = defaultdict(list)
    context_entries_by_name: dict[tuple[str, str], list[int]] = defaultdict(list)

    for index, entry in enumerate(entries):
        if getattr(entry, "type", "") == "cron_executed":
            task_name = _cron_task_name(entry)
            if task_name:
                anchors_by_name[(_entry_date(entry), task_name)].append(index)
            continue
        task_name = _cron_context_name(entry)
        if task_name:
            context_entries_by_name[(_entry_date(entry), task_name)].append(index)

    suppressed: set[int] = set()
    preserved: set[int] = set()
    insertions: dict[int, _RenderedLine] = {}
    cron_digests = 0
    cron_runs_folded = 0

    for (run_date, task_name), anchors in anchors_by_name.items():
        if len(anchors) < settings.cron_digest_min_runs:
            continue

        run_indices: list[list[int]] = [[] for _ in anchors]
        for index in context_entries_by_name.get((run_date, task_name), []):
            run_index = bisect_left(anchors, index)
            if run_index == len(anchors):
                # Entries after the final cron_executed record are still part
                # of the last run when a runtime emits a trailing event late.
                run_index -= 1
            run_indices[run_index].append(index)
        for run_index, anchor in enumerate(anchors):
            run_indices[run_index].append(anchor)
            run_indices[run_index].sort()

        notable_indices = [
            run_index
            for run_index, run in enumerate(run_indices)
            if _is_notable_run([entries[index] for index in run], entries[anchors[run_index]])
        ]
        selected_runs = {0, len(run_indices) - 1}
        selected_runs.update(notable_indices[: settings.cron_digest_max_notable_runs])

        all_indices = {index for run in run_indices for index in run}
        retained_indices = {index for run_index in selected_runs for index in run_indices[run_index]}
        suppressed.update(all_indices - retained_indices)
        preserved.update(index for index in all_indices if _is_preserved_entry(entries[index]))

        completed = sum(not _cron_run_failed(entries[anchor]) for anchor in anchors)
        failed = len(anchors) - completed
        send_count = sum(
            1
            for index in all_indices
            if getattr(entries[index], "type", "") in {"message_sent", "human_notify", "response_sent"}
        )
        memory_writes = [
            entries[index] for index in all_indices if getattr(entries[index], "type", "") == "memory_write"
        ]
        memory_paths = Counter(path for entry in memory_writes if (path := _memory_write_path(entry)))
        top_paths = ", ".join(f"{path}×{count}" for path, count in memory_paths.most_common(3)) or "none"
        summary = (
            f"[cron digest] {task_name}: {len(anchors)}回実行（completed={completed}, failed={failed}）, "
            f"送信/通知 {send_count}回, memory_write {len(memory_writes)}回"
            f"（パス上位3件: {top_paths}）"
        )
        first_index = min(run_indices[0]) if run_indices[0] else anchors[0]
        insertions[first_index] = _RenderedLine(
            ts=str(getattr(entries[first_index], "ts", "") or ""),
            text=f"[{_short_time(getattr(entries[first_index], 'ts', ''))}] {summary}",
        )
        cron_digests += 1
        cron_runs_folded += len(run_indices) - len(selected_runs)

    suppressed.difference_update(preserved)
    compacted: list[Any | _RenderedLine] = []
    for index, entry in enumerate(entries):
        synthetic = insertions.get(index)
        if synthetic is not None:
            compacted.append(synthetic)
        if index not in suppressed:
            compacted.append(entry)
    return compacted, cron_digests, cron_runs_folded


def _fold_repeated_tool_uses(items: list[Any | _RenderedLine]) -> tuple[list[Any | _RenderedLine], int]:
    """Keep only first/last identical tool uses and their results."""
    uses_by_command: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        if isinstance(item, _RenderedLine) or getattr(item, "type", "") != "tool_use":
            continue
        command = _normalized_command(item)
        if command:
            tool = str(getattr(item, "tool", "") or "")
            uses_by_command[(_entry_date(item), tool, command)].append(index)

    paired_results = _pair_tool_results(items)
    suppressed: set[int] = set()
    insertions: dict[int, _RenderedLine] = {}
    folded_count = 0
    for uses in uses_by_command.values():
        if len(uses) < 3:
            continue
        middle = uses[1:-1]
        for index in middle:
            suppressed.add(index)
            suppressed.update(paired_results.get(index, []))
        first_middle = middle[0]
        entry = items[first_middle]
        ts = str(getattr(entry, "ts", "") or "")
        insertions[first_middle] = _RenderedLine(
            ts=ts,
            text=f"[{_short_time(ts)}] （同一コマンド ×{len(middle)} 回、結果は省略）",
        )
        folded_count += len(middle)

    compacted: list[Any | _RenderedLine] = []
    for index, item in enumerate(items):
        synthetic = insertions.get(index)
        if synthetic is not None:
            compacted.append(synthetic)
        if index not in suppressed:
            compacted.append(item)
    return compacted, folded_count


def _pair_tool_results(items: list[Any | _RenderedLine]) -> dict[int, list[int]]:
    """Pair tool results by ID, falling back to ordered per-tool pairing."""
    results_by_id: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        if isinstance(item, _RenderedLine) or getattr(item, "type", "") != "tool_result":
            continue
        tool_use_id = _tool_use_id(item)
        if tool_use_id:
            results_by_id[tool_use_id].append(index)

    paired: dict[int, list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        if isinstance(item, _RenderedLine) or getattr(item, "type", "") != "tool_use":
            continue
        tool_use_id = _tool_use_id(item)
        if tool_use_id:
            paired[index].extend(results_by_id.get(tool_use_id, []))

    open_uses_by_tool: dict[str, list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        if isinstance(item, _RenderedLine):
            continue
        event_type = getattr(item, "type", "")
        tool = str(getattr(item, "tool", "") or "")
        if event_type == "tool_use" and not _tool_use_id(item):
            open_uses_by_tool[tool].append(index)
        elif event_type == "tool_result" and not _tool_use_id(item):
            open_uses = open_uses_by_tool.get(tool)
            if open_uses:
                paired[open_uses.pop(0)].append(index)
    return paired


def _entry_date(entry: Any) -> str:
    ts = str(getattr(entry, "ts", "") or "")
    return ts[:10] if len(ts) >= 10 else "unknown-date"


def _cron_task_name(entry: Any) -> str:
    meta = getattr(entry, "meta", None) or {}
    name = meta.get("task_name") if isinstance(meta, dict) else None
    if isinstance(name, str) and name.strip():
        return name.strip()
    return _cron_context_name(entry)


def _cron_context_name(entry: Any) -> str:
    context = getattr(entry, "ctx", "") or ""
    if isinstance(context, str) and context.startswith("cron:"):
        name = context[len("cron:") :].strip()
        return name or ""
    return ""


def _is_notable_run(run: list[Any], anchor: Any) -> bool:
    if _cron_run_failed(anchor):
        return True
    for entry in run:
        event_type = getattr(entry, "type", "")
        if event_type in _NOTABLE_CRON_EVENT_TYPES:
            return True
        if event_type == "tool_result" and _tool_result_failed(entry):
            return True
    return False


def _cron_run_failed(anchor: Any) -> bool:
    meta = getattr(anchor, "meta", None) or {}
    if not isinstance(meta, dict):
        meta = {}
    if _has_nonzero_exit_code(meta.get("exit_code")):
        return True
    status = meta.get("status")
    if status is not None:
        return str(status).strip().lower() != "completed"
    return False


def _is_preserved_entry(entry: Any) -> bool:
    event_type = getattr(entry, "type", "")
    if event_type in _PRESERVED_EVENT_TYPES:
        return True
    if event_type != "task_updated":
        return False
    meta = getattr(entry, "meta", None) or {}
    if not isinstance(meta, dict):
        return False
    status = meta.get("status") or meta.get("state")
    return isinstance(status, str) and status.strip().lower() in _COMPLETED_TASK_STATUSES


def _tool_result_failed(entry: Any) -> bool:
    meta = getattr(entry, "meta", None) or {}
    if not isinstance(meta, dict):
        return False
    return (
        bool(meta.get("is_error"))
        or meta.get("result_status") == "fail"
        or _has_nonzero_exit_code(meta.get("exit_code"))
    )


def _has_nonzero_exit_code(value: Any) -> bool:
    if value is None or value == "":
        return False
    try:
        return int(value) != 0
    except (TypeError, ValueError, OverflowError):
        return True


def _memory_write_path(entry: Any) -> str | None:
    meta = getattr(entry, "meta", None) or {}
    if isinstance(meta, dict):
        for key in ("path", "file_path", "target_path", "filename"):
            value = meta.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    text = str(getattr(entry, "summary", "") or getattr(entry, "content", "") or "")
    for token in _PATH_TOKEN_RE.findall(text):
        candidate = token.rstrip(".,:;)")
        if "." in candidate.rsplit("/", maxsplit=1)[-1] and candidate not in {".", ".."}:
            return candidate
    return None


def _normalized_command(entry: Any) -> str:
    meta = getattr(entry, "meta", None) or {}
    args = meta.get("args") if isinstance(meta, dict) else None
    command = args.get("command") if isinstance(args, dict) else None
    if not isinstance(command, str) or not command.strip():
        command = getattr(entry, "content", "") or getattr(entry, "summary", "") or ""
    if not isinstance(command, str):
        command = str(command)
    return " ".join(command.split())


def _tool_use_id(entry: Any) -> str:
    meta = getattr(entry, "meta", None) or {}
    value = meta.get("tool_use_id") if isinstance(meta, dict) else None
    return str(value) if value else ""


def _format_tool_result(entry: Any, error_tail_bytes: int) -> str:
    """Render a tool result as one metadata line, optionally retaining its tail."""
    ts = str(getattr(entry, "ts", "") or "")
    meta = getattr(entry, "meta", None) or {}
    if not isinstance(meta, dict):
        meta = {}
    failed = _tool_result_failed(entry)
    result_bytes = meta.get("result_bytes")
    if isinstance(result_bytes, (int, float)) and not isinstance(result_bytes, bool) and result_bytes >= 0:
        byte_count = int(result_bytes)
    else:
        byte_count = len(str(getattr(entry, "content", "") or "").encode("utf-8"))
    tool = str(getattr(entry, "tool", "") or "unknown").replace("\r", " ").replace("\n", " ")
    status = "fail" if failed else "ok"
    text = f"[{_short_time(ts)}] [tool_result {tool} exit={status} bytes={byte_count}]"
    if failed and error_tail_bytes > 0:
        content = str(getattr(entry, "content", "") or getattr(entry, "summary", "") or "")
        tail = _utf8_tail(content, error_tail_bytes).replace("\r", "\\r").replace("\n", "\\n")
        if tail:
            text += f" error_tail: {tail}"
    return text


def _utf8_tail(text: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return ""
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[-max_bytes:].decode("utf-8", errors="ignore")


def _short_time(ts: Any) -> str:
    value = str(ts or "")
    return value[11:16] if len(value) >= 16 else value
