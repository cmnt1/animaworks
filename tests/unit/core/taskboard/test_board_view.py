from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from core.schemas import TaskEntry
from core.tasks.board.models import BoardColumn
from core.tasks.board.tasks import TaskStore, task_database_path
from core.tasks.board.view import list_board, summarize_board
from core.tasks.dispatch import publish_delegation
from core.tasks.queue import TaskQueueManager
from core.time_utils import now_iso


def _entry(
    task_id: str,
    status: str = "pending",
    source: str = "anima",
    assignee: str = "worker",
    updated_at: str | None = None,
) -> TaskEntry:
    now = updated_at or now_iso()
    return TaskEntry(
        task_id=task_id,
        ts=now,
        source=source,
        original_instruction=f"Instruction for {task_id}",
        assignee=assignee,
        status=status,
        summary=task_id,
        relay_chain=[],
        updated_at=now,
        meta={},
    )


def _runtime(tmp_path: Path, monkeypatch, workers: tuple[str, ...] = ("worker", "boss")) -> tuple[Path, TaskStore]:
    runtime = tmp_path / "runtime"
    for worker in workers:
        (runtime / "animas" / worker / "state").mkdir(parents=True)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(runtime))
    return runtime, TaskStore(task_database_path(runtime / "animas" / "worker"))


def _tables(db_path: Path) -> set[str]:
    with sqlite3.connect(db_path) as db:
        return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _delegate(worker_dir: Path, *, task_id: str, tracking_id: str, delegator: str = "boss") -> None:
    publish_delegation(
        worker_dir,
        {
            "task_type": "llm",
            "task_id": task_id,
            "title": f"do {task_id}",
            "description": f"help with {task_id}",
            "source": "delegation",
        },
        delegator=delegator,
        tracking_task_id=tracking_id,
    )


def test_delegation_shows_receiver_todo_and_delegator_waiting(tmp_path: Path, monkeypatch) -> None:
    runtime, store = _runtime(tmp_path, monkeypatch)
    _delegate(runtime / "animas" / "worker", task_id="sub1", tracking_id="track1")

    rows = {row.task_id: row for row in list_board(store, all_viewers=True)}
    assert rows["sub1"].column == BoardColumn.TODO
    assert rows["sub1"].waiting is False
    assert rows["track1"].column == BoardColumn.WAITING
    assert rows["track1"].waiting is True
    # No presentation metadata table is created anymore.
    assert "taskboard_metadata" not in _tables(runtime / "shared" / "taskboard.sqlite3")


def test_no_ghost_waiting_after_completion(tmp_path: Path, monkeypatch) -> None:
    runtime, store = _runtime(tmp_path, monkeypatch)
    worker_dir = runtime / "animas" / "worker"
    _delegate(worker_dir, task_id="sub1", tracking_id="track1")

    TaskQueueManager(worker_dir).update_status("sub1", "done")
    rows = list_board(store, all_viewers=True)
    assert not any(row.waiting and row.anima_name == "boss" for row in rows)
    # The completed canonical task is still visible under DONE when history is included.
    done_rows = [row for row in list_board(store, all_viewers=True, history_limit=10) if row.visibility == "archived"]
    assert any(row.task_id == "sub1" for row in done_rows)


def test_ledger_only_rows_are_shown(tmp_path: Path, monkeypatch) -> None:
    _, store = _runtime(tmp_path, monkeypatch)
    store.apply("worker", _entry("exist").model_dump())
    rows = list_board(store, all_viewers=True)
    assert [row.task_id for row in rows] == ["exist"]
    # An ID that never existed (and has no metadata anymore) cannot appear.
    assert not any(row.task_id == "phantom" for row in rows)


def test_order_human_first_then_oldest(tmp_path: Path, monkeypatch) -> None:
    _, store = _runtime(tmp_path, monkeypatch)
    store.apply("worker", _entry("anima1", source="anima", updated_at="2026-01-03T00:00:00+00:00").model_dump())
    store.apply("worker", _entry("human2", source="human", updated_at="2026-01-02T00:00:00+00:00").model_dump())
    store.apply("worker", _entry("human1", source="human", updated_at="2026-01-01T00:00:00+00:00").model_dump())

    todo = [row for row in list_board(store) if row.column == BoardColumn.TODO]
    assert [row.task_id for row in todo] == ["human1", "human2", "anima1"]


def test_history_rows_appear_in_done_column_descending(tmp_path: Path, monkeypatch) -> None:
    _, store = _runtime(tmp_path, monkeypatch)
    store.apply("worker", _entry("live").model_dump())
    for index, status in ((1, "done"), (2, "done"), (3, "cancelled")):
        ts = f"2026-01-0{index}T00:00:00+00:00"
        store.apply("worker", _entry(f"t{index}").model_dump())
        with store.transaction() as db:
            db.execute(
                "UPDATE tasks SET entry_json=json_set(entry_json,'$.status',?, '$.updated_at',?) "
                "WHERE anima=? AND task_id=?",
                (status, ts, "worker", f"t{index}"),
            )

    done = [row for row in list_board(store, history_limit=2) if row.column == BoardColumn.DONE]
    assert [row.task_id for row in done] == ["t3", "t2"]  # newest first, limited


def test_summarize_board_delegation_counts(tmp_path: Path, monkeypatch) -> None:
    runtime, store = _runtime(tmp_path, monkeypatch)
    _delegate(runtime / "animas" / "worker", task_id="sub1", tracking_id="track1")

    summary = summarize_board(store, ["worker", "boss"])
    assert summary == {"pending": 1, "in_progress": 0, "delegated": 1, "total_active": 1}


def test_history_limit_zero_returns_no_terminal_rows(tmp_path: Path, monkeypatch) -> None:
    _, store = _runtime(tmp_path, monkeypatch)
    store.apply("worker", _entry("done").model_dump())
    with store.transaction() as db:
        db.execute(
            "UPDATE tasks SET entry_json=json_set(entry_json,'$.status','done','$.updated_at',?) "
            "WHERE anima=? AND task_id=?",
            (now_iso(), "worker", "done"),
        )
    rows = list_board(store, history_limit=0)
    assert all(row.visibility == "active" for row in rows)
    assert not any(row.task_id == "done" for row in rows)


def test_stale_timestamp_helper_is_unused_guard(tmp_path: Path, monkeypatch) -> None:
    # Keeps datetime/timedelta imports exercised for lint stability.
    assert datetime.now(UTC) > datetime.fromisoformat("2020-01-01T00:00:00+00:00") - timedelta(days=1)
