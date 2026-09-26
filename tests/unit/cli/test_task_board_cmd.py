from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta

import pytest

from cli.commands.task_cmd import register_task_command
from core.tasks.queue import TaskQueueManager


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    runtime_dir = tmp_path / "runtime"
    animas = runtime_dir / "animas"
    for name in ("worker", "boss", "other"):
        (animas / name).mkdir(parents=True)
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(runtime_dir))
    monkeypatch.delenv("ANIMAWORKS_ANIMA_DIR", raising=False)
    return runtime_dir, animas


def _invoke(argv: list[str]) -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    register_task_command(subparsers)
    args = parser.parse_args(["task", *argv])
    args.func(args)


def _add(runtime, task_id: str, *, owner: str = "worker", summary: str | None = None):
    _, animas = runtime
    queue = TaskQueueManager(animas / owner)
    return queue, queue.add_task(
        source="human",
        original_instruction=f"Instruction {task_id}",
        assignee=owner,
        summary=summary or task_id,
        task_id=task_id,
    )


def test_board_order_status_alias_and_stale_filter(runtime, monkeypatch, capsys):
    worker, todo = _add(runtime, "todo-old", summary="An old task")
    old = (datetime.now(UTC) - timedelta(days=5)).isoformat()
    worker.store.apply("worker", {"_event": "update", "task_id": todo.task_id, "updated_at": old})
    worker.add_task(
        source="human", original_instruction="Run", assignee="worker", summary="Running task", task_id="running"
    )
    worker.update_status("running", "in_progress")
    _add(runtime, "delegated-child")
    worker.store.alias("boss", "waiting-alias", "worker", "delegated-child")
    worker.add_delegated_task(
        original_instruction="Delegate",
        assignee="boss",
        summary="Waiting for subordinate",
        task_id="waiting-task",
    )

    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(runtime[1] / "boss"))
    _invoke(["board", "--json"])
    own_board = json.loads(capsys.readouterr().out)
    assert own_board["counts"] == {"todo": 0, "running": 0, "waiting": 1}
    assert own_board["tasks"][0]["task_id"] == "waiting-alias"

    monkeypatch.delenv("ANIMAWORKS_ANIMA_DIR")
    _invoke(["board", "--all", "--json", "--limit", "10"])
    all_board = json.loads(capsys.readouterr().out)
    ordered = [row["task_id"] for row in all_board["tasks"]]
    assert ordered[:3] == ["running", "todo-old", "delegated-child"]
    assert ordered[-1] == "waiting-task"
    assert all_board["counts"] == {"todo": 2, "running": 1, "waiting": 1}

    _invoke(["board", "--all", "--stale", "2", "--json"])
    stale = json.loads(capsys.readouterr().out)
    assert [row["task_id"] for row in stale["tasks"]] == ["todo-old"]


def test_other_task_requires_lease_and_cancel_updates_owner_queue(runtime, monkeypatch, capsys):
    queue, _ = _add(runtime, "foreign-task")
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(runtime[1] / "boss"))
    with pytest.raises(SystemExit) as denied:
        _invoke(["cancel", "foreign-task", "--reason", "obsolete"])
    assert denied.value.code != 0

    _invoke(["claim", "foreign-task", "--ttl", "30m"])
    assert "Lease acquired" in capsys.readouterr().out
    _invoke(["cancel", "foreign-task", "--reason", "obsolete"])
    assert queue.get_task_by_id("foreign-task").status == "cancelled"
    assert queue.get_task_by_id("foreign-task").meta["notes"][-1]["text"] == "obsolete"
    assert queue.store.get_lease("worker", "foreign-task") is None


def test_owner_can_mark_own_task_done_without_lease(runtime, monkeypatch, capsys):
    queue, _ = _add(runtime, "own-task")
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(runtime[1] / "worker"))
    _invoke(["done", "own-task", "--note", "verified", "--json"])
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "done"
    assert queue.get_task_by_id("own-task").status == "done"
    assert queue.store.get_lease("worker", "own-task") is None


def test_note_appends_without_discarding_existing_notes(runtime, monkeypatch, capsys):
    queue, entry = _add(runtime, "noted-task")
    queue.update_meta("noted-task", {"notes": [{"ts": "earlier", "by": "worker", "text": "keep"}]})
    monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(runtime[1] / "worker"))
    _invoke(["note", "noted-task", "new note", "--json"])
    capsys.readouterr()
    notes = queue.get_task_by_id("noted-task").meta["notes"]
    assert notes[0] == {"ts": "earlier", "by": "worker", "text": "keep"}
    assert notes[1]["text"] == "new note"


def test_show_resolves_alias_id(runtime, monkeypatch, capsys):
    _add(runtime, "child-task")
    _, animas = runtime
    store = TaskQueueManager(animas / "worker").store
    store.alias("boss", "tracking-id", "worker", "child-task")
    _invoke(["show", "tracking-id", "--json"])
    details = json.loads(capsys.readouterr().out)
    assert details["requested_id"] == "tracking-id"
    assert details["owner"] == "worker"
    assert details["task_id"] == "child-task"
    assert details["aliases"] == [{"viewer": "boss", "alias": "tracking-id"}]
