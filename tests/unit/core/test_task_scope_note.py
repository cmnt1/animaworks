from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.tasks.dispatch import update_task
from core.tasks.queue import TaskQueueManager


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, reply_to: str = "requester"):
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    animas = tmp_path / "animas"
    requester_dir = animas / "requester"
    owner_dir = animas / "owner"
    for directory in (requester_dir, owner_dir):
        (directory / "state").mkdir(parents=True)
    manager = TaskQueueManager(owner_dir)
    manager.submit(
        {
            "task_type": "llm",
            "task_id": "work",
            "title": "Work",
            "description": "Do the work",
            "reply_to": reply_to,
            "relay_chain": ["requester"],
        }
    )
    manager.store.alias("requester", "work-alias", "owner", "work")
    return requester_dir, owner_dir, manager


def _handler(anima_dir: Path):
    from core.tooling.handler_skills import SkillsToolsMixin

    handler = object.__new__(SkillsToolsMixin)
    handler._anima_dir = anima_dir
    handler._anima_name = anima_dir.name
    handler._activity = MagicMock()
    return handler


def _snapshot(manager: TaskQueueManager) -> dict:
    with manager.store.reader() as db:
        row = db.execute(
            "SELECT entry_json,input_json FROM tasks WHERE anima=? AND task_id=?",
            (manager.anima_dir.name, "work"),
        ).fetchone()
    return {"entry": json.loads(row["entry_json"]), "input": json.loads(row["input_json"])}


def _messages(tmp_path: Path, recipient: str = "requester") -> list[dict]:
    inbox = tmp_path / "shared" / "inbox" / recipient
    if not inbox.is_dir():
        return []
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(inbox.glob("*.json"))]


def test_scope_note_appends_history_without_status_change(tmp_path, monkeypatch):
    requester_dir, owner_dir, manager = _setup(tmp_path, monkeypatch)
    before = _snapshot(manager)

    response = json.loads(
        _handler(owner_dir)._handle_update_task({"task_id": "work", "scope_note": "narrow to API only"})
    )

    assert response.get("error_type") is None
    assert response["status"] == "pending"
    after = _snapshot(manager)
    assert after["entry"]["status"] == before["entry"]["status"]
    assert after["entry"]["meta"]["scope_notes"] == [
        {"note": "narrow to API only", "at": after["entry"]["meta"]["scope_notes"][0]["at"]}
    ]
    assert after["input"] == before["input"]
    messages = _messages(tmp_path)
    assert len(messages) == 1
    assert messages[0]["intent"] == "report"
    assert messages[0]["meta"] == {"event": "task_scope_note", "task_id": "work"}
    assert "narrow to API only" in messages[0]["content"]
    assert requester_dir.name == "requester"


def test_two_scope_notes_keep_both_entries_and_send_twice(tmp_path, monkeypatch):
    _, owner_dir, manager = _setup(tmp_path, monkeypatch)
    handler = _handler(owner_dir)

    for note in ("first scope", "second scope"):
        response = json.loads(handler._handle_update_task({"task_id": "work", "scope_note": note}))
        assert response.get("error_type") is None

    notes = _snapshot(manager)["entry"]["meta"]["scope_notes"]
    assert [entry["note"] for entry in notes] == ["first scope", "second scope"]
    assert len(_messages(tmp_path)) == 2


def test_requester_cannot_write_scope_note(tmp_path, monkeypatch):
    requester_dir, _, manager = _setup(tmp_path, monkeypatch)
    before = _snapshot(manager)

    response = json.loads(
        _handler(requester_dir)._handle_update_task({"task_id": "work-alias", "scope_note": "requester note"})
    )

    assert response["error_type"] == "TaskOwnedByOther"
    assert _snapshot(manager) == before
    assert _messages(tmp_path) == []


def test_scope_note_to_self_does_not_notify(tmp_path, monkeypatch):
    _, owner_dir, manager = _setup(tmp_path, monkeypatch, reply_to="owner")

    response = json.loads(_handler(owner_dir)._handle_update_task({"task_id": "work", "scope_note": "self note"}))

    assert response.get("error_type") is None
    assert _snapshot(manager)["entry"]["meta"]["scope_notes"][0]["note"] == "self note"
    assert _messages(tmp_path) == []


def test_scope_note_with_status_change_still_notifies_once(tmp_path, monkeypatch):
    _, owner_dir, manager = _setup(tmp_path, monkeypatch)

    entry = update_task(manager, "work", "done", summary="finished", scope_note="only the API slice")

    assert entry is not None
    assert entry.status == "done"
    assert entry.meta["scope_notes"][0]["note"] == "only the API slice"
    assert len(_messages(tmp_path)) == 1


@pytest.mark.anyio
async def test_internal_update_task_accepts_waiting_and_scope_note(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from server.routes.internal import create_internal_router

    _, owner_dir, manager = _setup(tmp_path, monkeypatch)
    manager.submit(
        {
            "task_type": "llm",
            "task_id": "ref",
            "title": "Reference",
            "description": "Reference task",
        }
    )
    before = _snapshot(manager)
    monkeypatch.setattr("core.paths.get_animas_dir", lambda: owner_dir.parent)
    app = FastAPI()
    app.state.ws_manager = MagicMock()
    app.include_router(create_internal_router(), prefix="/api")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        waiting = await client.post(
            "/api/internal/update-task",
            json={
                "anima_name": "owner",
                "task_id": "work",
                "status": "pending",
                "waiting_for": {"kind": "task", "ref": "ref"},
            },
        )
        assert waiting.status_code == 200
        after_wait = _snapshot(manager)
        assert after_wait["entry"]["meta"]["waiting_for"] == {"kind": "task", "ref": "ref"}

        scoped = await client.post(
            "/api/internal/update-task",
            json={"anima_name": "owner", "task_id": "work", "scope_note": "narrowed via host"},
        )
        assert scoped.status_code == 200
        assert scoped.json()["task"]["status"] == "pending"
        assert scoped.json()["task"]["meta"]["scope_notes"][0]["note"] == "narrowed via host"
        assert len(_messages(tmp_path)) == 1

        invalid = await client.post(
            "/api/internal/update-task",
            json={
                "anima_name": "owner",
                "task_id": "work",
                "status": "done",
                "waiting_for": {"kind": "task", "ref": "ref"},
            },
        )
        assert invalid.status_code == 400
        assert invalid.json()["error_type"] == "InvalidArguments"
        after_invalid = _snapshot(manager)
        assert after_invalid["entry"]["status"] == "pending"
        assert after_invalid["entry"]["meta"]["waiting_for"] == {"kind": "task", "ref": "ref"}

    assert before["entry"]["status"] == "pending"
