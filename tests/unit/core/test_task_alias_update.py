from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.exceptions import TaskOwnedByOther
from core.tasks.queue import TaskQueueManager


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _setup_delegation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, status: str = "pending"):
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    animas_dir = tmp_path / "animas"
    requester_dir = animas_dir / "requester"
    owner_dir = animas_dir / "owner"
    for anima_dir in (requester_dir, owner_dir):
        (anima_dir / "state").mkdir(parents=True)

    task_id = "delegated-task"
    owner = TaskQueueManager(owner_dir)
    owner.submit(
        {
            "task_type": "llm",
            "task_id": task_id,
            "title": "Delegated work",
            "description": "Do the delegated work",
            "reply_to": "requester",
            "relay_chain": ["requester"],
        }
    )
    if status == "waiting":
        attempt = owner.store.claim("owner", task_id, {"pid": 1})
        assert attempt is not None
        owner.store.finish(attempt["_attempt_token"], status="pending", stop_kind="interrupted")
    elif status != "pending":
        owner.update_status(task_id, status, summary=f"initial {status}")
    owner.store.alias("requester", task_id, "owner", task_id)
    return requester_dir, owner_dir, owner, task_id


def _task_snapshot(manager: TaskQueueManager, task_id: str) -> dict:
    with manager.store.reader() as db:
        row = db.execute(
            "SELECT entry_json, ready FROM tasks WHERE anima=? AND task_id=?",
            (manager.anima_dir.name, task_id),
        ).fetchone()
    entry = json.loads(row["entry_json"])
    return {
        "status": entry["status"],
        "summary": entry["summary"],
        "updated_at": entry["updated_at"],
        "ready": row["ready"],
        "meta": entry["meta"],
    }


def _handler(anima_dir: Path):
    from core.tooling.handler_skills import SkillsToolsMixin

    handler = object.__new__(SkillsToolsMixin)
    handler._anima_dir = anima_dir
    handler._anima_name = anima_dir.name
    handler._activity = MagicMock()
    return handler


