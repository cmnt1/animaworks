from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.tasks.dispatch import publish_tasks, update_task
from core.tasks.queue import TaskQueueManager


@pytest.fixture
def anima_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    directory = tmp_path / "animas" / "worker"
    (directory / "state").mkdir(parents=True)
    return directory


def payload(task_id: str, **fields) -> dict:
    return {
        "task_type": "llm",
        "task_id": task_id,
        "title": task_id,
        "description": f"Do {task_id}",
        **fields,
    }


def _snapshot(manager: TaskQueueManager, task_id: str) -> dict:
    with manager.store.reader() as db:
        row = db.execute(
            "SELECT entry_json,ready FROM tasks WHERE anima=? AND task_id=?",
            (manager.anima_dir.name, task_id),
        ).fetchone()
    entry = json.loads(row["entry_json"])
    return {"entry": entry, "ready": row["ready"]}


def _wait_count(manager: TaskQueueManager) -> int:
    with manager.store.reader() as db:
        return db.execute("SELECT COUNT(*) FROM task_waits WHERE anima=?", (manager.anima_dir.name,)).fetchone()[0]


def _handler(anima_dir: Path):
    from core.tooling.handler_skills import SkillsToolsMixin

    handler = object.__new__(SkillsToolsMixin)
    handler._anima_dir = anima_dir
    handler._anima_name = anima_dir.name
    handler._activity = MagicMock()
    return handler


def _declare_wait(manager: TaskQueueManager, task_id: str, waiting_for: dict) -> None:
    entry = update_task(manager, task_id, "pending", waiting_for=waiting_for)
    assert entry is not None


@pytest.mark.parametrize("terminal", ["done", "cancelled"])
def test_explicit_resume_keeps_new_wait_declaration(anima_dir, terminal):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("ref"), payload("waiter")])
    manager.update_status("waiter", terminal)

    entry = update_task(manager, "waiter", "pending", resume=True, waiting_for={"kind": "task", "ref": "ref"})

    assert entry is not None and entry.status == "pending"
    assert _snapshot(manager, "waiter")["ready"] == 0
    assert _wait_count(manager) == 1
    manager.update_status("ref", "done")
    assert _snapshot(manager, "waiter")["ready"] == 1
    assert _wait_count(manager) == 0


def test_scope_note_cannot_bypass_explicit_resume_validation(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("completed")])
    manager.update_status("completed", "done")

    with pytest.raises(ValueError, match="resume requires"):
        update_task(manager, "completed", None, resume=True, scope_note="Repeat this work")

    entry = manager.get_task_by_id("completed")
    assert entry.status == "done"
    assert "scope_notes" not in entry.meta


@pytest.mark.parametrize("terminal", ["done", "cancelled"])
def test_task_wait_resumes_on_terminal_update(anima_dir, terminal):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("ref"), payload("waiter")])
    _declare_wait(manager, "waiter", {"kind": "task", "ref": "ref"})

    update_task(manager, "ref", terminal, summary="reference settled")

    resumed = _snapshot(manager, "waiter")
    assert resumed["ready"] == 1
    assert resumed["entry"]["meta"].get("waiting_for") is None
    assert _wait_count(manager) == 0
    assert "waiter" in {item["task_id"] for item in manager.store.pending("worker")}


def test_task_wait_resumes_when_reference_is_done(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("ref"), payload("waiter")])
    _declare_wait(manager, "waiter", {"kind": "task", "ref": "ref"})

    waiting = _snapshot(manager, "waiter")
    assert waiting["ready"] == 0
    assert waiting["entry"]["meta"]["waiting_for"] == {"kind": "task", "ref": "ref"}
    assert _wait_count(manager) == 1

    attempt = manager.store.claim("worker", "ref", {"pid": 1})
    assert manager.store.finish(attempt["_attempt_token"], status="done", stop_kind="normal")

    resumed = _snapshot(manager, "waiter")
    assert resumed["ready"] == 1
    assert resumed["entry"]["meta"].get("waiting_for") is None
    assert _wait_count(manager) == 0
    assert "waiter" in {item["task_id"] for item in manager.store.pending("worker")}


def test_task_wait_resumes_when_reference_is_cancelled(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("ref"), payload("waiter")])
    _declare_wait(manager, "waiter", {"kind": "task", "ref": "ref"})

    update_task(manager, "ref", "cancelled", summary="not needed")

    resumed = _snapshot(manager, "waiter")
    assert resumed["ready"] == 1
    assert _wait_count(manager) == 0


