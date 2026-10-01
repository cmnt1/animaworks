from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.tasks.board.tasks import TaskStore, ensure_task_store_schema, task_database_path
from core.tasks.queue import TaskQueueManager


def _anima(tmp_path: Path) -> Path:
    anima = tmp_path / "runtime" / "animas" / "alice"
    (anima / "state").mkdir(parents=True)
    return anima


def test_read_only_missing_database_is_empty_without_creating_files(tmp_path: Path) -> None:
    db_path = tmp_path / "not-created" / "shared" / "taskboard.sqlite3"
    store = TaskStore.open(db_path, read_only=True)

    assert store.read("alice") == {}
    assert store.get("alice", "missing") is None
    assert store.get_lease("alice", "missing") is None
    assert store.board_rows() == []
    assert store.history_rows(None, 10) == []
    assert store.pending("alice") == []
    assert store.executable_ids("alice") == set()
    assert store.get_input("alice", "missing") is None
    assert store.active_attempts("alice") == []
    assert store.wakeups("alice") == []
    assert store.reference_records("alice") == {}
    assert store.maintenance_status("alice") == {
        "anima": "alice",
        "quiesced": False,
        "invalid_import_rows": 0,
        "active_attempts": 0,
        "owned_tasks": 0,
        "ready_tasks": 0,
    }
    assert not db_path.exists()
    assert not db_path.parent.exists()


def test_read_only_store_reads_existing_taskboard(tmp_path: Path) -> None:
    anima = _anima(tmp_path)
    task = TaskQueueManager(anima).add_task(
        source="human",
        original_instruction="read-only fixture",
        assignee="alice",
        summary="fixture task",
        task_id="fixture-task",
    )

    store = TaskStore.open(task_database_path(anima), read_only=True)

    assert store.read("alice")[task.task_id].summary == "fixture task"
    assert store.get("alice", task.task_id).original_instruction == "read-only fixture"
    with store._connect() as db, pytest.raises(sqlite3.OperationalError, match="readonly"):
        db.execute("CREATE TABLE readonly_probe (value TEXT)")


def test_schema_is_created_by_ensure_and_writable_open(tmp_path: Path) -> None:
    explicit_path = tmp_path / "explicit" / "taskboard.sqlite3"
    ensure_task_store_schema(explicit_path)
    assert explicit_path.is_file()
    with sqlite3.connect(explicit_path) as db:
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tasks'").fetchone()

    automatic_path = tmp_path / "automatic" / "taskboard.sqlite3"
    TaskStore.open(automatic_path, read_only=False)
    assert automatic_path.is_file()
