from __future__ import annotations

import json
import os
import time
from pathlib import Path

from core.tasks.board.housekeeping import (
    _archive_current_state_for_housekeeping,
    _cleanup_current_state,
    cleanup_taskboard_stale_artifacts,
)
from core.tasks.queue import TaskQueueManager


def _anima_dir(data_dir: Path, name: str = "sakura") -> Path:
    anima_dir = data_dir / "animas" / name
    (anima_dir / "state").mkdir(parents=True, exist_ok=True)
    (anima_dir / "episodes").mkdir(parents=True, exist_ok=True)
    return anima_dir


def _write_json(path: Path, payload: dict[str, object], *, age_hours: int = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    if age_hours:
        old_ts = time.time() - (age_hours * 3600)
        os.utime(path, (old_ts, old_ts))
    return path


def test_background_running_cleanup(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = _anima_dir(data_dir)
    old_running = _write_json(
        anima_dir / "state" / "background_tasks" / "running.json",
        {"task_id": "running", "status": "running", "created_at": time.time() - (49 * 3600)},
    )
    missing_created_running = _write_json(
        anima_dir / "state" / "background_tasks" / "missing-created.json",
        {"task_id": "missing-created", "status": "running"},
        age_hours=100,
    )
    completed = _write_json(
        anima_dir / "state" / "background_tasks" / "completed.json",
        {"task_id": "completed", "status": "completed", "created_at": 1, "completed_at": 1},
        age_hours=100,
    )

    result = cleanup_taskboard_stale_artifacts(data_dir, 24, 48, 24)

    assert result["background_running_deleted"] == 1
    assert not old_running.exists()
    assert missing_created_running.exists()
    assert completed.exists()


def test_stale_current_state_archives_and_resets_when_no_active_task(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = _anima_dir(data_dir)
    state_path = anima_dir / "state" / "current_state.md"
    state_path.write_text("status: working\nold notes", encoding="utf-8")
    old_ts = time.time() - (25 * 3600)
    os.utime(state_path, (old_ts, old_ts))

    result = _cleanup_current_state(data_dir / "animas", 24)

    assert result["archived"] == 1
    assert state_path.read_text(encoding="utf-8") == "status: idle\n"
    episode = next((anima_dir / "episodes").glob("*.md"))
    assert "## Working notes archived by TaskBoard housekeeping" in episode.read_text(encoding="utf-8")
    assert "old notes" in episode.read_text(encoding="utf-8")


def test_current_state_is_kept_when_active_task_exists(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = _anima_dir(data_dir)
    TaskQueueManager(anima_dir).add_task(
        source="human",
        original_instruction="active task",
        assignee="sakura",
        summary="active task",
        task_id="active-task",
    )
    state_path = anima_dir / "state" / "current_state.md"
    state_path.write_text("status: working\nactive notes", encoding="utf-8")
    old_ts = time.time() - (25 * 3600)
    os.utime(state_path, (old_ts, old_ts))

    result = _cleanup_current_state(data_dir / "animas", 24)

    assert result["archived"] == 0
    assert result["active_visible"] == 1
    assert state_path.read_text(encoding="utf-8") == "status: working\nactive notes"


def test_current_state_archive_failure_leaves_original_unchanged(
    monkeypatch,
    tmp_path: Path,
) -> None:
    anima_dir = _anima_dir(tmp_path / "data")
    state_path = anima_dir / "state" / "current_state.md"
    state_path.write_text("status: working\nkeep me", encoding="utf-8")

    def fail_atomic_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("core.platform.atomic_io.atomic_write_text", fail_atomic_write)

    assert _archive_current_state_for_housekeeping(anima_dir, state_path, "status: working\nkeep me") == "error"
    assert state_path.read_text(encoding="utf-8") == "status: working\nkeep me"


def test_current_state_archive_skips_if_file_changed_after_read(tmp_path: Path) -> None:
    anima_dir = _anima_dir(tmp_path / "data")
    state_path = anima_dir / "state" / "current_state.md"
    state_path.write_text("status: working\nold", encoding="utf-8")
    old_ts = time.time() - 10
    os.utime(state_path, (old_ts, old_ts))
    expected_mtime = state_path.stat().st_mtime
    state_path.write_text("status: working\nfresh", encoding="utf-8")

    outcome = _archive_current_state_for_housekeeping(
        anima_dir,
        state_path,
        "status: working\nold",
        expected_mtime=expected_mtime,
    )

    assert outcome == "changed"
    assert state_path.read_text(encoding="utf-8") == "status: working\nfresh"
    assert not list((anima_dir / "episodes").glob("*.md"))


def test_legacy_descriptors_never_requeue_canonical_work(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    anima_dir = _anima_dir(data_dir)
    queue = TaskQueueManager(anima_dir)
    queue.add_task(
        source="human",
        original_instruction="finished work",
        assignee="sakura",
        summary="finished",
        task_id="old-task",
    )
    queue.update_status("old-task", "done")
    paths = [
        _write_json(
            anima_dir / "state" / "pending" / folder / "old-task.json",
            {"task_id": "old-task", "snoozed_until": "2020-01-01T00:00:00+09:00"},
            age_hours=1000,
        )
        for folder in ("processing", "deferred", "suppressed")
    ]
    result = cleanup_taskboard_stale_artifacts(data_dir, 24, 48, 24)
    assert all(path.exists() for path in paths)
    assert queue.get_task_by_id("old-task").status == "done"
    assert not any(key.startswith(("processing_", "deferred_", "suppressed_")) for key in result)
