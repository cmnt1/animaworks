from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.room_manager import RoomManager
from server.routes.room import create_room_router


def _client(tmp_path: Path) -> tuple[TestClient, RoomManager]:
    manager = RoomManager(tmp_path / "meetings")
    app = FastAPI()
    app.state.room_manager = manager
    app.include_router(create_room_router())
    return TestClient(app), manager


def test_update_room_title_route_preserves_conversation(tmp_path: Path):
    client, manager = _client(tmp_path)
    room = manager.create_room(
        participants=["sakura", "kanna"],
        chair="sakura",
        created_by="taka",
        title="old",
    )
    manager.append_message(room.room_id, "taka", "human", "hello")

    response = client.patch(f"/rooms/{room.room_id}", json={"title": "AFF-012"})

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "AFF-012"
    assert data["conversation"][0]["text"] == "hello"


def test_list_rooms_includes_session_metadata(tmp_path: Path):
    client, manager = _client(tmp_path)
    room = manager.create_room(
        participants=["sakura", "kanna"],
        chair="sakura",
        created_by="taka",
        title="planning",
    )
    manager.append_message(room.room_id, "taka", "human", "hello")

    response = client.get("/rooms?include_closed=true")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["room_id"] == room.room_id
    assert data[0]["message_count"] == 1
    assert data[0]["last_message_at"]


def test_create_room_route_preserves_project_metadata(tmp_path: Path):
    client, _manager = _client(tmp_path)

    response = client.post(
        "/rooms",
        json={
            "participants": ["sakura", "kanna"],
            "chair": "sakura",
            "title": "AFF-012 ブログ立ち上げ機械",
            "project_department": "アフィリエイト",
            "project_task_code": "AFF-012",
            "project_note_path": r"E:\OneDriveBiz\Obsidian\_notes\Projects\ブログ立ち上げ機械.md",
            "project_task_title": "ブログ立ち上げ機械",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["project_department"] == "アフィリエイト"
    assert data["project_task_code"] == "AFF-012"
    assert data["project_task_title"] == "ブログ立ち上げ機械"


def test_project_tasks_route_reads_obsidian_projects_db(tmp_path: Path, monkeypatch):
    projects_dir = tmp_path / "_notes" / "Projects"
    projects_dir.mkdir(parents=True)
    (projects_dir / "ブログ立ち上げ機械.md").write_text(
        "---\nタスク名: ブログ立ち上げ機械\nカテゴリ: アフィリエイト\nステータス: 進行中\nタスクコード: AFF-012\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANIMAWORKS_OBSIDIAN_VAULT", str(tmp_path))
    client, _manager = _client(tmp_path)

    response = client.get("/rooms/project-tasks")

    assert response.status_code == 200
    data = response.json()
    assert data["departments"] == ["アフィリエイト"]
    assert data["tasks"][0]["task_code"] == "AFF-012"


def test_extract_action_items_route(tmp_path: Path, monkeypatch):
    client, manager = _client(tmp_path)
    room = manager.create_room(
        participants=["sakura", "rin"],
        chair="sakura",
        created_by="taka",
        title="planning",
    )
    manager.append_message(room.room_id, "sakura", "chair", "rinが資料を作る")

    async def fake_llm(*args, **kwargs):
        return '[{"assignee": "rin", "task": "資料を作る"}]'

    monkeypatch.setattr("core.memory._llm_utils.one_shot_completion", fake_llm)

    response = client.post(f"/rooms/{room.room_id}/action-items/extract", json={})

    assert response.status_code == 200
    assert response.json()["items"] == [{"assignee": "rin", "text": "資料を作る"}]


def test_save_action_items_route(tmp_path: Path):
    client, manager = _client(tmp_path)
    room = manager.create_room(
        participants=["sakura", "rin"],
        chair="sakura",
        created_by="taka",
    )

    response = client.put(
        f"/rooms/{room.room_id}/action-items",
        json={"items": [{"assignee": "rin", "text": "T1"}]},
    )

    assert response.status_code == 200
    items = response.json()["action_items"]
    assert items[0]["assignee"] == "rin"
    assert items[0]["status"] == "draft"


def test_save_action_items_route_rejects_non_participant(tmp_path: Path):
    client, manager = _client(tmp_path)
    room = manager.create_room(
        participants=["sakura", "rin"],
        chair="sakura",
        created_by="taka",
    )

    response = client.put(
        f"/rooms/{room.room_id}/action-items",
        json={"items": [{"assignee": "stranger", "text": "T1"}]},
    )

    assert response.status_code == 400


def test_dispatch_action_items_route(tmp_path: Path, monkeypatch):
    client, manager = _client(tmp_path)
    room = manager.create_room(
        participants=["sakura", "rin"],
        chair="sakura",
        created_by="taka",
    )
    manager.set_action_items(room.room_id, [{"assignee": "rin", "text": "T1"}])

    shared_dir = tmp_path / "shared"
    monkeypatch.setattr("server.routes.room.get_shared_dir", lambda: shared_dir)

    response = client.post(f"/rooms/{room.room_id}/action-items/dispatch", json={})

    assert response.status_code == 200
    assert response.json()["delivered"] == 1
    assert list((shared_dir / "inbox" / "rin").glob("*.json"))
