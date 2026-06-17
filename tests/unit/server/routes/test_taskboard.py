from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.memory.task_queue import TaskQueueManager
from core.taskboard.store import TaskBoardStore
from server.routes.system import create_system_router
from server.routes.taskboard import create_taskboard_router


def _make_app(tmp_path: Path, anima_names: list[str]) -> FastAPI:
    data_dir = tmp_path / "data"
    animas_dir = data_dir / "animas"
    shared_dir = data_dir / "shared"
    animas_dir.mkdir(parents=True, exist_ok=True)
    shared_dir.mkdir(parents=True, exist_ok=True)
    for name in anima_names:
        (animas_dir / name / "state").mkdir(parents=True, exist_ok=True)

    app = FastAPI()
    app.state.animas_dir = animas_dir
    app.state.shared_dir = shared_dir
    app.state.anima_names = anima_names
    app.include_router(create_taskboard_router(), prefix="/api")
    app.include_router(create_system_router(), prefix="/api")
    return app


def _queue(app: FastAPI, anima_name: str) -> TaskQueueManager:
    return TaskQueueManager(app.state.animas_dir / anima_name)


def _store(app: FastAPI) -> TaskBoardStore:
    return TaskBoardStore(app.state.shared_dir / "taskboard.sqlite3")


class TestTaskBoardList:
    async def test_lists_projected_tasks_with_filters_and_corrupt_warning(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        queue = _queue(app, "alice")
        active = queue.add_task(
            source="human",
            original_instruction="prepare release notes",
            assignee="alice",
            summary="prepare release notes",
            task_id="task-active",
        )
        snoozed = queue.add_task(
            source="human",
            original_instruction="wait for vendor reply",
            assignee="alice",
            summary="wait for vendor reply",
            task_id="task-snoozed",
        )
        done = queue.add_task(
            source="human",
            original_instruction="ship old patch",
            assignee="alice",
            summary="ship old patch",
            task_id="task-done",
        )
        queue.update_status(done.task_id, "done")
        _store(app).upsert_metadata(
            anima_name="alice",
            task_id=active.task_id,
            actor="planner",
            column="waiting",
            position=2.0,
        )
        _store(app).upsert_metadata(
            anima_name="alice",
            task_id=snoozed.task_id,
            actor="planner",
            visibility="snoozed",
            snoozed_until="2026-05-15T00:00:00+09:00",
        )
        queue.queue_path.write_text(
            queue.queue_path.read_text(encoding="utf-8") + "\n{bad-json\n",
            encoding="utf-8",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            default_resp = await client.get("/api/task-board")
            full_resp = await client.get("/api/task-board", params={"include_archived": "true"})
            query_resp = await client.get("/api/task-board", params={"q": "release"})

        assert default_resp.status_code == 200
        assert [task["task_id"] for task in default_resp.json()["tasks"]] == ["task-active"]
        assert default_resp.json()["tasks"][0]["column"] == "waiting"
        assert default_resp.json()["tasks"][0]["updated_at"] is not None
        assert default_resp.json()["columns"][0] == {"id": "todo", "title": "Todo", "count": 0}
        assert default_resp.json()["meta"]["warnings"]["corrupt_task_queue_lines"] == 1

        full_data = full_resp.json()
        assert {task["task_id"] for task in full_data["tasks"]} == {
            "task-active",
            "task-snoozed",
            "task-done",
        }
        assert full_data["counts"]["active"] == 1
        assert full_data["counts"]["snoozed"] == 1
        assert full_data["counts"]["archived"] == 1

        assert [task["task_id"] for task in query_resp.json()["tasks"]] == ["task-active"]

    async def test_unknown_assignee_returns_404(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/task-board", params={"assignee": "missing"})

        assert resp.status_code == 404
        assert resp.json()["detail"]["error"] == "anima_not_found"

    async def test_invalid_filters_return_422(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            visibility_resp = await client.get("/api/task-board", params={"visibility": "later"})
            column_resp = await client.get("/api/task-board", params={"column": "doing"})

        assert visibility_resp.status_code == 422
        assert column_resp.status_code == 422

    async def test_operational_task_titles_are_localized_for_display(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        queue = _queue(app, "alice")
        queue.add_task(
            source="human",
            original_instruction="追跡してください",
            assignee="alice",
            summary=(
                "Superseded by active Kanna retry 68db788caef8. "
                "Await final six-gate evidence or saved BLOCKED table."
            ),
            task_id="task-localized",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/task-board", params={"q": "Superseded"})

        assert resp.status_code == 200
        tasks = resp.json()["tasks"]
        assert [task["task_id"] for task in tasks] == ["task-localized"]
        assert tasks[0]["summary"] == (
            "最新のKanna再実行 68db788caef8 に引き継ぎ済み。"
            "最終6ゲート証跡または保存済みBLOCKED表を待機中。"
        )

    async def test_false_completion_summary_is_diagnostic_not_display_title(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["hikaru"])
        queue = _queue(app, "hikaru")
        task = queue.add_task(
            source="anima",
            original_instruction="修正内容を実装して最終証跡を提出してください。",
            assignee="hikaru",
            summary="実装タスク",
            task_id="task-blocked",
            meta={"task_desc": {"title": "安城デイリー売買レポート前日差分を修正"}},
        )
        queue.update_status(
            task.task_id,
            "blocked",
            summary="BLOCKED: Task reported an explicit follow-up/start step, not final evidence",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/task-board")

        assert resp.status_code == 200
        projected = resp.json()["tasks"][0]
        assert projected["display_title"] == "安城デイリー売買レポート前日差分を修正"
        assert projected["diagnostic_summary"] == "停止: 開始・次アクションのみで、最終証跡ではありません"
        assert projected["summary"] == "停止: 開始・次アクションのみで、最終証跡ではありません"

    async def test_stale_cron_in_progress_display_is_stopped(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        queue = _queue(app, "alice")
        task = queue.add_task(
            source="anima",
            original_instruction="run weekly knowledge cron",
            assignee="alice",
            summary="cron running",
            task_id="cron-stale",
            status="in_progress",
            meta={"from_cron": True, "cron_task_name": "weekly knowledge", "cron_type": "llm"},
        )
        queue.queue_path.write_text(
            queue.queue_path.read_text(encoding="utf-8").replace(
                '"updated_at": "' + queue.get_task_by_id(task.task_id).updated_at + '"',
                '"updated_at": "2000-01-01T00:00:00+09:00"',
            ),
            encoding="utf-8",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/task-board")

        assert resp.status_code == 200
        projected = resp.json()["tasks"][0]
        assert projected["queue_status"] == "in_progress"
        assert projected["column"] == "blocked"
        assert projected["display_title"] == "停止: 古いcron実行中: weekly knowledge"
        assert projected["diagnostic_summary"] == (
            "古いcron実行中が停止扱いになっています。再実行または環境確認が必要です。"
        )

    async def test_include_missing_returns_metadata_only_tasks(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        _store(app).upsert_metadata(
            anima_name="alice",
            task_id="missing-task",
            actor="planner",
            visibility="tombstoned",
            column="suppressed",
            tombstone_reason="queue compaction removed it",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            default_resp = await client.get("/api/task-board", params={"include_archived": "true"})
            missing_resp = await client.get(
                "/api/task-board",
                params={"include_archived": "true", "include_missing": "true"},
            )

        assert default_resp.json()["tasks"] == []
        assert missing_resp.json()["tasks"][0]["task_id"] == "missing-task"
        assert missing_resp.json()["tasks"][0]["queue_missing"] is True
        assert missing_resp.json()["tasks"][0]["display_title"] == "欠落タスク: alice:missing-task"
        assert missing_resp.json()["tasks"][0]["diagnostic_summary"] == (
            "TaskQueue本体が見つからないため、TaskBoardメタデータから復元表示しています。"
        )

    async def test_missing_delegated_child_uses_parent_title(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice", "bob"])
        _queue(app, "alice").add_task(
            source="anima",
            original_instruction="parent instruction",
            assignee="alice",
            summary="[委譲] missing child follow-up",
            task_id="parent-task",
            meta={"delegated_to": "bob", "delegated_task_id": "missing-child"},
        )
        _store(app).upsert_metadata(
            anima_name="bob",
            task_id="missing-child",
            actor="planner",
            column="todo",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get(
                "/api/task-board",
                params={"include_missing": "true", "include_archived": "true"},
            )

        child = next(task for task in resp.json()["tasks"] if task["task_id"] == "missing-child")
        assert child["queue_missing"] is True
        assert child["visibility"] == "archived"
        assert child["column"] == "suppressed"
        assert child["display_title"] == "[委譲] missing child follow-up"
        assert child["diagnostic_summary"] == (
            "TaskQueue本体が見つからないため、TaskBoardメタデータから復元表示しています。"
        )


class TestTaskBoardPatch:
    async def test_archiving_active_task_cancels_queue_entry(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        queue = _queue(app, "alice")
        task = queue.add_task(
            source="human",
            original_instruction="obsolete follow up",
            assignee="alice",
            summary="obsolete follow up",
            task_id="task-archive",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.patch(
                f"/api/task-board/alice/{task.task_id}",
                json={"visibility": "archived", "reason": "no longer relevant", "actor": "tadasi"},
            )

        assert resp.status_code == 200
        data = resp.json()["task"]
        assert data["visibility"] == "archived"
        assert data["queue_status"] == "cancelled"
        assert queue.get_task_by_id(task.task_id).status == "cancelled"
        assert queue.get_task_by_id(task.task_id).summary == "archived by TaskBoard: no longer relevant"

        events = _store(app).list_events(anima_name="alice", task_id=task.task_id)
        assert events[-1]["event_type"] == "archived"

    async def test_archiving_failed_task_cancels_queue_entry(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        queue = _queue(app, "alice")
        task = queue.add_task(
            source="anima",
            original_instruction="failed cron",
            assignee="alice",
            summary="failed cron",
            task_id="task-failed",
        )
        queue.update_status(task.task_id, "failed", summary="cron failed")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.patch(
                f"/api/task-board/alice/{task.task_id}",
                json={"visibility": "tombstoned", "reason": "duplicate cron noise", "actor": "tadasi"},
            )

        assert resp.status_code == 200
        data = resp.json()["task"]
        assert data["visibility"] == "archived"
        assert data["queue_status"] == "cancelled"
        assert queue.get_task_by_id(task.task_id).status == "cancelled"
        assert queue.get_task_by_id(task.task_id).summary == "tombstoned by TaskBoard: duplicate cron noise"

    async def test_authenticated_user_overrides_request_actor(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])

        @app.middleware("http")
        async def _inject_user(request, call_next):
            request.state.user = SimpleNamespace(username="owner")
            return await call_next(request)

        task = _queue(app, "alice").add_task(
            source="human",
            original_instruction="audit mutation",
            assignee="alice",
            summary="audit mutation",
            task_id="task-audit",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.patch(
                f"/api/task-board/alice/{task.task_id}",
                json={"column": "review", "actor": "spoofed"},
            )

        assert resp.status_code == 200
        assert resp.json()["task"]["board_updated_by"] == "owner"
        assert resp.json()["task"]["updated_at"] == resp.json()["task"]["board_updated_at"]
        assert _store(app).list_events(anima_name="alice", task_id=task.task_id)[-1]["actor"] == "owner"

    async def test_snoozed_requires_snoozed_until(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        task = _queue(app, "alice").add_task(
            source="human",
            original_instruction="check later",
            assignee="alice",
            summary="check later",
            task_id="task-snooze",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.patch(f"/api/task-board/alice/{task.task_id}", json={"visibility": "snoozed"})

        assert resp.status_code == 422
        assert resp.json()["detail"]["error"] == "snoozed_until_required"

    async def test_notification_ack_records_key_and_timestamp(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        task = _queue(app, "alice").add_task(
            source="human",
            original_instruction="notify me",
            assignee="alice",
            summary="notify me",
            task_id="task-notify",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                f"/api/task-board/alice/{task.task_id}/notification-ack",
                json={"notification_key": "runtime:alice:task-notify", "actor": "runtime"},
            )

        assert resp.status_code == 200
        metadata = _store(app).get_metadata("alice", task.task_id)
        assert metadata is not None
        assert metadata.notification_key == "runtime:alice:task-notify"
        assert metadata.last_notified_at is not None
        assert _store(app).list_events(anima_name="alice", task_id=task.task_id)[-1]["event_type"] == (
            "notification_acknowledged"
        )


class TestTaskSummaryCompatibility:
    async def test_legacy_summary_uses_taskboard_visibility(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        queue = _queue(app, "alice")
        visible = queue.add_task(
            source="human",
            original_instruction="visible task",
            assignee="alice",
            summary="visible task",
            task_id="task-visible",
        )
        snoozed = queue.add_task(
            source="human",
            original_instruction="hidden for now",
            assignee="alice",
            summary="hidden for now",
            task_id="task-hidden",
        )
        queue.update_status(visible.task_id, "in_progress")
        _store(app).upsert_metadata(
            anima_name="alice",
            task_id=snoozed.task_id,
            actor="planner",
            visibility="snoozed",
            snoozed_until="2026-05-15T00:00:00+09:00",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            legacy_resp = await client.get("/api/tasks/summary")
            board_resp = await client.get("/api/task-board/summary")

        assert legacy_resp.json() == {"pending": 0, "in_progress": 1, "total_active": 1}
        board_data = board_resp.json()
        assert board_data["in_progress"] == 1
        assert board_data["snoozed"] == 1
        assert board_data["total_active"] == 1

    async def test_summary_counts_review_column_as_review_not_blocked(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        queue = _queue(app, "alice")
        review = queue.add_task(
            source="human",
            original_instruction="needs review",
            assignee="alice",
            summary="needs review",
            task_id="task-review",
        )
        queue.update_status(review.task_id, "blocked")
        _store(app).upsert_metadata(
            anima_name="alice",
            task_id=review.task_id,
            actor="planner",
            column="review",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            board_resp = await client.get("/api/task-board/summary")

        board_data = board_resp.json()
        assert board_data["blocked"] == 0
        assert board_data["failed_review"] == 1
        assert board_data["total_active"] == 1

    async def test_summary_ignores_missing_metadata_rows_by_default(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["alice"])
        _store(app).upsert_metadata(
            anima_name="alice",
            task_id="missing-waiting",
            actor="planner",
            visibility="active",
            column="waiting",
            source_ref="task_queue:alice:missing-waiting",
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            board_resp = await client.get("/api/task-board/summary")
            list_resp = await client.get("/api/task-board")
            missing_resp = await client.get("/api/task-board", params={"include_missing": "true"})

        assert board_resp.json()["delegated"] == 0
        assert board_resp.json()["total_active"] == 0
        assert list_resp.json()["tasks"] == []
        assert missing_resp.json()["counts"]["active"] == 0
        assert missing_resp.json()["tasks"] == []

    async def test_summary_counts_blocked_child_parent_as_tracking_not_blocked(self, tmp_path: Path) -> None:
        app = _make_app(tmp_path, ["sakura", "hikaru"])
        hikaru = _queue(app, "hikaru")
        child = hikaru.add_task(
            source="anima",
            original_instruction="produce final evidence",
            assignee="hikaru",
            summary="produce final evidence",
            task_id="child-blocked",
        )
        hikaru.update_status(child.task_id, "blocked", summary="BLOCKED: missing evidence")
        sakura = _queue(app, "sakura")
        sakura.add_delegated_task(
            original_instruction="track delegated evidence",
            assignee="hikaru",
            summary="track delegated evidence",
            deadline="1h",
            meta={"delegated_to": "hikaru", "delegated_task_id": child.task_id},
        )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            board_resp = await client.get("/api/task-board/summary")

        board_data = board_resp.json()
        assert board_data["blocked"] == 1
        assert board_data["tracking"] == 1
        assert board_data["total_active"] == 2
