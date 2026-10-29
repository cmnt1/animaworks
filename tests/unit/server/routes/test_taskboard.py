from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.tasks.board.board_actions import BoardActionError
from core.tasks.queue import TaskQueueManager
from server.routes.taskboard import create_taskboard_router


def _make_app(tmp_path: Path, anima_names: list[str], monkeypatch=None) -> FastAPI:
    data_dir = tmp_path / "data"
    animas_dir = data_dir / "animas"
    shared_dir = data_dir / "shared"
    animas_dir.mkdir(parents=True, exist_ok=True)
    shared_dir.mkdir(parents=True, exist_ok=True)
    for name in anima_names:
        (animas_dir / name / "state").mkdir(parents=True, exist_ok=True)

    if monkeypatch is not None:
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(data_dir))

    app = FastAPI()
    app.state.animas_dir = animas_dir
    app.state.shared_dir = shared_dir
    app.state.anima_names = anima_names
    app.include_router(create_taskboard_router(), prefix="/api")
    return app


def _queue(app: FastAPI, anima_name: str) -> TaskQueueManager:
    return TaskQueueManager(app.state.animas_dir / anima_name)


class TestTaskBoardList:
    async def test_get_endpoints_do_not_create_a_missing_taskboard(self, tmp_path: Path, monkeypatch) -> None:
        app = _make_app(tmp_path, ["alice"], monkeypatch)
        db_path = app.state.shared_dir / "taskboard.sqlite3"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            list_response = await client.get("/api/task-board", params={"include_archived": "true"})
            summary_response = await client.get("/api/task-board/summary")

        assert list_response.status_code == 200
        assert list_response.json()["tasks"] == []
        assert summary_response.status_code == 200
        assert summary_response.json() == {"pending": 0, "in_progress": 0, "delegated": 0, "total_active": 0}
        assert not db_path.exists()

    async def test_lists_canonical_tasks_with_filters_and_corrupt_warning(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        queue = _queue(app, "alice")
        queue.add_task(
            source="human",
            original_instruction="prepare release notes",
            assignee="alice",
            summary="prepare release notes",
            task_id="task-active",
        )
        running = queue.add_task(
            source="human",
            original_instruction="write the report",
            assignee="alice",
            summary="write the report",
            task_id="task-running",
        )
        queue.update_status(running.task_id, "in_progress")
        done = queue.add_task(
            source="human",
            original_instruction="ship old patch",
            assignee="alice",
            summary="ship old patch",
            task_id="task-done",
        )
        queue.update_status(done.task_id, "done")
        # A stale legacy file cannot alter a canonical board or its diagnostics.
        queue.queue_path.parent.mkdir(parents=True, exist_ok=True)
        queue.queue_path.write_text("\n{bad-json\n", encoding="utf-8")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            default_resp = await client.get("/api/task-board")
            full_resp = await client.get("/api/task-board", params={"include_archived": "true"})
            query_resp = await client.get("/api/task-board", params={"q": "release"})
            column_resp = await client.get("/api/task-board", params={"column": "running"})

        assert default_resp.status_code == 200
        assert [task["task_id"] for task in default_resp.json()["tasks"]] == ["task-active", "task-running"]
        assert default_resp.json()["tasks"][0]["column"] == "todo"
        assert default_resp.json()["columns"][0] == {"id": "todo", "title": "Todo", "count": 1}
        assert default_resp.json()["meta"]["warnings"]["corrupt_task_queue_lines"] == 0
        assert default_resp.json()["counts"] == {"active": 2, "archived": 0}

        full_data = full_resp.json()
        assert {task["task_id"] for task in full_data["tasks"]} == {
            "task-active",
            "task-running",
            "task-done",
        }
        assert full_data["counts"] == {"active": 2, "archived": 1}

        assert [task["task_id"] for task in query_resp.json()["tasks"]] == ["task-active"]
        assert [task["task_id"] for task in column_resp.json()["tasks"]] == ["task-running"]

    async def test_unknown_assignee_returns_404(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/task-board", params={"assignee": "missing"})

        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "anima_not_found"

    async def test_invalid_column_returns_422(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/task-board", params={"column": "doing"})

        assert resp.status_code == 422


class TestTaskBoardSummary:
    async def test_summary_counts_canonical_work(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        queue = _queue(app, "alice")
        queue.add_task(
            source="human",
            original_instruction="pending work",
            assignee="alice",
            summary="pending work",
            task_id="task-pending",
        )
        running = queue.add_task(
            source="human",
            original_instruction="running work",
            assignee="alice",
            summary="running work",
            task_id="task-running",
        )
        queue.update_status(running.task_id, "in_progress")
        done = queue.add_task(
            source="human",
            original_instruction="finished",
            assignee="alice",
            summary="finished",
            task_id="task-done",
        )
        queue.update_status(done.task_id, "done")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/task-board/summary")

        assert resp.status_code == 200
        assert resp.json() == {"pending": 1, "in_progress": 1, "delegated": 0, "total_active": 2}


class TestTaskBoardCancel:
    async def test_cancel_marks_task_cancelled(self, tmp_path: Path, monkeypatch) -> None:
        app = _make_app(tmp_path, ["alice"], monkeypatch)
        queue = _queue(app, "alice")
        task = queue.add_task(
            source="human",
            original_instruction="obsolete follow up",
            assignee="alice",
            summary="obsolete follow up",
            task_id="task-cancel",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/task-board/alice/{task.task_id}/cancel",
                json={"reason": "no longer relevant"},
            )

        assert resp.status_code == 200
        assert resp.json()["result"]["status"] == "cancelled"
        assert queue.get_task_by_id(task.task_id).status == "cancelled"

    async def test_authenticated_user_is_actor(self, tmp_path: Path, monkeypatch) -> None:
        app = _make_app(tmp_path, ["alice"], monkeypatch)

        @app.middleware("http")
        async def _inject_user(request, call_next):
            request.state.user = SimpleNamespace(username="owner")
            return await call_next(request)

        task = _queue(app, "alice").add_task(
            source="human",
            original_instruction="audit cancel",
            assignee="alice",
            summary="audit cancel",
            task_id="task-cancel-audit",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/task-board/alice/{task.task_id}/cancel",
                json={"reason": "done by owner"},
            )

        assert resp.status_code == 200
        notes = queue_task_notes(app, "alice", task.task_id)
        assert notes and notes[-1]["by"] == "owner"

    async def test_cancel_unknown_task_returns_404(self, tmp_path: Path, monkeypatch) -> None:
        app = _make_app(tmp_path, ["alice"], monkeypatch)
        _queue(app, "alice")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/task-board/alice/does-not-exist/cancel",
                json={"reason": "gone"},
            )

        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "task_not_found"

    async def test_cancel_unknown_anima_returns_404(self, tmp_path: Path, monkeypatch) -> None:
        app = _make_app(tmp_path, ["alice"], monkeypatch)
        _queue(app, "alice")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/task-board/missing/task-x/cancel",
                json={"reason": "gone"},
            )

        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "anima_not_found"

    async def test_board_action_refusal_maps_to_409(self, tmp_path: Path, monkeypatch) -> None:
        app = _make_app(tmp_path, ["alice"], monkeypatch)
        task = _queue(app, "alice").add_task(
            source="human",
            original_instruction="refuse me",
            assignee="alice",
            summary="refuse me",
            task_id="task-refuse",
        )

        def _refuse(**kwargs):
            raise BoardActionError("task is leased by other until 2099", 2)

        monkeypatch.setattr("server.routes.taskboard.run_board_action", _refuse)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/task-board/alice/{task.task_id}/cancel",
                json={"reason": "please"},
            )

        assert resp.status_code == 409
        assert resp.json()["detail"]["error"] == "board_action_refused"


def queue_task_notes(app: FastAPI, anima_name: str, task_id: str) -> list:
    queue = _queue(app, anima_name)
    entry = queue.get_task_by_id(task_id)
    if entry is None:
        return []
    return list(entry.meta.get("notes", []))
