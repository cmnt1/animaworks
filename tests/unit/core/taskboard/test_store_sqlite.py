from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from core.paths import get_taskboard_db_path
from core.taskboard.models import AttentionVisibility, BoardColumn
from core.taskboard.store import TaskBoardStore


def test_get_taskboard_db_path_uses_shared_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

    assert get_taskboard_db_path() == tmp_path.resolve() / "shared" / "taskboard.sqlite3"


def test_store_uses_default_taskboard_db_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

    store = TaskBoardStore()

    assert store.db_path == tmp_path.resolve() / "shared" / "taskboard.sqlite3"
    assert store.db_path.exists()


def test_store_creates_wal_database_and_schema_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "shared" / "taskboard.sqlite3"

    TaskBoardStore(db_path)
    TaskBoardStore(db_path)

    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        tables = {
            row[0]
            for row in conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

    assert journal_mode == "wal"
    assert "taskboard_metadata" in tables
    assert "taskboard_events" in tables


def test_upsert_and_read_metadata_appends_events(tmp_path: Path) -> None:
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    created = store.upsert_metadata(
        anima_name="sakura",
        task_id="task-1",
        actor="alice",
        visibility="active",
        column=BoardColumn.WAITING,
        position=20.0,
        source_ref="task_queue:sakura:task-1",
    )
    updated = store.upsert_metadata(
        anima_name="sakura",
        task_id="task-1",
        actor="bob",
        column="blocked",
    )

    assert created.visibility == AttentionVisibility.ACTIVE
    assert updated.column == BoardColumn.BLOCKED
    assert updated.position == 20.0
    assert updated.updated_by == "bob"

    read_back = store.get_metadata("sakura", "task-1")
    assert read_back == updated

    events = store.list_events(anima_name="sakura", task_id="task-1")
    assert [event["event_type"] for event in events] == ["metadata_upserted", "column_changed"]
    assert events[1]["payload"]["updates"] == {"column": "blocked"}


def test_visibility_change_uses_specific_event_type(tmp_path: Path) -> None:
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    store.upsert_metadata(anima_name="sakura", task_id="task-1", actor="alice")
    archived = store.upsert_metadata(
        anima_name="sakura",
        task_id="task-1",
        actor="alice",
        visibility=AttentionVisibility.ARCHIVED,
    )

    assert archived.visibility == AttentionVisibility.ARCHIVED
    assert store.list_events(anima_name="sakura", task_id="task-1")[-1]["event_type"] == "archived"


def test_invalid_visibility_and_column_are_rejected(tmp_path: Path) -> None:
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    with pytest.raises(ValueError):
        store.upsert_metadata(anima_name="sakura", task_id="task-1", visibility="forgotten")

    with pytest.raises(ValueError):
        store.upsert_metadata(anima_name="sakura", task_id="task-2", column="triage")


def test_record_surface_increments_count_and_records_event(tmp_path: Path) -> None:
    store = TaskBoardStore(tmp_path / "taskboard.sqlite3")

    first = store.record_surface(anima_name="sakura", task_id="task-1", actor="runtime", notification_key="n1")
    second = store.record_surface(anima_name="sakura", task_id="task-1", actor="runtime")

    assert first.surface_count == 1
    assert first.notification_key == "n1"
    assert second.surface_count == 2
    assert second.notification_key == "n1"

    events = store.list_events(anima_name="sakura", task_id="task-1")
    assert [event["event_type"] for event in events] == ["surface_recorded", "surface_recorded"]