def _notice_records(tmp_path: Path, actor: str, recipient: str) -> list[dict]:
    notice_file = tmp_path / "shared" / "task_notices" / f"{actor}__{recipient}.jsonl"
    return [json.loads(line) for line in notice_file.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_requester_pending_alias_is_rejected_without_mutation(tmp_path, monkeypatch):
    requester_dir, _, owner, task_id = _setup_delegation(tmp_path, monkeypatch, status="cancelled")
    before = _task_snapshot(owner, task_id)

    result = json.loads(_handler(requester_dir)._handle_update_task({"task_id": task_id, "status": "pending"}))

    assert result["error_type"] == "TaskOwnedByOther"
    assert "owner" in result["message"]
    assert "send_message" in result["message"]
    assert _task_snapshot(owner, task_id) == before


def test_requester_done_alias_is_rejected_without_mutation(tmp_path, monkeypatch):
    requester_dir, _, owner, task_id = _setup_delegation(tmp_path, monkeypatch)
    before = _task_snapshot(owner, task_id)

    result = json.loads(_handler(requester_dir)._handle_update_task({"task_id": task_id, "status": "done"}))

    assert result["error_type"] == "TaskOwnedByOther"
    assert _task_snapshot(owner, task_id) == before
    assert "completed_by" not in _task_snapshot(owner, task_id)["meta"]


def test_requester_pending_alias_cannot_reopen_done_task(tmp_path, monkeypatch):
    requester_dir, _, owner, task_id = _setup_delegation(tmp_path, monkeypatch, status="done")
    before = _task_snapshot(owner, task_id)

    result = json.loads(_handler(requester_dir)._handle_update_task({"task_id": task_id, "status": "pending"}))

    assert result["error_type"] == "TaskOwnedByOther"
    assert _task_snapshot(owner, task_id) == before
    with pytest.raises(TaskOwnedByOther, match="owner"):
        TaskQueueManager(requester_dir).update_status(task_id, "in_progress")


def test_requester_cannot_update_legacy_child_id_reference(tmp_path, monkeypatch):
    requester_dir, _, owner, task_id = _setup_delegation(tmp_path, monkeypatch)
    with owner.store.transaction() as db:
        db.execute("DELETE FROM task_aliases WHERE viewer='requester' AND alias=?", (task_id,))
        db.execute(
            "INSERT INTO task_aliases(viewer,alias,anima,task_id) VALUES(?,?,?,?)",
            ("requester", "legacy-tracking-id", "owner", task_id),
        )
    before = _task_snapshot(owner, task_id)

    with pytest.raises(TaskOwnedByOther, match="owner"):
        TaskQueueManager(requester_dir).update_status(task_id, "pending")

    assert _task_snapshot(owner, task_id) == before


def test_requester_cancel_alias_cancels_owner_task_and_queues_one_notice(tmp_path, monkeypatch):
    requester_dir, _, owner, task_id = _setup_delegation(tmp_path, monkeypatch)

    result = json.loads(
        _handler(requester_dir)._handle_update_task(
            {"task_id": task_id, "status": "cancelled", "summary": "Request no longer needed"}
        )
    )

    assert result["status"] == "cancelled"
    updated = owner.get_task_by_id(task_id)
    assert updated is not None
    assert updated.status == "cancelled"
    assert updated.summary == "Request no longer needed"
    notices = _notice_records(tmp_path, "requester", "owner")
    assert len(notices) == 1
    assert notices[0]["action"] == "cancel"
    assert "Request no longer needed" in notices[0]["detail"]
    assert "withdrew" in notices[0]["detail"] or "取り下げ" in notices[0]["detail"]


def test_owner_can_resume_waiting_task(tmp_path, monkeypatch):
    _, owner_dir, owner, task_id = _setup_delegation(tmp_path, monkeypatch, status="waiting")
    assert _task_snapshot(owner, task_id)["ready"] == 0

    result = json.loads(
        _handler(owner_dir)._handle_update_task({"task_id": task_id, "status": "pending", "resume": True})
    )

    assert result["status"] == "pending"
    assert owner.store.pending("owner")[0]["task_id"] == task_id
    assert _task_snapshot(owner, task_id)["ready"] == 1


def test_owner_cancel_notifies_requester_with_reason(tmp_path, monkeypatch):
    _, owner_dir, owner, task_id = _setup_delegation(tmp_path, monkeypatch)

    result = json.loads(
        _handler(owner_dir)._handle_update_task(
            {"task_id": task_id, "status": "cancelled", "summary": "Cannot complete safely"}
        )
    )

    assert result["status"] == "cancelled"
    notices = _notice_records(tmp_path, "owner", "requester")
    assert len(notices) == 1
    assert notices[0]["action"] == "cancel"
    assert "Cannot complete safely" in notices[0]["detail"]


@pytest.mark.anyio
async def test_internal_update_task_uses_alias_ownership_rules(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from server.routes.internal import create_internal_router

    requester_dir, _, owner, task_id = _setup_delegation(tmp_path, monkeypatch)
    app = FastAPI()
    app.include_router(create_internal_router(), prefix="/api")
    before = _task_snapshot(owner, task_id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/api/internal/update-task",
            json={"anima_name": requester_dir.name, "task_id": task_id, "status": "pending"},
        )
        assert denied.status_code == 409
        assert denied.json()["error_type"] == "TaskOwnedByOther"
        assert _task_snapshot(owner, task_id) == before

        cancelled = await client.post(
            "/api/internal/update-task",
            json={
                "anima_name": requester_dir.name,
                "task_id": task_id,
                "status": "cancelled",
                "summary": "Withdrawn by requester",
            },
        )

    assert cancelled.status_code == 200
    assert owner.get_task_by_id(task_id).status == "cancelled"
    notices = _notice_records(tmp_path, "requester", "owner")
    assert len(notices) == 1
    assert "Withdrawn by requester" in notices[0]["detail"]


def test_sandbox_host_fallback_preserves_task_owned_error(tmp_path, monkeypatch):
    import errno

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from core.tasks.dispatch import update_task
    from server.routes.internal import create_internal_router

    requester_dir, _, owner, task_id = _setup_delegation(tmp_path, monkeypatch)
    requester = TaskQueueManager(requester_dir)
    before = _task_snapshot(owner, task_id)
    app = FastAPI()
    app.include_router(create_internal_router(), prefix="/api")
    client = TestClient(app)

    def deny_local_store(_task_id: str, _status: str):
        raise PermissionError(errno.EROFS, "read-only task store")

    def post_to_host(endpoint: str, payload: dict):
        response = client.post(f"/api/internal/{endpoint}", json=payload)
        response.raise_for_status()
        return response.json()

    monkeypatch.setattr(requester, "assert_task_update_owner", deny_local_store)
    monkeypatch.setattr("core.tasks.dispatch._post_tasks", post_to_host)

    with pytest.raises(TaskOwnedByOther) as error:
        update_task(requester, task_id, "pending")

    assert error.value.owner == "owner"
    assert _task_snapshot(owner, task_id) == before
