"""Unit tests for PendingTaskExecutor."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.i18n import t
from core.supervisor.pending_executor import PendingTaskExecutor


def _make_executor(tmp_path: Path) -> PendingTaskExecutor:
    """Create a PendingTaskExecutor with minimal dependencies."""
    anima_dir = tmp_path / "animas" / "test-anima"
    anima_dir.mkdir(parents=True, exist_ok=True)
    mock_anima = MagicMock()
    mock_anima.agent.background_manager = MagicMock()

    return PendingTaskExecutor(
        anima=mock_anima,
        anima_name="test-anima",
        anima_dir=anima_dir,
        shutdown_event=asyncio.Event(),
    )


class TestPendingTaskExecutorInit:
    """Test PendingTaskExecutor initialization."""

    def test_creates_instance(self, tmp_path):
        executor = _make_executor(tmp_path)
        assert executor._anima_name == "test-anima"

    def test_independent_instantiation(self, tmp_path):
        """PendingTaskExecutor can be instantiated without AnimaRunner."""
        anima_dir = tmp_path / "animas" / "standalone"
        anima_dir.mkdir(parents=True)
        executor = PendingTaskExecutor(
            anima=MagicMock(),
            anima_name="standalone",
            anima_dir=anima_dir,
            shutdown_event=asyncio.Event(),
        )
        assert executor._anima_name == "standalone"


class TestExecutePendingTask:
    """Test pending task execution."""

    @pytest.mark.asyncio
    async def test_submits_to_background_manager(self, tmp_path):
        """Task should be submitted to BackgroundTaskManager."""
        executor = _make_executor(tmp_path)

        task_desc = {
            "task_id": "test-123",
            "tool_name": "web_search",
            "subcommand": "search",
            "raw_args": ["query"],
            "anima_dir": str(tmp_path / "animas" / "test-anima"),
        }

        await executor.execute_pending_task(task_desc)

        executor._anima.agent.background_manager.submit.assert_called_once()
        call_args = executor._anima.agent.background_manager.submit.call_args
        assert call_args[0][0] == "web_search:search"

    @pytest.mark.asyncio
    async def test_skips_when_no_anima(self, tmp_path):
        """Should skip when anima is None."""
        executor = _make_executor(tmp_path)
        executor._anima = None

        # Should not raise
        await executor.execute_pending_task({"tool_name": "test"})

    @pytest.mark.asyncio
    async def test_skips_when_no_background_manager(self, tmp_path):
        """Should skip when background_manager is None."""
        executor = _make_executor(tmp_path)
        executor._anima.agent.background_manager = None

        # Should not raise
        await executor.execute_pending_task({"tool_name": "test"})


class TestWatcherLoop:
    """Test pending task watcher loop."""

    @pytest.mark.asyncio
    async def test_picks_up_pending_files(self, tmp_path):
        """Watcher should pick up and process .json files in pending dir."""
        executor = _make_executor(tmp_path)
        pending_dir = executor._anima_dir / "state" / "background_tasks" / "pending"
        pending_dir.mkdir(parents=True, exist_ok=True)

        task = {"task_id": "test-1", "tool_name": "test_tool", "subcommand": "", "raw_args": []}
        (pending_dir / "task1.json").write_text(json.dumps(task))

        original_wait_for = asyncio.wait_for

        async def stop_after_first(coro, *, timeout):
            executor._shutdown_event.set()
            raise TimeoutError

        with patch("core.supervisor.pending_executor.asyncio.wait_for", side_effect=stop_after_first):
            await executor.watcher_loop()

        assert not (pending_dir / "task1.json").exists()
        executor._anima.agent.background_manager.submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_invalid_json(self, tmp_path):
        """Watcher should handle invalid JSON files gracefully."""
        executor = _make_executor(tmp_path)
        pending_dir = executor._anima_dir / "state" / "background_tasks" / "pending"
        pending_dir.mkdir(parents=True, exist_ok=True)

        (pending_dir / "bad.json").write_text("not json")

        async def stop_after_first(coro, *, timeout):
            executor._shutdown_event.set()
            raise TimeoutError

        with patch("core.supervisor.pending_executor.asyncio.wait_for", side_effect=stop_after_first):
            await executor.watcher_loop()

        assert not (pending_dir / "bad.json").exists()


class TestMachineDirectiveInjection:
    """Test machine tool directive injection into TaskExec prompt."""

    def test_directive_appended_when_machine_in_description(self):
        """Prompt should have machine directive when description mentions machine."""
        description = "machineツールで実装し、検証してpushする"
        assert "machine" in description.lower()
        directive = t("pending_executor.machine_directive")
        assert "MUST" in directive

    def test_directive_not_appended_without_machine(self):
        """No directive when description does not mention machine."""
        description = "git pushして結果を報告する"
        assert "machine" not in description.lower()

    def test_case_insensitive_detection(self):
        """Detection should be case-insensitive."""
        for desc in ["Machineで実装", "MACHINE RUN", "use machine tool"]:
            assert "machine" in desc.lower()

    def test_directive_i18n_ja(self):
        directive = t("pending_executor.machine_directive", lang="ja")
        assert "MUST" in directive
        assert "animaworks-tool machine run" in directive

    def test_directive_i18n_en(self):
        directive = t("pending_executor.machine_directive", lang="en")
        assert "MUST" in directive
        assert "animaworks-tool machine run" in directive

    def test_integration_prompt_with_machine(self):
        """Simulate the prompt construction logic: machine → directive appended."""
        base_prompt = "あなたはタスク実行エージェントです。\n## 作業内容\nmachineで実装し検証する"
        description = "machineで実装し検証する"
        directive = t("pending_executor.machine_directive")

        prompt = base_prompt
        if "machine" in description.lower():
            prompt += "\n\n" + directive

        assert prompt.endswith(directive)
        assert "MUST" in prompt

    def test_integration_prompt_without_machine(self):
        """Prompt stays unchanged when no machine mention."""
        base_prompt = "あなたはタスク実行エージェントです。\n## 作業内容\nCI結果を確認する"
        description = "CI結果を確認してレポートを作成する"

        prompt = base_prompt
        if "machine" in description.lower():
            prompt += "\n\n" + t("pending_executor.machine_directive")

        assert prompt == base_prompt


class TestStreamErrorSuppression:
    """Test that stream errors are suppressed when task queue is already done."""

    @pytest.mark.asyncio
    async def test_suppressed_when_queue_is_done(self, tmp_path):
        """Stream error should NOT raise when task queue status is 'done'."""
        executor = _make_executor(tmp_path)
        bg_event = asyncio.Event()
        executor._anima._get_interrupt_event = lambda _name: bg_event

        async def _stream_with_error(*args, **kwargs):
            yield {"type": "text_delta", "text": "partial output"}
            yield {"type": "error", "message": "stream disconnected 3 times"}

        executor._anima.agent.run_cycle_streaming = _stream_with_error
        executor._anima.agent.reset_reply_tracking = MagicMock()
        executor._anima.agent.reset_read_paths = MagicMock()
        executor._anima.agent.set_task_cwd = MagicMock()
        executor._anima.messenger = MagicMock()

        task_desc = {
            "task_id": "task-done-1",
            "title": "Already completed task",
            "description": "Task that completes before stream error",
        }

        mock_entry = MagicMock()
        mock_entry.status = "done"
        mock_entry.summary = "Task completed successfully"

        with (
            patch("core.paths.load_prompt", return_value="test prompt"),
            patch("core.memory.activity.ActivityLogger") as mock_activity,
            patch("core.supervisor.pending_executor._resolve_default_workspace", return_value=""),
            patch("core.memory.task_queue.TaskQueueManager") as mock_tqm,
        ):
            mock_activity.return_value.log = MagicMock()
            mock_tqm.return_value.get_task_by_id.return_value = mock_entry

            result = await executor._run_llm_task(task_desc)
            assert result == "Task completed successfully"

    @pytest.mark.asyncio
    async def test_raises_when_queue_is_not_done(self, tmp_path):
        """Stream error should raise TaskExecError when queue status is not 'done'."""
        from core.supervisor.pending_executor import TaskExecError

        executor = _make_executor(tmp_path)
        bg_event = asyncio.Event()
        executor._anima._get_interrupt_event = lambda _name: bg_event

        async def _stream_with_error(*args, **kwargs):
            yield {"type": "error", "message": "stream disconnected"}

        executor._anima.agent.run_cycle_streaming = _stream_with_error
        executor._anima.agent.reset_reply_tracking = MagicMock()
        executor._anima.agent.reset_read_paths = MagicMock()
        executor._anima.agent.set_task_cwd = MagicMock()
        executor._anima.messenger = MagicMock()

        task_desc = {
            "task_id": "task-pending-1",
            "title": "Incomplete task",
            "description": "Task that did not complete",
        }

        mock_entry = MagicMock()
        mock_entry.status = "in_progress"

        with (
            patch("core.paths.load_prompt", return_value="test prompt"),
            patch("core.memory.activity.ActivityLogger") as mock_activity,
            patch("core.supervisor.pending_executor._resolve_default_workspace", return_value=""),
            patch("core.memory.task_queue.TaskQueueManager") as mock_tqm,
        ):
            mock_activity.return_value.log = MagicMock()
            mock_tqm.return_value.get_task_by_id.return_value = mock_entry

            with pytest.raises(TaskExecError, match="streaming error"):
                await executor._run_llm_task(task_desc)

    @pytest.mark.asyncio
    async def test_raises_when_queue_lookup_fails(self, tmp_path):
        """Stream error should raise TaskExecError when queue lookup raises."""
        from core.supervisor.pending_executor import TaskExecError

        executor = _make_executor(tmp_path)
        bg_event = asyncio.Event()
        executor._anima._get_interrupt_event = lambda _name: bg_event

        async def _stream_with_error(*args, **kwargs):
            yield {"type": "error", "message": "stream disconnected"}

        executor._anima.agent.run_cycle_streaming = _stream_with_error
        executor._anima.agent.reset_reply_tracking = MagicMock()
        executor._anima.agent.reset_read_paths = MagicMock()
        executor._anima.agent.set_task_cwd = MagicMock()
        executor._anima.messenger = MagicMock()

        task_desc = {
            "task_id": "task-err-1",
            "title": "Queue inaccessible task",
            "description": "Task where queue cannot be read",
        }

        with (
            patch("core.paths.load_prompt", return_value="test prompt"),
            patch("core.memory.activity.ActivityLogger") as mock_activity,
            patch("core.supervisor.pending_executor._resolve_default_workspace", return_value=""),
            patch("core.memory.task_queue.TaskQueueManager") as mock_tqm,
        ):
            mock_activity.return_value.log = MagicMock()
            mock_tqm.return_value.get_task_by_id.side_effect = OSError("disk error")

            with pytest.raises(TaskExecError, match="streaming error"):
                await executor._run_llm_task(task_desc)

    @pytest.mark.asyncio
    async def test_raises_when_task_not_in_queue(self, tmp_path):
        """Stream error should raise when task is not found in queue (None)."""
        from core.supervisor.pending_executor import TaskExecError

        executor = _make_executor(tmp_path)
        bg_event = asyncio.Event()
        executor._anima._get_interrupt_event = lambda _name: bg_event

        async def _stream_with_error(*args, **kwargs):
            yield {"type": "error", "message": "stream disconnected"}

        executor._anima.agent.run_cycle_streaming = _stream_with_error
        executor._anima.agent.reset_reply_tracking = MagicMock()
        executor._anima.agent.reset_read_paths = MagicMock()
        executor._anima.agent.set_task_cwd = MagicMock()
        executor._anima.messenger = MagicMock()

        task_desc = {
            "task_id": "task-missing-1",
            "title": "Unknown task",
            "description": "Task not registered in queue",
        }

        with (
            patch("core.paths.load_prompt", return_value="test prompt"),
            patch("core.memory.activity.ActivityLogger") as mock_activity,
            patch("core.supervisor.pending_executor._resolve_default_workspace", return_value=""),
            patch("core.memory.task_queue.TaskQueueManager") as mock_tqm,
        ):
            mock_activity.return_value.log = MagicMock()
            mock_tqm.return_value.get_task_by_id.return_value = None

            with pytest.raises(TaskExecError, match="streaming error"):
                await executor._run_llm_task(task_desc)

    @pytest.mark.asyncio
    async def test_no_suppression_when_no_error(self, tmp_path):
        """Normal completion (no stream error) returns result without raising."""
        executor = _make_executor(tmp_path)
        bg_event = asyncio.Event()
        executor._anima._get_interrupt_event = lambda _name: bg_event

        async def _stream_success(*args, **kwargs):
            yield {"type": "text_delta", "text": "done"}
            yield {
                "type": "cycle_done",
                "cycle_result": {"summary": "all good", "action": "complete"},
            }

        executor._anima.agent.run_cycle_streaming = _stream_success
        executor._anima.agent.reset_reply_tracking = MagicMock()
        executor._anima.agent.reset_read_paths = MagicMock()
        executor._anima.agent.set_task_cwd = MagicMock()
        executor._anima.messenger = MagicMock()

        task_desc = {
            "task_id": "task-ok-1",
            "title": "Normal task",
            "description": "Task that completes normally",
        }

        with (
            patch("core.paths.load_prompt", return_value="test prompt"),
            patch("core.memory.activity.ActivityLogger") as mock_activity,
            patch("core.supervisor.pending_executor._resolve_default_workspace", return_value=""),
        ):
            mock_activity.return_value.log = MagicMock()
            result = await executor._run_llm_task(task_desc)
            assert result == "all good"


class TestLlmTaskFailurePropagation:
    @pytest.mark.asyncio
    async def test_run_llm_task_raises_when_cycle_done_action_is_error(self, tmp_path):
        executor = _make_executor(tmp_path)
        bg_event = asyncio.Event()
        executor._anima._get_interrupt_event = lambda _name: bg_event

        async def _failing_stream(*args, **kwargs):
            yield {
                "type": "cycle_done",
                "cycle_result": {
                    "action": "error",
                    "summary": "stream retry exhausted",
                },
            }

        executor._anima.agent.run_cycle_streaming = _failing_stream
        executor._anima.agent.reset_reply_tracking = MagicMock()
        executor._anima.agent.reset_read_paths = MagicMock()
        executor._anima.agent.set_task_cwd = MagicMock()
        executor._anima.messenger.send = MagicMock()

        task_desc = {
            "task_id": "llm-fail-1",
            "title": "Broken task",
            "description": "Investigate failure",
        }

        with (
            patch("core.paths.load_prompt", return_value="test prompt"),
            patch("core.memory.activity.ActivityLogger") as mock_activity,
            patch("core.supervisor.pending_executor._resolve_default_workspace", return_value=""),
        ):
            mock_activity.return_value.log = MagicMock()
            with pytest.raises(RuntimeError, match="stream retry exhausted"):
                await executor._run_llm_task(task_desc)
