from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Conversation view mixin for ActivityLogger.

Internal module — import from :mod:`core.activity.logger` instead.
"""

import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any

from core.activity.format import EVENT_SETS
from core.activity.models import (
    ActivityEntry,
    time_diff,
)
from core.i18n import t
from core.time_utils import now_local

logger = logging.getLogger("animaworks.activity")


_TOOL_RESULT_TRUNCATE = 1500
_TOOL_INPUT_TRUNCATE = 500


def _source_key_for_entry(entry: ActivityEntry) -> str:
    """Return a compact source key for chat rendering."""
    if entry.type.startswith("heartbeat_"):
        return "heartbeat"
    if entry.type == "cron_executed":
        return "cron"
    if entry.type.startswith("task_exec_"):
        return "task"
    if entry.channel == "inbox":
        return "inbox"
    if entry.channel == "chat":
        return "chat"
    if entry.type == "message_sent":
        return "dm"
    return entry.channel or "chat"


def _is_inbox_raw_entry(raw: dict[str, Any]) -> bool:
    meta = raw.get("meta", {})
    trigger = meta.get("trigger", "") if isinstance(meta, dict) else ""
    session_type = meta.get("session_type", "") if isinstance(meta, dict) else ""
    return (
        raw.get("channel") == "inbox"
        or session_type == "inbox"
        or trigger == "inbox"
        or (isinstance(trigger, str) and trigger.startswith("inbox:"))
    )


def _external_user_aliases() -> dict[str, str]:
    """Map external chat user IDs (Slack/Discord/Chatwork) to configured user aliases."""
    try:
        from core.config.io import load_config

        aliases = load_config().external_messaging.user_aliases
    except Exception:
        logger.debug("Failed to load external user aliases", exc_info=True)
        return {}
    mapping: dict[str, str] = {}
    for alias, cfg in aliases.items():
        for ext_id in (cfg.slack_user_id, cfg.discord_user_id, cfg.chatwork_room_id):
            if ext_id:
                mapping[str(ext_id)] = alias
    return mapping


def _split_interim_texts(content: str, interim: list[Any]) -> tuple[str, list[str]]:
    """Remove progress remarks spoken before tool calls from the start of a reply.

    Returns the remaining reply body and the remarks that were actually found.
    When nothing lines up, the content is returned unchanged.
    """
    rest = content.lstrip()
    found: list[str] = []
    for item in interim:
        text = str(item or "").strip()
        if not text:
            continue
        if not rest.startswith(text):
            break
        found.append(text)
        rest = rest[len(text) :].lstrip()
    if not found or not rest:
        return content, []
    return rest, found


def _truncate_tool_field(value: Any, limit: int) -> Any:
    """Truncate tool input/result for the conversation view API."""
    if isinstance(value, str):
        if len(value) <= limit:
            return value
        return value[:limit] + f"\n…({len(value) - limit} chars truncated)"
    if isinstance(value, (dict, list)):
        s = json.dumps(value, ensure_ascii=False)
        if len(s) <= limit:
            return value
        return s[:limit] + f"\n…({len(s) - limit} chars truncated)"
    return value


def _tool_target_from_input(value: Any) -> str:
    """Extract a compact, user-facing target from a tool's input."""
    obj = value
    if isinstance(value, str):
        try:
            obj = json.loads(value)
        except (TypeError, ValueError):
            obj = value

    target: Any = None
    if isinstance(obj, dict):
        for key in ("file_path", "path", "command", "query", "pattern", "url", "to", "name", "channel"):
            candidate = obj.get(key)
            if candidate:
                target = candidate
                break
    elif obj is not None:
        target = obj

    if target is None:
        return ""
    if isinstance(target, (dict, list)):
        target = json.dumps(target, ensure_ascii=False)
    compact = re.sub(r"\s+", " ", str(target)).strip()
    return compact[:80]


def _summarize_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    """Return only the fields needed to list a tool call in chat history."""
    return {
        "tool_name": tool_call.get("tool_name", ""),
        "tool_use_id": tool_call.get("tool_use_id", ""),
        "is_error": bool(tool_call.get("is_error", False)),
        "target": tool_call.get("target")
        or _tool_target_from_input(tool_call.get("input", tool_call.get("input_summary", ""))),
    }


