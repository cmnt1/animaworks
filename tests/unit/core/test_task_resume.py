"""Resume path: requeue a task under the same task_id using its saved input.

Covers the canonical resume entry point (update_task with resume=True), the
TaskStore.resume boundary, and the CLI `task resume` backend.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.memory.task_queue import TaskQueueManager
from core.tasks_dispatch import publish_tasks, update_task


@pytest.fixture
def anima_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    directory = tmp_path / "animas" / "worker"
    (directory / "state").mkdir(parents=True)
    return directory


def payload(task_id: str = "task-one", **fields) -> dict:
    return {
        "task_type": "llm",
        "task_id": task_id,
        "title": "Task",
        "description": "Complete this task",
        **fields,
    }


def test_resume_cancelled_task_requeues_same_id(anima_dir):
    original = payload()
    publish_tasks(anima_dir, [original])
    manager = TaskQueueManager(anima_dir)
    manager.update_status("task-one", "cancelled", summary="gave up")

    entry = update_task(manager, "task-one", "pending", resume=True)

    assert entry.task_id == "task-one"
    assert entry.status == "pending"
    assert manager.store.pending("worker") == [original]
    assert manager.store.get_input("worker", "task-one") == original


def test_resume_ended_pending_returns_to_ready(anima_dir):
    original = payload()
    publish_tasks(anima_dir, [original])
    manager = TaskQueueManager(anima_dir)
    attempt = manager.store.claim("worker", "task-one", {"pid": 1})
    manager.store.finish(attempt["_attempt_token"], status="pending", stop_kind="interrupted")
    assert manager.store.pending("worker") == []

    entry = update_task(manager, "task-one", "pending", resume=True)

    assert entry.status == "pending"
    assert manager.store.pending("worker") == [original]


def test_resume_preserves_original_execution_input(anima_dir):
    original = payload(description="大事な確定指示" * 50)
    publish_tasks(anima_dir, [original])
    manager = TaskQueueManager(anima_dir)
    manager.update_status("task-one", "cancelled", summary="retry")

    update_task(manager, "task-one", "pending", resume=True)

    assert manager.store.get_input("worker", "task-one") == original


def test_resume_rejects_active_attempt(anima_dir):
    publish_tasks(anima_dir, [payload()])
    manager = TaskQueueManager(anima_dir)
    manager.store.claim("worker", "task-one", {"pid": 1})

    with pytest.raises(ValueError, match="active attempt"):
        update_task(manager, "task-one", "pending", resume=True)


def test_resume_rejects_backlog_without_input(anima_dir):
    manager = TaskQueueManager(anima_dir)
    manager.add_task(
        source="human",
        original_instruction="some work",
        assignee="worker",
        summary="some work",
        task_id="task-one",
    )

    with pytest.raises(ValueError, match="submit_tasks"):
        update_task(manager, "task-one", "pending", resume=True)


def test_resume_missing_id_raises_not_found(anima_dir):
    manager = TaskQueueManager(anima_dir)

    with pytest.raises(ValueError, match="Task not found: missing"):
        manager.store.resume("worker", "missing")


def test_resume_rejects_stale_attempt_identity(anima_dir):
    from core.taskboard.tasks import attempt_scope

    publish_tasks(anima_dir, [payload()])
    manager = TaskQueueManager(anima_dir)
    manager.store.claim("worker", "task-one", {"pid": 1})
    stale = {"anima": "worker", "task_id": "task-one", "token": "stale-token"}

    with attempt_scope(stale), pytest.raises(ValueError, match="Stale task attempt cannot resume itself"):
        manager.store.resume("worker", "task-one")


def test_resume_requires_pending_status(anima_dir):
    publish_tasks(anima_dir, [payload()])
    manager = TaskQueueManager(anima_dir)

    with pytest.raises(ValueError, match="resume requires status"):
        update_task(manager, "task-one", "done", resume=True)


def test_update_without_resume_does_not_clear_ready(anima_dir):
    original = payload()
    publish_tasks(anima_dir, [original])
    manager = TaskQueueManager(anima_dir)
    attempt = manager.store.claim("worker", "task-one", {"pid": 1})
    manager.store.finish(attempt["_attempt_token"], status="pending", stop_kind="interrupted")
    assert manager.store.pending("worker") == []

    entry = update_task(manager, "task-one", "pending")

    assert entry is not None
    assert manager.store.pending("worker") == []


def test_cli_resume_success_and_not_found(anima_dir, capsys):
    from cli.commands.task_cmd import _cmd_resume

    original = payload()
    publish_tasks(anima_dir, [original])
    manager = TaskQueueManager(anima_dir)
    manager.update_status("task-one", "cancelled", summary="retry")

    _cmd_resume(SimpleNamespace(task_id="task-one"), manager)
    out = json.loads(capsys.readouterr().out)
    assert out["task_id"] == "task-one"
    assert out["status"] == "pending"
    assert manager.store.pending("worker") == [original]

    with pytest.raises(SystemExit) as stopped:
        _cmd_resume(SimpleNamespace(task_id="missing"), manager)
    assert stopped.value.code != 0
    assert "task not found or invalid status" in capsys.readouterr().err
