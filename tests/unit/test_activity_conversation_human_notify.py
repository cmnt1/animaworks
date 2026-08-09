"""Unit tests for human_notify / human_reply in conversation view API."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

import pytest

from core.memory.activity import ActivityEntry, ActivityLogger


@pytest.fixture
def anima_dir(tmp_path: Path) -> Path:
    d = tmp_path / "animas" / "test-anima"
    (d / "activity_log").mkdir(parents=True)
    return d


@pytest.fixture
def activity_logger(anima_dir: Path) -> ActivityLogger:
    return ActivityLogger(anima_dir)


def _make_entry(
    type: str,
    ts: str,
    *,
    content: str = "",
    summary: str = "",
    **kwargs: object,
) -> ActivityEntry:
    return ActivityEntry(ts=ts, type=type, content=content, summary=summary, **kwargs)


class TestConversationTypes:
    def test_human_notify_in_conversation_types(self) -> None:
        assert "human_notify" in ActivityLogger._CONVERSATION_TYPES

    def test_human_reply_in_conversation_types(self) -> None:
        assert "human_reply" in ActivityLogger._CONVERSATION_TYPES

    def test_live_event_types_include_human_events(self) -> None:
        assert "human_notify" in ActivityLogger._LIVE_EVENT_TYPES
        assert "human_reply" in ActivityLogger._LIVE_EVENT_TYPES


class TestEntriesToMessages:
    def test_human_notify_message_shape(self, activity_logger: ActivityLogger) -> None:
        entries = [
            _make_entry(
                "human_notify",
                "2026-08-09T10:00:00+09:00",
                content="Please approve the deploy",
                meta={
                    "subject": "Deploy gate",
                    "priority": "high",
                    "callback_id": "cb-1",
                },
            ),
        ]
        messages = activity_logger._entries_to_messages(entries)
        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "system"
        assert msg["type"] == "human_notify"
        assert msg["content"] == "Please approve the deploy"
        assert msg["subject"] == "Deploy gate"
        assert msg["priority"] == "high"
        assert msg["callback_id"] == "cb-1"
        assert msg["source_key"] == "call_human"
        assert msg["tool_calls"] == []
        assert msg["from_person"] == ""

    def test_human_reply_message_shape(self, activity_logger: ActivityLogger) -> None:
        entries = [
            _make_entry(
                "human_reply",
                "2026-08-09T10:05:00+09:00",
                content="approve: looks good",
                from_person="alice",
                via="web",
            ),
        ]
        messages = activity_logger._entries_to_messages(entries)
        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "human"
        assert msg["type"] == "human_reply"
        assert msg["content"] == "approve: looks good"
        assert msg["from_person"] == "alice"
        assert msg["via"] == "web"
        assert msg["source_key"] == "call_human_reply"
        assert msg["tool_calls"] == []

    def test_call_human_tool_use_skipped(self, activity_logger: ActivityLogger) -> None:
        """call_human tool_use is not nested; human_notify card is canonical."""
        entries = [
            _make_entry(
                "response_sent",
                "2026-08-09T10:00:00+09:00",
                content="I will ask the human.",
            ),
            _make_entry(
                "tool_use",
                "2026-08-09T10:00:01+09:00",
                tool="call_human",
                meta={"tool_use_id": "tu_ch", "args": {"subject": "X", "body": "Y"}},
            ),
            _make_entry(
                "tool_result",
                "2026-08-09T10:00:02+09:00",
                tool="call_human",
                content='{"status":"sent"}',
                meta={"tool_use_id": "tu_ch"},
            ),
            _make_entry(
                "human_notify",
                "2026-08-09T10:00:03+09:00",
                content="Y",
                meta={"subject": "X", "priority": "normal"},
            ),
            _make_entry(
                "tool_use",
                "2026-08-09T10:00:04+09:00",
                tool="read_memory_file",
                meta={"tool_use_id": "tu_rm", "args": {"path": "x.md"}},
            ),
            _make_entry(
                "tool_result",
                "2026-08-09T10:00:05+09:00",
                content="ok",
                meta={"tool_use_id": "tu_rm"},
            ),
        ]
        messages = activity_logger._entries_to_messages(entries)
        # response_sent (with read_memory tool only) + human_notify
        assert len(messages) == 2
        assert messages[0]["role"] == "assistant"
        tool_names = [tc["tool_name"] for tc in messages[0]["tool_calls"]]
        assert "call_human" not in tool_names
        assert "read_memory_file" in tool_names
        assert messages[1]["type"] == "human_notify"


class TestConversationViewLoad:
    def test_human_events_appear_on_default_thread(
        self, activity_logger: ActivityLogger, anima_dir: Path
    ) -> None:
        activity_logger.log(
            "human_notify",
            content="Body text",
            meta={"subject": "Subj", "priority": "urgent", "callback_id": "cb-x"},
            ctx="chat",
        )
        activity_logger.log(
            "human_reply",
            content="approve",
            from_person="bob",
            via="slack",
            ctx="chat",
            meta={"callback_id": "cb-x", "decision": "approve"},
        )
        view = activity_logger.get_conversation_view(thread_id="default", limit=50)
        messages = [m for s in view["sessions"] for m in s["messages"]]
        types = [m.get("type") for m in messages]
        assert "human_notify" in types
        assert "human_reply" in types

    def test_inbox_ctx_human_events_still_on_default(
        self, activity_logger: ActivityLogger
    ) -> None:
        """human_notify/human_reply with inbox channel still appear on default."""
        activity_logger.log(
            "human_notify",
            content="Inbox-originated notify",
            channel="inbox",
            meta={
                "subject": "From inbox path",
                "priority": "normal",
                "trigger": "inbox",
            },
            ctx="inbox",
        )
        activity_logger.log(
            "human_reply",
            content="got it",
            from_person="carol",
            via="slack",
            channel="inbox",
            meta={"trigger": "inbox", "thread_ts": "1.2"},
            ctx="inbox",
        )
        # Ordinary inbox message_received must still be excluded from default.
        activity_logger.log(
            "message_received",
            content="secret inbox only",
            channel="inbox",
            meta={"trigger": "inbox"},
            ctx="inbox",
        )
        view = activity_logger.get_conversation_view(thread_id="default", limit=50)
        messages = [m for s in view["sessions"] for m in s["messages"]]
        contents = [m.get("content") for m in messages]
        assert "Inbox-originated notify" in contents
        assert "got it" in contents
        assert "secret inbox only" not in contents
