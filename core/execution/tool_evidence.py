from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Shared L1 tool evidence and best-effort activity recording.

Engine adapters normalize provider-specific events into tool records and
activity details, then use this class for consistent record accumulation and
activity-log writes. Activity logging is deliberately best-effort so a failed
log write never interrupts tool execution.
"""

from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.execution.base import ToolCallRecord


def summarise_tool_input(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Return a concise one-line summary of tool input for the activity log."""
    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        return cmd[:300] if cmd else "(empty)"
    if tool_name in ("Read", "Write", "Edit"):
        return tool_input.get("file_path", "(no path)")
    if tool_name in ("Grep", "Glob"):
        return tool_input.get("pattern", "(no pattern)")
    return str(tool_input)[:300]


def sanitise_tool_args(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Strip or bound large payload fields before persisting tool arguments."""
    if tool_name == "Write":
        sanitised = {key: value for key, value in tool_input.items() if key != "content"}
        if "content" in tool_input:
            sanitised["content_length"] = len(tool_input["content"])
        return sanitised
    if tool_name == "Edit":
        sanitised = {}
        for key, value in tool_input.items():
            if key in ("old_string", "new_string"):
                sanitised[key] = value[:200] if isinstance(value, str) else value
            else:
                sanitised[key] = value
        return sanitised
    return tool_input


class ToolEvidence:
    """Accumulate tool-call records and write normalized activity evidence."""

    def __init__(self, anima_dir: Path | None = None) -> None:
        self._anima_dir = anima_dir
        self._records: dict[str, dict[str, Any]] = {}
        self._logged_tool_calls: set[str] = set()

    def started(self, tool_id: str, tool_name: str) -> None:
        """Retain an attempted tool when its completion event is not observed."""
        key = tool_id or f"unknown:{tool_name}"
        self._records.setdefault(
            key,
            asdict(
                ToolCallRecord(
                    tool_id=tool_id,
                    tool_name=tool_name,
                    result_summary="completion_not_observed",
                    is_error=True,
                )
            ),
        )

    def merge(self, records: list[Any]) -> None:
        """Merge completed tool records, replacing provisional starts by ID."""
        for record in records:
            data = asdict(record) if isinstance(record, ToolCallRecord) else dict(record)
            key = data.get("tool_id") or f"unknown:{data.get('tool_name', '')}"
            self._records[key] = data

    def observe(self, event: dict[str, Any]) -> None:
        """Update evidence from a normalized L0 stream event."""
        if event.get("type") == "tool_start":
            self.started(str(event.get("tool_id") or ""), str(event.get("tool_name") or ""))
        self.merge(event.get("tool_call_records") or [])

    def to_dicts(self) -> list[dict[str, Any]]:
        """Return accumulated records in first-observed order."""
        return list(self._records.values())

    def record_tool_use(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        *,
        tool_use_id: str | None = None,
        blocked: bool = False,
        block_reason: str = "",
    ) -> None:
        """Write a normalized ``tool_use`` activity entry (best-effort)."""
        if self._anima_dir is None:
            return
        try:
            from core.memory.activity.logger import ActivityLogger

            meta: dict[str, Any] = {"args": sanitise_tool_args(tool_name, tool_input)}
            if tool_use_id:
                meta["tool_use_id"] = tool_use_id
            if blocked:
                meta["blocked"] = True
                meta["reason"] = block_reason
            ActivityLogger(self._anima_dir).log(
                "tool_use",
                tool=tool_name,
                content=summarise_tool_input(tool_name, tool_input),
                meta=meta,
            )
        except Exception:
            import logging

            logging.getLogger("animaworks.execution.tool_evidence").debug(
                "Failed to log tool_use for %s", tool_name, exc_info=True
            )

    def record_tool_result(
        self,
        tool_name: str,
        tool_use_id: str,
        result_content: str,
        *,
        is_error: bool = False,
        extra_meta: dict[str, Any] | None = None,
    ) -> None:
        """Write a normalized ``tool_result`` activity entry (best-effort)."""
        if self._anima_dir is None:
            return
        try:
            from core.memory.activity.logger import ActivityLogger

            meta: dict[str, Any] = {"tool_use_id": tool_use_id, "is_error": is_error}
            if extra_meta:
                for key, value in extra_meta.items():
                    meta.setdefault(key, value)
            content = result_content[:20_000] if len(result_content) > 20_000 else result_content
            ActivityLogger(self._anima_dir).log("tool_result", tool=tool_name, content=content, meta=meta)
        except Exception:
            import logging

            logging.getLogger("animaworks.execution.tool_evidence").debug(
                "Failed to log tool_result for %s", tool_name, exc_info=True
            )

    def record_tool_call(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
        result_content: str,
        *,
        is_error: bool = False,
        extra_meta: dict[str, Any] | None = None,
    ) -> None:
        """Write one tool-use/result pair, suppressing duplicate completions."""
        key = tool_use_id or f"unknown:{tool_name}"
        if key in self._logged_tool_calls:
            return
        self._logged_tool_calls.add(key)
        self.record_tool_use(tool_name, tool_input, tool_use_id=tool_use_id)
        self.record_tool_result(
            tool_name,
            tool_use_id,
            result_content,
            is_error=is_error,
            extra_meta=extra_meta,
        )

    def __bool__(self) -> bool:
        return bool(self._records)