class ConversationMixin:
    """Mixin providing conversation view methods for ActivityLogger."""

    _CONVERSATION_TYPES = EVENT_SETS["chat"]

    def get_conversation_view(
        self,
        *,
        before: str | None = None,
        limit: int = 50,
        session_gap_minutes: int = 10,
        thread_id: str | None = None,
        strict_thread: bool = False,
        tool_detail: str = "full",
    ) -> dict[str, Any]:
        """Build a conversation view from activity log entries.

        Pairs tool events, groups into sessions (by gap/trigger change),
        returns ``{"sessions": [...], "has_more": bool, "next_before": str}``.
        """
        entries = self._load_conversation_entries(
            before=before,
            limit=limit,
            thread_id=thread_id,
            strict_thread=strict_thread,
        )
        messages = self._entries_to_messages(entries, tool_detail=tool_detail)

        if len(messages) <= limit and entries:
            entries = self._load_conversation_entries(
                before=before,
                limit=limit,
                thread_id=thread_id,
                strict_thread=strict_thread,
                _target_multiplier=15,
            )
            messages = self._entries_to_messages(entries, tool_detail=tool_detail)

        has_more = len(messages) > limit
        if has_more:
            messages = messages[-limit:]

        next_before: str | None = None
        if has_more and messages:
            next_before = messages[0]["ts"]

        sessions = self._group_into_sessions(messages, session_gap_minutes)

        return {
            "sessions": sessions,
            "has_more": has_more,
            "next_before": next_before,
        }

    def get_conversation_tool_calls(
        self,
        message_ts: str,
        *,
        thread_id: str = "default",
        strict_thread: bool = False,
    ) -> list[dict[str, Any]] | None:
        """Load full tool calls attached to a specific assistant message."""
        try:
            message_time = datetime.fromisoformat(message_ts.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            return None

        entries = self._load_conversation_entries(
            before=(message_time + timedelta(microseconds=1)).isoformat(),
            limit=200,
            thread_id=thread_id,
            strict_thread=strict_thread,
            _specific_day=message_time.date(),
        )

        message = next(
            (
                item
                for item in self._entries_to_messages(entries)
                if item.get("role") == "assistant" and item.get("ts") == message_ts
            ),
            None,
        )
        tool_calls = message.get("tool_calls") if message else None
        return tool_calls if tool_calls else None

    def _load_conversation_entries(
        self,
        *,
        before: str | None = None,
        limit: int = 50,
        thread_id: str | None = None,
        strict_thread: bool = False,
        _target_multiplier: int = 3,
        _specific_day: date | None = None,
    ) -> list[ActivityEntry]:
        """Load conversation-relevant entries, scanning enough days for *limit* messages."""
        target_raw = limit * _target_multiplier + 50
        entries: list[ActivityEntry] = []
        today = now_local().date()
        max_scan_days = 365
        # Thread filters may match few entries and never reach target_raw;
        # without a file cap the scan reads (and JSON-parses) every log file
        # ever written, blocking for seconds per request. Named threads have
        # a conversation-file fallback for older history.
        max_files_scanned = 30
        files_scanned = 0

        target_days = (
            [_specific_day]
            if _specific_day is not None
            else [today - timedelta(days=day_offset) for day_offset in range(max_scan_days)]
        )
        for target in target_days:
            day_offset = (today - target).days
            path = self._log_dir / f"{target.isoformat()}.jsonl"  # type: ignore[attr-defined]
            if not path.exists():
                if day_offset > 30 and not entries:
                    break
                continue

            day_entries: list[ActivityEntry] = []
            try:
                for line_num, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(),
                    start=1,
                ):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if raw.get("type") not in self._CONVERSATION_TYPES:
                        continue
                    is_inbox_entry = _is_inbox_raw_entry(raw)
                    # call_human notify/reply stay on the default thread even when
                    # the activity row was written during inbox/heartbeat handling.
                    if (
                        thread_id != "inbox"
                        and is_inbox_entry
                        and raw.get("type") not in ("human_notify", "human_reply")
                    ):
                        continue
                    ts = raw.get("ts", "")
                    if before and ts >= before:
                        continue
                    if thread_id is not None:
                        meta = raw.get("meta", {})
                        has_thread_id = isinstance(meta, dict) and "thread_id" in meta
                        if strict_thread:
                            if not has_thread_id:
                                continue
                            if meta.get("thread_id") != thread_id:
                                continue
                        else:
                            default_tid = "inbox" if is_inbox_entry and thread_id == "inbox" else "default"
                            entry_tid = meta.get("thread_id", default_tid) if isinstance(meta, dict) else default_tid
                            if entry_tid != thread_id:
                                continue
                    if "from" in raw:
                        raw["from_person"] = raw.pop("from")
                    if "to" in raw:
                        raw["to_person"] = raw.pop("to")
                    try:
                        entry = ActivityEntry(
                            **{k: v for k, v in raw.items() if k in ActivityEntry.__dataclass_fields__}
                        )
                    except (TypeError, ValueError, KeyError):
                        logger.debug("Skipping malformed entry at line %d in %s", line_num, path)
                        continue
                    entry._line_number = line_num
                    day_entries.append(entry)
            except Exception:
                logger.exception("Failed to read activity log %s", path)

            entries = day_entries + entries
            files_scanned += 1
            if len(entries) >= target_raw or files_scanned >= max_files_scanned:
                break

        return entries

    def _entries_to_messages(
        self,
        entries: list[ActivityEntry],
        *,
        tool_detail: str = "full",
    ) -> list[dict[str, Any]]:
        """Convert raw activity entries to conversation messages (pair + nest tools)."""
        from core.activity.format import pair_tool_events
        from core.anima.emotion_tag import extract_emotion

        result_by_use_id: dict[int, ActivityEntry] = {
            id(ex.tool_use): ex.result for ex in pair_tool_events(entries) if ex.result is not None
        }

        messages: list[dict[str, Any]] = []
        pending_tool_calls: list[dict[str, Any]] = []
        user_aliases = _external_user_aliases()

        for e in entries:
            if e.type == "message_received":
                self._flush_tool_calls(messages, pending_tool_calls)
                messages.append(
                    {
                        "ts": e.ts,
                        "role": "human",
                        "content": e.content,
                        "from_person": user_aliases.get(e.from_person, e.from_person),
                        "to_person": e.to_person,
                        "source_key": _source_key_for_entry(e),
                        "tool_calls": [],
                    }
                )

            elif e.type == "message_sent":
                self._flush_tool_calls(messages, pending_tool_calls)
                messages.append(
                    {
                        "ts": e.ts,
                        "role": "assistant",
                        "content": e.content,
                        "from_person": "",
                        "to_person": e.to_person,
                        "source_key": _source_key_for_entry(e),
                        "tool_calls": [],
                    }
                )

            elif e.type == "response_sent":
                clean_content, emotion = extract_emotion(e.content)
                msg = {
                    "ts": e.ts,
                    "role": "assistant",
                    "content": clean_content,
                    "emotion": emotion if clean_content != e.content else None,
                    "from_person": "",
                    "to_person": e.to_person,
                    "source_key": _source_key_for_entry(e),
                    "tool_calls": [],
                }
                interim = e.meta.get("interim_texts")
                if isinstance(interim, list) and interim:
                    body, found = _split_interim_texts(clean_content, interim)
                    if found:
                        msg["content"] = body
                        msg["interim_texts"] = found
                if e.meta.get("thinking_text"):
                    msg["thinking_text"] = e.meta["thinking_text"]
                images = e.meta.get("images") or e.meta.get("artifacts") or []
                if isinstance(images, list) and images:
                    msg["images"] = images
                messages.append(msg)
                if pending_tool_calls:
                    msg["tool_calls"].extend(pending_tool_calls)
                    pending_tool_calls.clear()

            elif e.type == "tool_use":
                # human_notify card is the canonical display for call_human.
                if e.tool == "call_human":
                    continue
                tid = e.meta.get("tool_use_id", "")
                result_entry = result_by_use_id.get(id(e))
                raw_input = e.meta.get("args", e.content)
                raw_result = result_entry.content if result_entry else ""
                tc: dict[str, Any] = {
                    "tool_use_id": tid,
                    "tool_name": e.tool,
                    "input": _truncate_tool_field(raw_input, _TOOL_INPUT_TRUNCATE),
                    "result": _truncate_tool_field(raw_result, _TOOL_RESULT_TRUNCATE),
                    "is_error": (result_entry.meta.get("is_error", False) if result_entry else False),
                }
                if e.meta.get("blocked"):
                    tc["is_error"] = True
                    tc["result"] = t("activity.blocked", reason=e.meta.get("reason", ""))
                if tool_detail == "summary":
                    tc = _summarize_tool_call({**tc, "input": raw_input})
                pending_tool_calls.append(tc)

            elif e.type == "tool_result":
                pass

            elif e.type == "human_notify":
                self._flush_tool_calls(messages, pending_tool_calls)
                messages.append(
                    {
                        "ts": e.ts,
                        "role": "system",
                        "type": "human_notify",
                        "content": e.content,
                        "subject": e.meta.get("subject", ""),
                        "priority": e.meta.get("priority", "normal"),
                        "callback_id": e.meta.get("callback_id", ""),
                        "notification_id": e.meta.get("notification_id") or e.ts,
                        "replied": False,
                        "emotion": None,
                        "from_person": "",
                        "source_key": "call_human",
                        "tool_calls": [],
                    }
                )

            elif e.type == "human_reply":
                self._flush_tool_calls(messages, pending_tool_calls)
                messages.append(
                    {
                        "ts": e.ts,
                        "role": "human",
                        "type": "human_reply",
                        "content": e.content,
                        "from_person": user_aliases.get(e.from_person, e.from_person),
                        "via": e.via,
                        "notification_id": e.meta.get("notification_id", ""),
                        "callback_id": e.meta.get("callback_id", ""),
                        "source_key": "call_human_reply",
                        "tool_calls": [],
                    }
                )

            elif e.type == "voice_call":
                self._flush_tool_calls(messages, pending_tool_calls)
                messages.append(
                    {
                        "ts": e.ts,
                        "role": "assistant",
                        "type": "voice_call",
                        "content": e.summary or e.content,
                        "started_at": e.meta.get("started_at", ""),
                        "duration_seconds": e.meta.get("duration_seconds", 0),
                        "transcript": e.meta.get("transcript", []),
                        "source_key": "voice_call",
                        "tool_calls": [],
                    }
                )

            elif e.type == "heartbeat_start":
                self._flush_tool_calls(messages, pending_tool_calls)
                messages.append(
                    {
                        "ts": e.ts,
                        "role": "system",
                        "content": e.summary or t("activity.heartbeat_start"),
                        "from_person": "",
                        "source_key": _source_key_for_entry(e),
                        "tool_calls": [],
                        "_trigger": "heartbeat",
                    }
                )

            elif e.type == "heartbeat_end":
                self._flush_tool_calls(messages, pending_tool_calls)
                messages.append(
                    {
                        "ts": e.ts,
                        "role": "system",
                        "content": e.summary or e.content or t("activity.heartbeat_end"),
                        "from_person": "",
                        "source_key": _source_key_for_entry(e),
                        "tool_calls": [],
                        "_trigger": "heartbeat",
                    }
                )

            elif e.type == "cron_executed":
                self._flush_tool_calls(messages, pending_tool_calls)
                task_name = e.meta.get("task_name", "")
                content = e.summary or e.content or task_name or t("activity.cron_task_exec")
                messages.append(
                    {
                        "ts": e.ts,
                        "role": "system",
                        "content": content,
                        "from_person": "",
                        "source_key": _source_key_for_entry(e),
                        "tool_calls": [],
                        "_trigger": "cron",
                    }
                )

            elif e.type == "task_exec_start":
                self._flush_tool_calls(messages, pending_tool_calls)
                messages.append(
                    {
                        "ts": e.ts,
                        "role": "system",
                        "content": e.summary or t("activity.task_exec_start_label"),
                        "from_person": "",
                        "source_key": _source_key_for_entry(e),
                        "tool_calls": [],
                        "_trigger": "task",
                    }
                )

            elif e.type == "task_exec_end":
                self._flush_tool_calls(messages, pending_tool_calls)
                messages.append(
                    {
                        "ts": e.ts,
                        "role": "system",
                        "content": e.summary or e.content or t("activity.task_exec_end_label"),
                        "from_person": "",
                        "source_key": _source_key_for_entry(e),
                        "tool_calls": [],
                        "_trigger": "task",
                    }
                )

            elif e.type == "error":
                self._flush_tool_calls(messages, pending_tool_calls)
                messages.append(
                    {
                        "ts": e.ts,
                        "role": "system",
                        "content": t("activity.error_prefix") + (e.content or e.summary or ""),
                        "from_person": "",
                        "source_key": _source_key_for_entry(e),
                        "tool_calls": [],
                    }
                )

        self._flush_tool_calls(messages, pending_tool_calls)

        notifications = [msg for msg in messages if msg.get("type") == "human_notify"]
        for reply in (msg for msg in messages if msg.get("type") == "human_reply"):
            reply_ts = str(reply.get("ts") or "")
            candidates = [notify for notify in notifications if str(notify.get("ts") or "") <= reply_ts]
            if not candidates:
                continue

            notification_id = reply.get("notification_id")
            callback_id = reply.get("callback_id")
            matched = next(
                (
                    notify
                    for notify in reversed(candidates)
                    if (notification_id and notify.get("notification_id") == notification_id)
                    or (callback_id and notify.get("callback_id") == callback_id)
                ),
                None,
            )
            if matched is None:
                matched = next((notify for notify in reversed(candidates) if not notify["replied"]), candidates[-1])
            matched["replied"] = True

        # Answering in the normal chat (not via the reply button) also answers earlier notifications.
        if notifications:
            anima_names = self._sibling_anima_names()
            human_ts = [
                str(msg.get("ts") or "")
                for msg in messages
                if msg.get("role") == "human"
                and msg.get("type") != "human_reply"
                and msg.get("from_person")
                and msg.get("from_person") not in anima_names
            ]
            for notify in notifications:
                if not notify["replied"] and any(ts > str(notify.get("ts") or "") for ts in human_ts):
                    notify["replied"] = True

        if tool_detail == "summary":
            for message in messages:
                calls = message.get("tool_calls")
                if message.get("role") == "assistant" and calls:
                    message["tool_calls"] = [_summarize_tool_call(call) for call in calls]
                    message["tool_calls_detail"] = "lazy"

        return messages

    def _sibling_anima_names(self) -> set[str]:
        anima_dir = getattr(self, "anima_dir", None)
        try:
            return {p.name for p in anima_dir.parent.iterdir() if p.is_dir()} if anima_dir else set()
        except OSError:
            return set()

    @staticmethod
    def _flush_tool_calls(
        messages: list[dict[str, Any]],
        pending: list[dict[str, Any]],
    ) -> None:
        """Attach pending tool calls to the last assistant message."""
        if not pending:
            return
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                msg["tool_calls"].extend(pending)
                pending.clear()
                return
        pending.clear()

    @staticmethod
    def _group_into_sessions(
        messages: list[dict[str, Any]],
        gap_minutes: int,
    ) -> list[dict[str, Any]]:
        """Group messages into sessions by time gaps and trigger changes."""
        if not messages:
            return []

        gap_seconds = gap_minutes * 60
        sessions: list[dict[str, Any]] = []
        current_msgs: list[dict[str, Any]] = []
        current_trigger = "chat"

        for msg in messages:
            msg_trigger = msg.pop("_trigger", None)
            effective_trigger = msg_trigger or "chat"

            if current_msgs:
                prev_ts = current_msgs[-1]["ts"]
                trigger_changed = effective_trigger != current_trigger
                time_gap = time_diff(prev_ts, msg["ts"]) >= gap_seconds

                if trigger_changed or time_gap:
                    sessions.append(
                        {
                            "session_start": current_msgs[0]["ts"],
                            "session_end": current_msgs[-1]["ts"],
                            "trigger": current_trigger,
                            "messages": current_msgs,
                        }
                    )
                    current_msgs = []

            current_trigger = effective_trigger
            current_msgs.append(msg)

        if current_msgs:
            sessions.append(
                {
                    "session_start": current_msgs[0]["ts"],
                    "session_end": current_msgs[-1]["ts"],
                    "trigger": current_trigger,
                    "messages": current_msgs,
                }
            )

        return sessions