def test_task_wait_alias_reference_resolves_to_canonical(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("ref"), payload("waiter")])
    manager.store.alias("worker", "alias-ref", "worker", "ref")
    _declare_wait(manager, "waiter", {"kind": "task", "ref": "alias-ref"})

    attempt = manager.store.claim("worker", "ref", {"pid": 1})
    assert manager.store.finish(attempt["_attempt_token"], status="done", stop_kind="normal")

    assert _snapshot(manager, "waiter")["ready"] == 1
    assert _wait_count(manager) == 0


def test_time_wait_resumes_only_after_until(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("waiter")])
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    _declare_wait(manager, "waiter", {"kind": "time", "until": past})

    assert _snapshot(manager, "waiter")["entry"]["meta"]["waiting_for"] == {"kind": "time", "until": past}
    assert _snapshot(manager, "waiter")["ready"] == 0
    assert manager.store.satisfy_due_time_waits("worker", now=datetime.now(UTC)) == 1
    resumed = _snapshot(manager, "waiter")
    assert resumed["ready"] == 1
    assert resumed["entry"]["meta"].get("waiting_for") is None
    assert _wait_count(manager) == 0


def test_future_time_wait_is_left_alone(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("waiter")])
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    _declare_wait(manager, "waiter", {"kind": "time", "until": future})

    assert manager.store.satisfy_due_time_waits("worker", now=datetime.now(UTC)) == 0
    assert _snapshot(manager, "waiter")["ready"] == 0
    assert _wait_count(manager) == 1


def test_task_wait_can_name_a_reference_submitted_later(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("waiter")])
    _declare_wait(manager, "waiter", {"kind": "task", "ref": "later"})

    publish_tasks(anima_dir, [payload("later")])
    attempt = manager.store.claim("worker", "later", {"pid": 1})
    assert manager.store.finish(attempt["_attempt_token"], status="done", stop_kind="normal")

    assert _snapshot(manager, "waiter")["ready"] == 1


def test_task_wait_without_saved_input_emits_wakeup(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("ref")])
    manager.add_task(
        source="human",
        original_instruction="work without execution input",
        assignee="worker",
        summary="backlog work",
        task_id="waiter",
    )
    _declare_wait(manager, "waiter", {"kind": "task", "ref": "ref"})

    attempt = manager.store.claim("worker", "ref", {"pid": 1})
    assert manager.store.finish(attempt["_attempt_token"], status="done", stop_kind="normal")

    assert _snapshot(manager, "waiter")["ready"] == 0
    wakeups = manager.store.wakeups("worker")
    assert [row["reason"] for row in wakeups] == ["wait_satisfied"]
    assert wakeups[0]["task_id"] == "waiter"


@pytest.mark.parametrize("kind", ["message", "external"])
def test_message_and_external_waits_only_record_the_reason(anima_dir, kind):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("waiter")])
    _declare_wait(manager, "waiter", {"kind": kind, "ref": "someone"})

    waiting = _snapshot(manager, "waiter")
    assert waiting["ready"] == 0
    assert waiting["entry"]["meta"]["waiting_for"]["kind"] == kind
    assert _wait_count(manager) == 0


def test_done_clears_wait_and_late_reference_has_no_effect(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("ref"), payload("waiter")])
    _declare_wait(manager, "waiter", {"kind": "task", "ref": "ref"})

    update_task(manager, "waiter", "done", summary="finished manually")
    assert _wait_count(manager) == 0
    assert _snapshot(manager, "waiter")["entry"]["meta"].get("waiting_for") is None

    attempt = manager.store.claim("worker", "ref", {"pid": 1})
    assert manager.store.finish(attempt["_attempt_token"], status="done", stop_kind="normal")
    assert _snapshot(manager, "waiter")["entry"]["status"] == "done"
    assert _snapshot(manager, "waiter")["ready"] == 0


def test_wait_can_be_declared_after_returning_a_terminal_task_to_pending(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("ref"), payload("waiter")])
    update_task(manager, "waiter", "done", summary="finished")
    update_task(manager, "waiter", "cancelled", summary="withdrawn")

    _declare_wait(manager, "waiter", {"kind": "task", "ref": "ref"})
    waiting = _snapshot(manager, "waiter")
    assert waiting["entry"]["status"] == "pending"
    assert waiting["entry"]["meta"]["waiting_for"] == {"kind": "task", "ref": "ref"}
    assert waiting["ready"] == 0
    assert _wait_count(manager) == 1

    attempt = manager.store.claim("worker", "ref", {"pid": 1})
    assert manager.store.finish(attempt["_attempt_token"], status="done", stop_kind="normal")
    assert _snapshot(manager, "waiter")["ready"] == 1


