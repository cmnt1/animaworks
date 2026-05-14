from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core._anima_inbox import _rescue_regenerate_pending
from core.memory.task_queue import TaskQueueManager
from core.taskboard.models import AttentionVisibility
from core.taskboard.store import TaskBoardStore
from core.tooling.handler_skills import SkillsToolsMixin

pytestmark = pytest.mark.e2e


def _make_handler(anima_dir: Path) -> SkillsToolsMixin:
    handler = object.__new__(SkillsToolsMixin)
    handler._anima_dir = anima_dir
    handler._anima_name = anima_dir.name
    handler._activity = MagicMock()
    handler._pending_executor_wake = None
    return handler


def test_taskboard_blocks_retry_and_delegation_rescue_resurrection(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    (anima_dir / "state").mkdir(parents=True, exist_ok=True)

    queue = TaskQueueManager(anima_dir)
    entry = queue.add_task(
        source="human",
        original_instruction="do not resurrect this task",
        assignee="sakura",
        summary="do not resurrect this task",
        task_id="archived1234",
        meta={"task_desc": {"title": "do not resurrect this task"}},
    )
    queue.update_status(entry.task_id, "failed", summary="FAILED: old failure")

    store = TaskBoardStore(data_dir / "shared" / "taskboard.sqlite3")
    store.upsert_metadata(
        anima_name="sakura",
        task_id=entry.task_id,
        visibility=AttentionVisibility.ARCHIVED,
    )

    retry_result = json.loads(
        _make_handler(anima_dir)._handle_update_task({"task_id": entry.task_id, "status": "pending"})
    )
    _rescue_regenerate_pending(
        anima_dir,
        entry.task_id,
        SimpleNamespace(content="delegated work", from_person="manager"),
    )

    assert retry_result["error_type"] == "TaskSuppressed"
    assert not (anima_dir / "state" / "pending" / f"{entry.task_id}.json").exists()
    assert not (anima_dir / "state" / "pending" / "deferred" / f"{entry.task_id}.json").exists()
    assert TaskQueueManager(anima_dir).get_task_by_id(entry.task_id).status == "failed"


def test_delegation_rescue_recreates_future_snoozed_task_only_in_deferred(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    (anima_dir / "state").mkdir(parents=True, exist_ok=True)

    queue = TaskQueueManager(anima_dir)
    entry = queue.add_task(
        source="human",
        original_instruction="wake later",
        assignee="sakura",
        summary="wake later",
        task_id="snoozed1234",
    )
    TaskBoardStore(data_dir / "shared" / "taskboard.sqlite3").upsert_metadata(
        anima_name="sakura",
        task_id=entry.task_id,
        visibility=AttentionVisibility.SNOOZED,
        snoozed_until=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )

    _rescue_regenerate_pending(
        anima_dir,
        entry.task_id,
        SimpleNamespace(content="delegated work", from_person="manager"),
    )

    assert not (anima_dir / "state" / "pending" / f"{entry.task_id}.json").exists()
    assert (anima_dir / "state" / "pending" / "deferred" / f"{entry.task_id}.json").exists()
