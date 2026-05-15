"""Unit tests for semantic replay projection."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime, timedelta

from core.memory.activity import ActivityEntry, ActivityLogger, build_semantic_replay_events

BASE = "2026-05-14T12:00:00+09:00"

REQUIRED_FIELDS = {
    "id",
    "ts",
    "actor",
    "target",
    "kind",
    "label",
    "summary",
    "importance",
    "group_id",
    "group_type",
    "status",
    "source_event_ids",
    "raw_event_count",
    "line_type",
    "channel",
    "tool",
    "debug",
}


def _ts(offset_minutes: int = 0) -> str:
    return (datetime.fromisoformat(BASE) + timedelta(minutes=offset_minutes)).isoformat()


def _make(event_type: str, offset: int, *, anima_name: str = "sumire", **kwargs) -> ActivityEntry:
    entry = ActivityEntry(ts=_ts(offset), type=event_type, **kwargs)
    entry._anima_name = anima_name
    entry._line_number = offset + 1
    return entry


def _project(entries: list[ActivityEntry]) -> list[dict]:
    groups = ActivityLogger.group_by_trigger(entries)
    return build_semantic_replay_events(groups)


class TestSemanticReplayProjection:
    def test_message_contract_and_group_id_precedence(self) -> None:
        events = _project(
            [
                _make(
                    "message_received",
                    0,
                    from_person="admin",
                    content="Please handle review",
                    meta={"task_id": "task-123", "thread_id": "thread-999", "from_type": "human"},
                ),
                _make("response_sent", 1, content="I will handle it"),
            ]
        )

        first = events[0]
        assert set(first) == REQUIRED_FIELDS
        assert first["group_id"] == "task:task-123"
        assert first["group_type"] == "chat"
        assert first["kind"] == "message"
        assert first["actor"] == "admin"
        assert first["target"] == "sumire"
        assert first["importance"] == 4
        assert len(first["label"]) <= 48
        assert len(first["summary"]) <= 180

    def test_visible_delegate_tool_maps_to_semantic_delegation(self) -> None:
        events = _project(
            [
                _make("heartbeat_start", 0),
                _make(
                    "tool_use",
                    1,
                    tool="delegate_task",
                    summary="Implementation review requested",
                    to_person="rin",
                    meta={"tool_use_id": "tu-1", "task_name": "Replay semantic events"},
                ),
                _make(
                    "tool_result",
                    2,
                    tool="delegate_task",
                    content="queued",
                    meta={"tool_use_id": "tu-1"},
                ),
                _make("heartbeat_end", 3, summary="Done"),
            ]
        )

        delegation = next(event for event in events if event["kind"] == "delegation")
        assert delegation["tool"] == "delegate_task"
        assert delegation["target"] == "rin"
        assert delegation["line_type"] == "delegation"
        assert len(delegation["source_event_ids"]) == 2
        assert delegation["debug"]["suppressed_count"] == 1
        assert "tool_result" in delegation["debug"]["source_types"]
        assert all(event["kind"] != "tool_result" for event in events)

    def test_low_value_tool_group_falls_back_to_hidden_other_event(self) -> None:
        events = _project(
            [
                _make("tool_use", 0, tool="web_search", summary="raw search"),
                _make("tool_result", 1, tool="web_search", content="raw result"),
            ]
        )

        assert len(events) == 1
        event = events[0]
        assert event["kind"] == "other"
        assert event["label"] == "Tool activity"
        assert event["importance"] == 1
        assert event["debug"]["suppressed_count"] >= 1

    def test_task_update_completed_status(self) -> None:
        events = _project(
            [
                _make(
                    "task_updated",
                    0,
                    summary="Replay semantic event task closed",
                    meta={"status": "completed", "task_name": "Replay semantic events"},
                )
            ]
        )

        task = events[0]
        assert task["kind"] == "task"
        assert task["status"] == "completed"
        assert task["importance"] == 5
        assert task["group_id"] == "task:Replay semantic events"

    def test_error_event_is_high_importance_failed(self) -> None:
        events = _project([_make("error", 0, summary="Tool failed", meta={"repo": "animaworks", "number": 82})])

        error = events[0]
        assert error["kind"] == "error"
        assert error["status"] == "failed"
        assert error["importance"] == 5
        assert error["group_id"] == "issue:animaworks#82"
