from __future__ import annotations

import json
import os
import time
from datetime import timedelta
from pathlib import Path

import pytest

from core.config.models import HousekeepingConfig
from core.memory.maintenance.housekeeping import run_housekeeping
from core.tasks.queue import TaskQueueManager
from core.time_utils import now_local

pytestmark = pytest.mark.e2e


def _write_json(path: Path, payload: dict[str, object], *, age_hours: int = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    if age_hours:
        old_ts = time.time() - (age_hours * 3600)
        os.utime(path, (old_ts, old_ts))
    return path


async def test_housekeeping_preserves_legacy_llm_evidence_and_cleans_unrelated_artifacts(tmp_path: Path) -> None:
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
        housekeeping=HousekeepingConfig(
            pending_processing_stale_hours=24,
            background_running_stale_hours=48,
            current_state_stale_hours=24,
        ),
    )

    taskboard = results["taskboard_stale"]
    assert all(
        key not in taskboard
        for key in ("processing_recovered", "processing_queue_synced", "deferred_woken", "suppressed_deleted")
    )
    assert taskboard["background_running_deleted"] == 1
    assert taskboard["current_state_archived"] == 1

    assert (anima_dir / "state" / "pending" / "processing" / "recover-task.json").exists()
    assert (anima_dir / "state" / "pending" / "deferred" / "wake-task.json").exists()
    assert (anima_dir / "state" / "pending" / "suppressed" / "old-hidden.json").exists()
    assert not (anima_dir / "state" / "pending" / "wake-task.json").exists()
    assert not (anima_dir / "state" / "background_tasks" / "stale-running.json").exists()
    assert queue.get_task_by_id("recover-task").status == "in_progress"
    assert queue.store.pending("sakura") == []
    assert state_path.read_text(encoding="utf-8") == "status: idle\n"
    assert "stale idle notes" in next((idle_anima_dir / "episodes").glob("*.md")).read_text(encoding="utf-8")


async def test_housekeeping_no_longer_touches_presentation_metadata(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    (anima_dir / "state").mkdir(parents=True, exist_ok=True)
    (anima_dir / "episodes").mkdir(parents=True, exist_ok=True)

    queue = TaskQueueManager(anima_dir)
    queue.add_task(
        source="human",
        original_instruction="keep me",
        assignee="sakura",
        summary="keep me",
        task_id="live-task",
    )

    results = await run_housekeeping(
        data_dir,
        housekeeping=HousekeepingConfig(
            pending_processing_stale_hours=24,
            background_running_stale_hours=48,
            current_state_stale_hours=24,
        ),
    )

    taskboard = results["taskboard_stale"]
    assert "orphan_archived" not in taskboard
    assert "purged_deleted" not in taskboard
    # Canonical task is unaffected.
    assert queue.get_task_by_id("live-task").status == "pending"
    # No presentation metadata table is created (tasks are the only board source).
    shared_db = data_dir / "shared" / "taskboard.sqlite3"
    if shared_db.exists():
        import sqlite3

        with sqlite3.connect(shared_db) as db:
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "taskboard_metadata" not in names
        assert "taskboard_events" not in names
