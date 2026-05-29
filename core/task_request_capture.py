from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Capture task-like internal DMs as executable recipient tasks.

This is a safety net for manual sends and legacy send_message usage. The
primary path for delegation remains ``delegate_task``.
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.time_utils import get_app_timezone

logger = logging.getLogger("animaworks.task_request_capture")

_ACTION_RE = re.compile(
    r"(再提出|提出|依頼|お願いします|してください|対応|実施|確認|修正|作成|登録|調査|"
    r"検証|回答|返信|resubmit|submit|provide|prepare|fix|check|verify|complete)",
    re.IGNORECASE,
)
_EVIDENCE_RE = re.compile(r"(正式証跡|証跡|evidence|proof)", re.IGNORECASE)
_DEADLINE_MARKER_RE = re.compile(r"(期限|締切|deadline|due)", re.IGNORECASE)
_ABS_DEADLINE_RE = re.compile(
    r"(?P<date>\d{4}-\d{1,2}-\d{1,2})[T\s日]+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?)"
    r"(?:\s*(?:JST|Asia/Tokyo))?",
    re.IGNORECASE,
)
_REL_DEADLINE_RE = re.compile(r"\b(?P<rel>\d+[mhd])\b", re.IGNORECASE)
_NO_CAPTURE_NOTIFICATION_TYPES = {"task_completion", "task_complete_notify"}
_TASK_COMPLETION_NOTICE_RE = re.compile(
    r"^\s*"
    r"(?:\[Thread context[^\]]*\].*?\[/Thread context\]\s*)?"
    r"\u30bf\u30b9\u30af\u300c.*?\u300d\s*"
    r"\(ID:\s*[A-Za-z0-9_-]{1,64}\)\s*"
    r"\u304c\u5b8c\u4e86\u3057\u307e\u3057\u305f",
    re.DOTALL,
)
_STATUS_INQUIRY_RE = re.compile(
    r"(?:へ)?確認です|ステータス|達成状況|進捗|対応状況|完了見込み|ブロッカー|max iterations",
    re.IGNORECASE,
)
_STATUS_INQUIRY_REPLY_RE = re.compile(
    r"(?:教えてください|知らせてください|共有してください)",
    re.IGNORECASE,
)


def _is_task_completion_notice(content: str, meta: dict[str, Any]) -> bool:
    """Return True for TaskExec completion chatter, including legacy bodies."""
    if meta.get("notification_type") in _NO_CAPTURE_NOTIFICATION_TYPES:
        return True
    return bool(_TASK_COMPLETION_NOTICE_RE.search(content))


def _is_status_inquiry(content: str, intent: str) -> bool:
    """Return True for supervisory status-check DMs, not executable work."""
    if intent != "question":
        return False
    if not _STATUS_INQUIRY_RE.search(content):
        return False
    return bool(_STATUS_INQUIRY_REPLY_RE.search(content))


def looks_like_task_request(*, content: str, intent: str = "", msg_type: str = "message", meta: dict[str, Any] | None = None) -> bool:
    """Return True when a DM looks like actionable work for the recipient."""
    if msg_type != "message":
        return False
    meta = meta or {}
    if meta.get("task_id") or meta.get("autocreated_task_id"):
        return False
    if _is_task_completion_notice(content, meta):
        return False
    if _is_status_inquiry(content, intent):
        return False
    if intent == "delegation":
        return False

    text = content.strip()
    if not text:
        return False

    has_action = bool(_ACTION_RE.search(text))
    has_deadline = bool(_DEADLINE_MARKER_RE.search(text) or _ABS_DEADLINE_RE.search(text))
    has_evidence = bool(_EVIDENCE_RE.search(text))
    return has_action and (has_deadline or has_evidence)


def extract_deadline(content: str) -> str | None:
    """Extract a TaskQueue-compatible deadline from free-form text."""
    marker_pos = _DEADLINE_MARKER_RE.search(content)
    search_text = content[marker_pos.start() :] if marker_pos else content

    abs_match = _ABS_DEADLINE_RE.search(search_text)
    if abs_match:
        raw = f"{abs_match.group('date')}T{abs_match.group('time')}"
        try:
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=get_app_timezone())
            return dt.isoformat()
        except ValueError:
            logger.debug("Failed to parse absolute deadline from %r", raw)

    rel_match = _REL_DEADLINE_RE.search(search_text)
    if rel_match:
        return rel_match.group("rel").lower()

    return None


def summarize_task_request(content: str, to: str) -> str:
    """Build a concise queue summary for a captured task request."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:120]
    return f"DM task request for {to}"


def capture_task_request_from_message(
    *,
    animas_dir: Path,
    from_person: str,
    to_person: str,
    content: str,
    message_id: str,
    thread_id: str,
    intent: str = "",
    msg_type: str = "message",
    meta: dict[str, Any] | None = None,
) -> str | None:
    """Create recipient task files for task-like internal DMs.

    Returns the created or existing task id. Returns ``None`` when the message
    is not task-like, is not between known Animas, or persistence fails.
    """
    if not looks_like_task_request(content=content, intent=intent, msg_type=msg_type, meta=meta):
        return None

    sender_dir = animas_dir / from_person
    target_dir = animas_dir / to_person
    if not sender_dir.is_dir() or not target_dir.is_dir():
        return None

    try:
        from core.memory.task_queue import TaskQueueManager

        manager = TaskQueueManager(target_dir)
        for task in manager.list_tasks():
            task_meta = task.meta or {}
            if task_meta.get("source_message_id") == message_id:
                return task.task_id

        deadline = extract_deadline(content)
        summary = summarize_task_request(content, to_person)
        entry = manager.add_task(
            source="anima",
            original_instruction=content,
            assignee=to_person,
            summary=summary,
            deadline=deadline,
            relay_chain=[from_person],
            meta={
                "source": "message_request_capture",
                "source_message_id": message_id,
                "source_thread_id": thread_id,
                "source_from": from_person,
                "source_intent": intent,
            },
        )

        task_desc = {
            "task_type": "llm",
            "task_id": entry.task_id,
            "title": summary,
            "description": content,
            "context": "",
            "acceptance_criteria": [],
            "constraints": [],
            "file_paths": [],
            "submitted_by": from_person,
            "submitted_at": datetime.now(UTC).isoformat(),
            "reply_to": from_person,
            "source": "message_request_capture",
            "working_directory": "",
            "priority": entry.priority,
        }
        pending_dir = target_dir / "state" / "pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        (pending_dir / f"{entry.task_id}.json").write_text(
            json.dumps(task_desc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info(
            "Captured task-like DM as recipient task: %s -> %s task=%s msg=%s",
            from_person,
            to_person,
            entry.task_id,
            message_id,
        )
        return entry.task_id
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to capture task-like DM as recipient task: %s -> %s msg=%s: %s",
            from_person,
            to_person,
            message_id,
            exc,
        )
        return None
