"""Finished tasks close their TaskBoard cards, including the requester's waiting card."""

from __future__ import annotations

from pathlib import Path

from core.tasks.board.store import TaskBoardStore
from core.tasks.queue import TaskQueueManager


def _setup(tmp_path: Path) -> tuple[TaskQueueManager, TaskBoardStore]:
    anima = tmp_path / "runtime" / "animas" / "worker"
    anima.mkdir(parents=True)
    queue = TaskQueueManager(anima)
    board = TaskBoardStore(queue.store.db_path)
    queue.submit({"task_id": "t1", "title": "work", "description": "do it"})
    board.upsert_metadata(anima_name="worker", task_id="t1", visibility="active", column="todo")
    board.upsert_metadata(anima_name="boss", task_id="t1", visibility="active", column="waiting")
    return queue, board


def _visibility(board: TaskBoardStore, anima: str, task_id: str) -> str:
    card = board.get_metadata(anima, task_id)
    assert card is not None
    return str(card.visibility.value if hasattr(card.visibility, "value") else card.visibility)


def test_runner_finish_archives_owner_and_requester_cards(tmp_path: Path) -> None:
    queue, board = _setup(tmp_path)
    attempt = queue.store.claim("worker", "t1", {"pid": 1, "process_start_time": 1})
    assert attempt
    assert queue.store.finish(attempt["_attempt_token"], status="done", stop_kind="completed")
    assert _visibility(board, "worker", "t1") == "archived"
    assert _visibility(board, "boss", "t1") == "archived"


def test_update_to_cancelled_archives_aliased_requester_card(tmp_path: Path) -> None:
    queue, board = _setup(tmp_path)
    with queue.store.transaction() as db:
        db.execute("INSERT INTO task_aliases VALUES('boss','tracking','worker','t1')")
    board.upsert_metadata(anima_name="boss", task_id="tracking", visibility="active", column="waiting")
    queue.update_status("t1", "cancelled")
    assert _visibility(board, "boss", "tracking") == "archived"
    assert _visibility(board, "boss", "t1") == "archived"


def test_requeue_keeps_cards_active(tmp_path: Path) -> None:
    queue, board = _setup(tmp_path)
    attempt = queue.store.claim("worker", "t1", {"pid": 1, "process_start_time": 1})
    assert attempt
    assert queue.store.finish(attempt["_attempt_token"], status="pending", stop_kind="interrupted")
    assert _visibility(board, "boss", "t1") == "active"
