# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Integration tests for submit → TaskStore → command execution → result."""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.tasks.background import BackgroundTask, BackgroundTaskManager, TaskStatus
from core.tasks.pending_executor import PendingTaskExecutor
from core.tasks.queue import TaskQueueManager


class TestSubmitTaskStoreIntegration:
    async def test_submit_claim_execute_and_persist_attempt_and_compatible_result(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from core.integrations import _handle_submit

        anima_dir = tmp_path / "animas" / "test-anima"
        anima_dir.mkdir(parents=True)
        monkeypatch.setenv("ANIMAWORKS_ANIMA_DIR", str(anima_dir))

        captured = io.StringIO()
        with patch("builtins.print", side_effect=lambda value, **_kwargs: captured.write(str(value) + "\n")):
            _handle_submit(["image_gen", "3d", "assets/avatar.png"])
        acknowledgement = json.loads(captured.getvalue())
        task_id = acknowledgement["task_id"]

        queue = TaskQueueManager(anima_dir)
        submitted = queue.store.get_input(anima_dir.name, task_id)
        assert submitted is not None
        assert submitted["task_type"] == "command"
        assert submitted["tool_name"] == "image_gen"
        assert submitted["raw_args"] == ["3d", "assets/avatar.png"]
        assert not (anima_dir / "state" / "background_tasks" / "pending").exists()

        manager = BackgroundTaskManager(anima_dir, anima_name=anima_dir.name)
        manager.on_complete = AsyncMock()
        anima = MagicMock()
        anima.agent.background_manager = manager
        anima._background_worker_pool_size = 1
        anima._clear_busy_status_sidecar_if_idle = MagicMock()
        executor = PendingTaskExecutor(
            anima=anima,
            anima_name=anima_dir.name,
            anima_dir=anima_dir,
            shutdown_event=asyncio.Event(),
        )

        completed = SimpleNamespace(returncode=0, stdout='{"generated": true}', stderr="")
        with patch("subprocess.run", return_value=completed):
            claims = executor._claim_canonical_pending_tasks()
            assert len(claims) == 1
            assert claims[0]["task_type"] == "command"
            await executor._execute_canonical_task(claims[0])

        task = queue.get_task_by_id(task_id)
        assert task is not None
        assert task.status == "done"
        assert task.meta["executor"] == "command"
        assert task.meta["command_status"] == "completed"

        result_path = anima_dir / "state" / "background_tasks" / f"{task_id}.json"
        result = json.loads(result_path.read_text(encoding="utf-8"))
        assert result["task_id"] == task_id
        assert result["status"] == "completed"
        assert result["result"] == '{"generated": true}'
        manager.on_complete.assert_awaited_once()

        with queue.store.reader() as db:
            attempt = db.execute("SELECT stop_kind,result_ref FROM task_attempts WHERE task_id=?", (task_id,)).fetchone()
        assert attempt["stop_kind"] == "command_completed"
        assert attempt["result_ref"] == f"state/task_results/{task_id}/{task.meta['last_attempt_token']}.md"
        assert (anima_dir / attempt["result_ref"]).read_text(encoding="utf-8") == '{"generated": true}'

    def test_notification_write_then_drain(self, tmp_path: Path) -> None:
        """Verify the existing background notification file can still be drained."""
        notif_dir = tmp_path / "state" / "background_notifications"
        notif_dir.mkdir(parents=True)

        task_id = "abc123"
        notif_content = (
            "# バックグラウンドタスク完了: image_gen\n\n"
            f"- タスクID: {task_id}\n"
            "- ツール: image_gen\n"
            "- ステータス: completed\n"
            "- 結果: [image_gen] completed: OK\n"
        )
        (notif_dir / f"{task_id}.md").write_text(notif_content, encoding="utf-8")

        from core.anima.digital_anima import DigitalAnima

        anima = object.__new__(DigitalAnima)
        mock_agent = MagicMock()
        mock_agent.anima_dir = tmp_path
        mock_agent.background_manager = None
        mock_agent.has_human_notifier = False
        anima.agent = mock_agent
        anima.name = "test-anima"

        notifications = anima.drain_background_notifications()
        assert len(notifications) == 1
        assert "image_gen" in notifications[0]
        assert task_id in notifications[0]
        assert not list(notif_dir.glob("*.md"))

    @pytest.mark.asyncio
    async def test_on_complete_then_drain_roundtrip(self, tmp_path: Path) -> None:
        """The current completion callback keeps writing drainable notifications."""
        from core.anima.digital_anima import DigitalAnima

        anima_dir = tmp_path / "animas" / "test"
        anima_dir.mkdir(parents=True)
        anima = object.__new__(DigitalAnima)
        mock_agent = MagicMock()
        mock_agent.anima_dir = anima_dir
        mock_agent.background_manager = None
        mock_agent.has_human_notifier = False
        anima.agent = mock_agent
        anima.name = "test-anima"

        task = BackgroundTask(
            task_id="roundtrip01",
            anima_name="test-anima",
            tool_name="image_gen:3d",
            tool_args={"subcommand": "3d"},
            status=TaskStatus.COMPLETED,
            result="Generated model",
        )
        await anima._on_background_task_complete(task)

        notif_dir = anima_dir / "state" / "background_notifications"
        assert (notif_dir / "roundtrip01.md").exists()
        notifications = anima.drain_background_notifications()
        assert len(notifications) == 1
        assert "roundtrip01" in notifications[0]
        assert "image_gen:3d" in notifications[0]
        assert "完了" in notifications[0]
        assert anima.drain_background_notifications() == []
