from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.tasks.board.readiness import require_task_store_ready
from core.tasks.board.tasks import TaskStore, task_database_path
from core.tasks.queue import TaskQueueManager


def _anima(tmp_path: Path) -> Path:
    anima = tmp_path / "runtime" / "animas" / "fixture"
    (anima / "state").mkdir(parents=True)
    return anima


def test_readiness_on_fresh_runtime_is_read_only(tmp_path: Path):
    anima = _anima(tmp_path)
    require_task_store_ready(anima)
    assert not task_database_path(anima).exists()

    assert TaskQueueManager(anima).load_active_tasks() == {}
    assert task_database_path(anima).exists()


def test_runtime_read_does_not_implicitly_import_legacy_state(tmp_path: Path):
    anima = _anima(tmp_path)
    legacy_files = [
        anima / "state" / "task_queue.jsonl",
        anima / "state" / "task_queue_archive.jsonl",
        anima / "state" / "pending" / "job.json",
    ]
    for path in legacy_files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"task_id":"legacy"}\n', encoding="utf-8")
    originals = {path: path.read_bytes() for path in legacy_files}

    assert TaskQueueManager(anima).load_active_tasks() == {}
    assert {path: path.read_bytes() for path in legacy_files} == originals
    with sqlite3.connect(task_database_path(anima)) as db:
        assert db.execute("SELECT count(*) FROM task_imports").fetchone()[0] == 0
    with pytest.raises(RuntimeError, match="task-store migrate"):
        require_task_store_ready(anima)


def test_explicit_import_marker_allows_canonical_reads_without_replay(tmp_path: Path):
    anima = _anima(tmp_path)
    store = TaskStore(task_database_path(anima))
    store.import_legacy(anima)
    legacy = anima / "state/task_queue.jsonl"
    legacy.write_text("late obsolete write must not be revived\n")
    require_task_store_ready(anima)

    assert TaskQueueManager(anima).load_active_tasks() == {}
    assert not TaskQueueManager(anima).store.pending(anima.name)