def test_done_with_waiting_for_is_invalid_and_does_not_mutate(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("ref"), payload("waiter")])
    before = _snapshot(manager, "waiter")

    response = json.loads(
        _handler(anima_dir)._handle_update_task(
            {
                "task_id": "waiter",
                "status": "done",
                "waiting_for": {"kind": "task", "ref": "ref"},
            }
        )
    )

    assert response["error_type"] == "InvalidArguments"
    assert _snapshot(manager, "waiter") == before
    assert _wait_count(manager) == 0


def test_list_tasks_and_alias_projection_expose_waiting_for(tmp_path, monkeypatch):
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    animas = tmp_path / "animas"
    requester_dir = animas / "requester"
    owner_dir = animas / "owner"
    for directory in (requester_dir, owner_dir):
        (directory / "state").mkdir(parents=True)
    owner = TaskQueueManager(owner_dir)
    owner.submit(
        {
            "task_type": "llm",
            "task_id": "work",
            "title": "Work",
            "description": "Do work",
            "reply_to": "requester",
            "relay_chain": ["requester"],
        }
    )
    _declare_wait(owner, "work", {"kind": "task", "ref": "other"})
    owner.store.alias("requester", "work-alias", "owner", "work")

    requester = TaskQueueManager(requester_dir)
    alias = requester.store.read("requester")["work-alias"]
    assert alias.meta["waiting_for"] == {"kind": "task", "ref": "other"}

    listed = json.loads(_handler(requester_dir)._handle_list_tasks({"detail": False}))
    item = next(entry for entry in listed if entry["task_id"] == "work-alias")
    assert item["waiting_for"] == {"kind": "task", "ref": "other"}


def test_waiting_label_formats_time_readably():
    from core.tasks.waiting import waiting_label

    label = waiting_label({"kind": "time", "until": "2026-10-20T09:00:00+09:00"})
    assert "10/20 09:00" in label


def _declare_inside_attempt(manager: TaskQueueManager, task_id: str, waiting_for: dict) -> None:
    """The real flow: the running TaskExec declares the wait, then its attempt ends pending."""
    attempt = manager.store.claim("worker", task_id, {"pid": 1})
    _declare_wait(manager, task_id, waiting_for)
    assert manager.store.finish(attempt["_attempt_token"], status="pending", stop_kind="normal", wakeup=False)


def test_wait_declared_inside_attempt_survives_finish(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("ref"), payload("waiter")])
    _declare_inside_attempt(manager, "waiter", {"kind": "task", "ref": "ref"})

    assert _wait_count(manager) == 1
    assert _snapshot(manager, "waiter")["entry"]["meta"]["waiting_for"]["kind"] == "task"

    update_task(manager, "ref", "done", summary="settled")
    assert _snapshot(manager, "waiter")["ready"] == 1
    assert _wait_count(manager) == 0


def test_reference_ending_during_waiter_attempt_resumes_at_finish(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("ref"), payload("waiter")])
    attempt = manager.store.claim("worker", "waiter", {"pid": 1})
    _declare_wait(manager, "waiter", {"kind": "task", "ref": "ref"})
    update_task(manager, "ref", "done", summary="settled early")
    assert _wait_count(manager) == 1

    assert manager.store.finish(attempt["_attempt_token"], status="pending", stop_kind="normal", wakeup=False)
    assert _snapshot(manager, "waiter")["ready"] == 1
    assert _wait_count(manager) == 0


def test_wait_on_already_ended_reference_resumes_at_once(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("ref"), payload("waiter")])
    update_task(manager, "ref", "done", summary="already settled")

    _declare_wait(manager, "waiter", {"kind": "task", "ref": "ref"})
    assert _snapshot(manager, "waiter")["ready"] == 1
    assert _wait_count(manager) == 0


def test_time_wait_is_not_woken_while_attempt_runs(anima_dir):
    manager = TaskQueueManager(anima_dir)
    publish_tasks(anima_dir, [payload("waiter")])
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    attempt = manager.store.claim("worker", "waiter", {"pid": 1})
    _declare_wait(manager, "waiter", {"kind": "time", "ref": "later", "until": past})
    assert manager.store.satisfy_due_time_waits("worker") == 0
    assert _wait_count(manager) == 1
    assert manager.store.finish(attempt["_attempt_token"], status="pending", stop_kind="normal", wakeup=False)
    assert manager.store.satisfy_due_time_waits("worker") == 1
    assert _snapshot(manager, "waiter")["ready"] == 1
