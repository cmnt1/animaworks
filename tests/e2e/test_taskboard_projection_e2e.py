"""End-to-end: TaskBoard view derives directly from the canonical TaskStore.

There is no separate presentation metadata anymore — every board row comes from
the canonical ``tasks`` / ``task_aliases`` tables.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.tasks.board.models import BoardColumn
from core.tasks.board.tasks import TaskStore, task_database_path
from core.tasks.board.view import list_board
from core.tasks.queue import TaskQueueManager

pytestmark = pytest.mark.e2e


def test_taskboard_derives_columns_from_canonical_queue(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    sakura_dir = data_dir / "animas" / "sakura"
    (sakura_dir / "state").mkdir(parents=True)

    queue = TaskQueueManager(sakura_dir)
    queue.add_task(
        source="human",
        original_instruction="prepare rollout",
        assignee="sakura",
        summary="prepare rollout",
        task_id="task-rollout",
    )
    running = queue.add_task(
        source="human",
        original_instruction="review rollout",
        assignee="sakura",
        summary="review rollout",
        task_id="task-running",
    )
    queue.update_status(running.task_id, "in_progress")
    done = queue.add_task(
        source="human",
        original_instruction="ship old patch",
        assignee="sakura",
        summary="ship old patch",
        task_id="task-done",
    )
    queue.update_status(done.task_id, "done")

    store = TaskStore(task_database_path(sakura_dir))

    active = list_board(store, owner="sakura")
    assert {(row.task_id, row.column.value) for row in active} == {
        ("task-rollout", "todo"),
        ("task-running", "running"),
    }
    assert all(row.visibility == "active" for row in active)

    with_history = list_board(store, owner="sakura", history_limit=10)
    assert {row.task_id for row in with_history} == {"task-rollout", "task-running", "task-done"}
    done_row = next(row for row in with_history if row.task_id == "task-done")
    assert done_row.column == BoardColumn.DONE
    assert done_row.visibility == "archived"


def test_terminal_status_hides_from_active_board_since_tasks_are_ssot(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    sakura_dir = data_dir / "animas" / "sakura"
    (sakura_dir / "state").mkdir(parents=True)

    queue = TaskQueueManager(sakura_dir)
    task = queue.add_task(
        source="human",
        original_instruction="delegated work",
        assignee="sakura",
        summary="delegated work",
        task_id="task-complete",
    )

    updated = queue.update_status(task.task_id, "done", summary="delegated work done")
    assert updated is not None
    assert updated.status == "done"

    store = TaskStore(task_database_path(sakura_dir))

    active = list_board(store, owner="sakura")
    assert all(row.task_id != task.task_id for row in active)

    with_history = list_board(store, owner="sakura", history_limit=10)
    row = next(row for row in with_history if row.task_id == task.task_id)
    assert row.column == BoardColumn.DONE
    assert row.queue_status == "done"
