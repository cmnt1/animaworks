from __future__ import annotations

import json
import os
import time
from datetime import timedelta
from pathlib import Path

import pytest

from core.memory.housekeeping import run_housekeeping
from core.memory.task_queue import TaskQueueManager
from core.taskboard.store import TaskBoardStore
from core.time_utils import now_local

pytestmark = pytest.mark.e2e


def _write_json(path: Path, payload: dict[str, object], *, age_hours: int = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    if age_hours:
        old_ts = time.time() - (age_hours * 3600)
        os.utime(path, (old_ts, old_ts))
    return path


async def test_taskboard_housekeeping_remediates_stale_runtime_artifacts_end_to_end(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    idle_anima_dir = data_dir / "animas" / "mei"
    for path in (anima_dir, idle_anima_dir):
        (path / "state").mkdir(parents=True, exist_ok=True)
        (path / "episodes").mkdir(parents=True, exist_ok=True)

    queue = TaskQueueManager(anima_dir)
    queue.add_task(
        source="human",
        original_instruction="recover processing",
        assignee="sakura",
        summary="recover processing",
        status="in_progress",
        task_id="recover-task",
    )
    _write_json(
        anima_dir / "state" / "pending" / "processing" / "recover-task.json",
        {"task_id": "recover-task"},
        age_hours=25,
    )
    _write_json(
        anima_dir / "state" / "pending" / "deferred" / "wake-task.json",
        {"task_id": "wake-task", "snoozed_until": (now_local() - timedelta(minutes=5)).isoformat()},
    )
    _write_json(
        anima_dir / "state" / "pending" / "suppressed" / "old-hidden.json",
        {"task_id": "old-hidden"},
        age_hours=31 * 24,
    )
    _write_json(
        anima_dir / "state" / "background_tasks" / "stale-running.json",
        {
            "task_id": "stale-running",
            "status": "running",
            "created_at": time.time() - (49 * 3600),
        },
    )

    state_path = idle_anima_dir / "state" / "current_state.md"
    state_path.write_text("status: working\nstale idle notes", encoding="utf-8")
    old_ts = time.time() - (25 * 3600)
    os.utime(state_path, (old_ts, old_ts))

    results = await run_housekeeping(
        data_dir,
        pending_processing_stale_hours=24,
        background_running_stale_hours=48,
        current_state_stale_hours=24,
        taskboard_suppressed_retention_days=30,
    )

    taskboard = results["taskboard_stale"]
    assert taskboard["processing_recovered"] == 1
    assert taskboard["processing_queue_synced"] == 1
    assert taskboard["deferred_woken"] == 1
    assert taskboard["suppressed_deleted"] == 1
    assert taskboard["background_running_deleted"] == 1
    assert taskboard["current_state_archived"] == 1

    assert (anima_dir / "state" / "pending" / "failed" / "recover-task.json").exists()
    assert (anima_dir / "state" / "pending" / "wake-task.json").exists()
    assert not (anima_dir / "state" / "pending" / "suppressed" / "old-hidden.json").exists()
    assert not (anima_dir / "state" / "background_tasks" / "stale-running.json").exists()
    assert queue.get_task_by_id("recover-task").status == "failed"
    assert state_path.read_text(encoding="utf-8") == "status: idle\n"
    assert "stale idle notes" in next((idle_anima_dir / "episodes").glob("*.md")).read_text(encoding="utf-8")

    events = TaskBoardStore(data_dir / "shared" / "taskboard.sqlite3").list_events(
        anima_name="sakura",
        task_id="recover-task",
    )
    assert events[-1]["event_type"] == "stale_processing_recovered"
