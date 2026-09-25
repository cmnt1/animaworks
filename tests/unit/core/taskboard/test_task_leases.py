from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.memory.task_queue import TaskQueueManager
from core.schemas import TaskEntry
from core.taskboard.tasks import TaskStore, task_database_path
from core.time_utils import now_iso


def _entry(task_id: str, status: str = "pending", updated_at: str | None = None) -> TaskEntry:
    now = updated_at or now_iso()
    return TaskEntry(
        task_id=task_id,
        ts=now,
        source="human",
        original_instruction=f"Instruction for {task_id}",
        assignee="worker",
        status=status,
        summary=task_id,
        relay_chain=[],
        updated_at=now,
        meta={},
    )


def _runtime(tmp_path: Path, monkeypatch) -> tuple[Path, TaskStore]:
    runtime = tmp_path / "runtime"
    worker_dir = runtime / "animas" / "worker"
    worker_dir.mkdir(parents=True)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(runtime))
    return worker_dir, TaskStore(task_database_path(worker_dir))


def test_lease_acquire_conflict_renew_expire_and_release(tmp_path, monkeypatch):
    _, store = _runtime(tmp_path, monkeypatch)
    first = store.acquire_lease("worker", "t1", "rin", 1800)
    assert first is not None
    assert first["holder"] == "rin"
    assert store.get_lease("worker", "t1") == first
    assert store.acquire_lease("worker", "t1", "sora", 60) is None

    renewed = store.acquire_lease("worker", "t1", "rin", 3600)
    assert renewed is not None
    assert renewed["expires_at"] > first["expires_at"]

    with store.transaction() as db:
        expired = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        db.execute("UPDATE task_leases SET expires_at=? WHERE anima='worker' AND task_id='t1'", (expired,))
    assert store.get_lease("worker", "t1") is None
    assert store.acquire_lease("worker", "t1", "sora", 60)["holder"] == "sora"
    assert not store.release_lease("worker", "t1", "rin")
    assert store.release_lease("worker", "t1", "sora")
    assert store.get_lease("worker", "t1") is None


def test_leases_are_removed_by_apply_and_finish_terminal_paths(tmp_path, monkeypatch):
    worker_dir, store = _runtime(tmp_path, monkeypatch)
    store.apply("worker", _entry("direct").model_dump())
    assert store.acquire_lease("worker", "direct", "rin", 600)
    TaskQueueManager(worker_dir).update_status("direct", "cancelled")
    assert store.get_lease("worker", "direct") is None

    payload = {"task_id": "runner", "task_type": "llm", "description": "run"}
    runner_entry = _entry("runner")
    assert store.submit("worker", runner_entry, payload)
    attempt = store.claim("worker", "runner", {"pid": 1})
    assert attempt
    assert store.acquire_lease("worker", "runner", "rin", 600)
    assert store.finish(attempt["_attempt_token"], status="done", stop_kind="completed")
    assert store.get_lease("worker", "runner") is None


def test_board_rows_exclude_archived_terminal_and_include_alias_waiting(tmp_path, monkeypatch):
    _, store = _runtime(tmp_path, monkeypatch)
    old = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    store.apply("worker", _entry("todo", updated_at=old).model_dump())
    store.apply("worker", _entry("running", status="in_progress").model_dump())
    store.apply("worker", _entry("done", status="done").model_dump())
    with store.transaction() as db:
        db.execute("UPDATE tasks SET archived=1 WHERE anima='worker' AND task_id='done'")
        db.execute("INSERT INTO task_aliases VALUES('boss','tracking','worker','todo')")

    rows = store.board_rows(viewer="boss")
    assert [(row["task_id"], row["waiting"]) for row in rows] == [
        ("running", False),
        ("todo", False),
        ("tracking", True),
    ]
    assert all(row["task_id"] != "done" for row in rows)
    assert rows[0]["canonical_task_id"] == "running"


def test_board_rows_include_latest_attempt_details(tmp_path, monkeypatch):
    _, store = _runtime(tmp_path, monkeypatch)
    payload = {"task_id": "attempted", "task_type": "llm", "description": "run"}
    assert store.submit("worker", _entry("attempted"), payload)
    attempt = store.claim("worker", "attempted", {"pid": 1})
    assert attempt
    assert store.finish(attempt["_attempt_token"], status="pending", stop_kind="interrupted")
    row = store.board_rows(anima="worker")[0]
    assert row["started_at"]
    assert row["ended_at"]
    assert row["stop_kind"] == "interrupted"


def test_old_database_gets_lease_table_even_when_claim_control_exists(tmp_path):
    db_path = tmp_path / "shared" / "taskboard.sqlite3"
    db_path.parent.mkdir(parents=True)
    import sqlite3

    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE task_claim_control (anima TEXT PRIMARY KEY, paused INTEGER NOT NULL)")
    TaskStore(db_path)
    with sqlite3.connect(db_path) as db:
        assert db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_leases'").fetchone()
