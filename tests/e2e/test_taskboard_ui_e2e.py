from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.memory.task_queue import TaskQueueManager
from core.taskboard.store import TaskBoardStore

pytestmark = pytest.mark.e2e


def _create_app(tmp_path: Path, anima_names: list[str]):
    animas_dir = tmp_path / "animas"
    shared_dir = tmp_path / "shared"
    for name in anima_names:
        anima_dir = animas_dir / name
        (anima_dir / "state").mkdir(parents=True, exist_ok=True)
        (anima_dir / "identity.md").write_text(f"# {name}\n", encoding="utf-8")
    (shared_dir / "channels").mkdir(parents=True, exist_ok=True)

    with (
        patch("server.app.ProcessSupervisor") as mock_sup_cls,
        patch("server.app.load_config") as mock_cfg,
        patch("server.app.WebSocketManager") as mock_ws_cls,
        patch("server.app.load_auth") as mock_auth,
    ):
        cfg = MagicMock()
        cfg.setup_complete = True
        cfg.server.base_path = ""
        mock_cfg.return_value = cfg

        auth_cfg = MagicMock()
        auth_cfg.auth_mode = "local_trust"
        mock_auth.return_value = auth_cfg

        supervisor = MagicMock()
        supervisor.get_all_status.return_value = {}
        supervisor.get_process_status.return_value = {"status": "stopped", "pid": None}
        supervisor.is_scheduler_running.return_value = False
        supervisor.scheduler = None
        mock_sup_cls.return_value = supervisor

        ws_manager = MagicMock()
        ws_manager.active_connections = []
        mock_ws_cls.return_value = ws_manager

        from server.app import create_app

        app = create_app(animas_dir, shared_dir)

    import server.app as server_app

    local_auth = MagicMock()
    local_auth.auth_mode = "local_trust"
    server_app.load_auth = lambda: local_auth
    return app


def _seed_taskboard(app) -> tuple[str, str]:
    alice_queue = TaskQueueManager(app.state.animas_dir / "alice")
    bob_queue = TaskQueueManager(app.state.animas_dir / "bob")
    todo = alice_queue.add_task(
        source="human",
        original_instruction="prepare UI rollout",
        assignee="alice",
        summary="prepare UI rollout",
        task_id="task-ui",
    )
    running = bob_queue.add_task(
        source="human",
        original_instruction="verify TaskBoard action",
        assignee="bob",
        summary="verify TaskBoard action",
        task_id="task-action",
    )
    bob_queue.update_status(running.task_id, "in_progress")
    TaskBoardStore(app.state.shared_dir / "taskboard.sqlite3").upsert_metadata(
        anima_name="bob",
        task_id=running.task_id,
        actor="planner",
        column="running",
        position=1000,
    )
    return todo.task_id, running.task_id


async def test_taskboard_route_static_assets_and_api_smoke(tmp_path: Path) -> None:
    app = _create_app(tmp_path, ["alice", "bob"])
    _seed_taskboard(app)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        index_resp = await client.get("/")
        page_resp = await client.get("/_v/test/pages/task-board.js")
        utils_resp = await client.get("/_v/test/pages/task-board-utils.js")
        css_resp = await client.get("/_v/test/styles/task-board.css")
        board_resp = await client.get("/api/task-board", params={"include_missing": "true"})

    assert index_resp.status_code == 200
    assert '#/task-board' in index_resp.text
    assert 'data-route="/task-board"' in index_resp.text
    assert "task-board.css" in index_resp.text
    assert '#/board' in index_resp.text

    assert page_resp.status_code == 200
    assert "/api/task-board" in page_resp.text
    assert "REFRESH_MS = 30000" in page_resp.text
    assert "document.visibilityState" in page_resp.text
    assert "escapeAttr" in page_resp.text
    assert "_renderToken" in page_resp.text
    assert 'method: "PATCH"' in page_resp.text
    assert "position: (index + 1) * 1000" in page_resp.text
    assert 'reasonRequired: action === "expire" || action === "tombstone"' in page_resp.text
    assert 'setCustomValidity(t("taskboard.reason_required"))' in page_resp.text
    assert 'confirmRequired: action === "tombstone"' in page_resp.text
    assert "taskboard.mark_done" not in page_resp.text
    assert "/api/channels" not in page_resp.text
    assert "../pages/board" not in page_resp.text

    assert utils_resp.status_code == 200
    assert 'if (action === "archive") return "archived";' in utils_resp.text
    assert 'if (action === "tombstone") return "tombstoned";' in utils_resp.text
    assert "toISOString().slice(0, 16)" not in utils_resp.text
    assert "getHours()" in utils_resp.text
    assert css_resp.status_code == 200
    assert "@media (max-width: 720px)" in css_resp.text
    assert ".taskboard-mobile-tabs" in css_resp.text

    assert board_resp.status_code == 200
    task_ids = {task["task_id"] for task in board_resp.json()["tasks"]}
    assert {"task-ui", "task-action"} <= task_ids


async def test_taskboard_ui_actions_do_not_modify_board_channels(tmp_path: Path) -> None:
    app = _create_app(tmp_path, ["alice", "bob"])
    alice_task_id, bob_task_id = _seed_taskboard(app)
    channel_path = app.state.shared_dir / "channels" / "general.jsonl"
    channel_entry = {
        "ts": "2026-05-14T10:00:00+09:00",
        "from": "alice",
        "text": "Board conversation remains independent",
    }
    channel_path.write_text(json.dumps(channel_entry, ensure_ascii=False) + "\n", encoding="utf-8")
    before = channel_path.read_bytes()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        snooze_resp = await client.patch(
            f"/api/task-board/alice/{alice_task_id}",
            json={
                "visibility": "snoozed",
                "snoozed_until": "2026-05-15T10:00:00+09:00",
                "actor": "dashboard",
            },
        )
        reactivate_resp = await client.patch(
            f"/api/task-board/alice/{alice_task_id}",
            json={"visibility": "active", "snoozed_until": None, "actor": "dashboard"},
        )
        reorder_resp = await client.patch(
            f"/api/task-board/bob/{bob_task_id}",
            json={"position": 2000, "actor": "dashboard"},
        )
        channels_resp = await client.get("/api/channels")

    assert snooze_resp.status_code == 200
    assert reactivate_resp.status_code == 200
    assert reorder_resp.status_code == 200
    assert reorder_resp.json()["task"]["position"] == 2000
    assert channel_path.read_bytes() == before
    assert channels_resp.status_code == 200
    assert channels_resp.json()[0]["name"] == "general"
    assert channels_resp.json()[0]["message_count"] == 1
