from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
import json
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

from core.memory.task_queue import TaskQueueManager
from core.time_utils import now_local
from core.tooling.handler import ToolHandler
from core.tooling.heartbeat_snapshot import build_heartbeat_observe_snapshot


def test_heartbeat_observe_snapshot_returns_fixed_health_sections(data_dir: Path, make_anima) -> None:
    hikaru = make_anima("hikaru")
    kanna = make_anima("kanna")

    inbox_dir = data_dir / "shared" / "inbox" / "hikaru"
    inbox_dir.mkdir(parents=True)
    (inbox_dir / "msg1.json").write_text(
        json.dumps(
            {
                "id": "msg1",
                "thread_id": "thread-1",
                "from_person": "sakura",
                "to_person": "hikaru",
                "type": "message",
                "intent": "report",
                "source": "anima",
                "priority": "high",
                "timestamp": "2026-05-24T20:34:00+09:00",
                "content": "Owner instruction body preview test",
                "meta": {"task_id": "task-1"},
            }
        ),
        encoding="utf-8",
    )

    (hikaru / "state" / "background_notifications").mkdir()
    (hikaru / "state" / "background_notifications" / "bg1.md").write_text("done", encoding="utf-8")
    (hikaru / "state" / "current_state.md").write_text("Working on owner check", encoding="utf-8")
    (hikaru / "state" / "pending").mkdir(exist_ok=True)
    (hikaru / "state" / "pending" / "stale.md").write_text("pending", encoding="utf-8")
    (hikaru / "state" / "task_results").mkdir()
    (hikaru / "state" / "task_results" / "done.md").write_text("Task result preview", encoding="utf-8")

    deadline = (now_local() - timedelta(minutes=5)).isoformat()
    manager = TaskQueueManager(hikaru)
    task = manager.add_task(
        source="human",
        original_instruction="Check report",
        assignee="hikaru",
        summary="Owner check",
        deadline=deadline,
    )
    manager.update_status(task.task_id, "blocked", summary="Waiting for evidence")

    activity_dir = kanna / "activity_log"
    activity_dir.mkdir()
    (activity_dir / "2026-05-23.jsonl").write_text(
        json.dumps({"ts": "2026-05-23T05:00:00+09:00", "type": "heartbeat_end", "summary": "OK"})
        + "\n",
        encoding="utf-8",
    )

    snapshot = build_heartbeat_observe_snapshot(
        hikaru,
        peers=["kanna", "../bad"],
        recent_minutes=120,
        max_items=3,
    )

    assert snapshot["status"] == "ok"
    assert snapshot["scope"]["mutates"] is False
    assert snapshot["scope"]["arbitrary_paths"] is False
    assert snapshot["inbox"]["unread_count"] == 1
    assert snapshot["inbox"]["message_previews"] == [
        {
            "file": "msg1.json",
            "mtime": snapshot["inbox"]["message_previews"][0]["mtime"],
            "size_bytes": snapshot["inbox"]["message_previews"][0]["size_bytes"],
            "status": "ok",
            "id": "msg1",
            "thread_id": "thread-1",
            "from": "sakura",
            "to": "hikaru",
            "type": "message",
            "intent": "report",
            "source": "anima",
            "priority": "high",
            "timestamp": "2026-05-24T20:34:00+09:00",
            "routing_hint": "human_or_owner",
            "content_preview": "Owner instruction body preview test",
            "meta_keys": ["task_id"],
        }
    ]
    assert snapshot["background_notifications"]["count"] == 1
    assert snapshot["current_state"]["content_preview"] == "Working on owner check"
    assert snapshot["pending_files"]["direct_count"] == 1
    assert snapshot["task_results"]["count"] == 1
    assert snapshot["task_results"]["samples"][0]["content_preview"] == "Task result preview"
    assert snapshot["task_queue"]["active_count"] == 1
    assert snapshot["task_queue"]["active_by_status"] == {"blocked": 1}
    assert snapshot["task_queue"]["overdue_count"] == 1
    assert set(snapshot["peer_activity"]["peers"]) == {"kanna"}
    assert snapshot["peer_activity"]["peers"]["kanna"]["latest_event"]["type"] == "heartbeat_end"


def test_tool_handler_exposes_heartbeat_snapshot(data_dir: Path, make_anima) -> None:
    hikaru = make_anima("hikaru")
    handler = ToolHandler(anima_dir=hikaru, memory=MagicMock(), tool_registry=[])

    result = json.loads(handler.handle("heartbeat_observe_snapshot", {"max_items": 2}))

    assert result["status"] == "ok"
    assert result["anima"] == "hikaru"
    assert "task_queue" in result
    assert "inbox" in result
    assert "current_state" in result
    assert "task_results" in result
