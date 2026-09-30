# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Tests for TaskStore watching and command execution in PendingTaskExecutor."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.exceptions import ToolExecutionError
from core.tasks.pending_executor import PendingTaskExecutor

# ── Helpers ──────────────────────────────────────────────────


def _make_executor(tmp_path: Path) -> PendingTaskExecutor:
    """Create a PendingTaskExecutor pointing at a temporary directory."""
    anima_dir = tmp_path / "animas" / "test-anima"
    anima_dir.mkdir(parents=True, exist_ok=True)
    return PendingTaskExecutor(
        anima=None,
        anima_name="test-anima",
        anima_dir=anima_dir,
        shutdown_event=asyncio.Event(),
    )


def _make_executor_with_anima(tmp_path: Path) -> PendingTaskExecutor:
    """Create a PendingTaskExecutor with a mocked anima and BackgroundTaskManager."""
    anima_dir = tmp_path / "animas" / "test-anima"
    anima_dir.mkdir(parents=True, exist_ok=True)

    mock_anima = MagicMock()
    mock_anima._lock = asyncio.Lock()

    # Mock the background manager chain: anima.agent.background_manager
    bg_mgr = MagicMock()
    bg_mgr.submit = MagicMock(return_value="mock-task-id")
    mock_anima.agent.background_manager = bg_mgr

    return PendingTaskExecutor(
        anima=mock_anima,
        anima_name="test-anima",
        anima_dir=anima_dir,
        shutdown_event=asyncio.Event(),
    )


# ── TestPendingTaskWatcherLoop ───────────────────────────────


class TestPendingTaskWatcherLoop:
    """Tests for TaskStore claim and dispatch."""

    def test_reuses_task_queue_manager(self, tmp_path: Path) -> None:
        executor = _make_executor_with_anima(tmp_path)
        with patch("core.tasks.queue.TaskQueueManager") as manager_type:
            first = executor._get_task_queue_manager()
            second = executor._get_task_queue_manager()
        assert first is second
        manager_type.assert_called_once_with(executor._anima_dir)

    def _stop_after_first(self, executor):
        async def _mock(coro, *, timeout):
            coro.close()
            executor._shutdown_event.set()
            raise TimeoutError

        return _mock

    async def test_claims_and_dispatches_command_from_task_store(self, tmp_path: Path) -> None:
        from core.tasks.queue import TaskQueueManager

        executor = _make_executor_with_anima(tmp_path)
        queue = TaskQueueManager(executor._anima_dir)
        queue.submit(
            {
                "task_type": "command",
                "task_id": "command-1",
                "title": "image_gen:3d",
                "description": "Generate a model",
                "tool_name": "image_gen",
                "subcommand": "3d",
                "raw_args": ["3d", "assets/model.png"],
                "anima_dir": str(executor._anima_dir),
            },
            meta={"executor": "command"},
        )
        executed: list[dict] = []

        async def execute(task_desc: dict) -> None:
            executed.append(task_desc)
            queue.update_status(task_desc["task_id"], "done")

        executor.execute_pending_task = execute  # type: ignore[assignment]
        with patch("core.tasks.pending_executor.asyncio.wait_for", side_effect=self._stop_after_first(executor)):
            await executor.watcher_loop()

        assert len(executed) == 1
        assert executed[0]["task_type"] == "command"
        assert executed[0]["_attempt_token"]
        assert queue.get_task_by_id("command-1").status == "done"
        assert queue.store.active_attempts(executor._anima_name) == []
        assert queue.store.get_input(executor._anima_name, "command-1")["raw_args"] == ["3d", "assets/model.png"]
        assert not (executor._anima_dir / "state" / "background_tasks" / "pending").exists()

    async def test_preserves_legacy_llm_evidence_without_watching_files(self, tmp_path: Path) -> None:
        from core.tasks.board.tasks import TaskStore, task_database_path

        executor = _make_executor_with_anima(tmp_path)
        llm_pending_dir = executor._anima_dir / "state" / "pending"
        llm_pending_dir.mkdir(parents=True, exist_ok=True)
        junk = llm_pending_dir / "pr4894-reviews-raw.json"
        junk.write_text("[]", encoding="utf-8")
        TaskStore(task_database_path(executor._anima_dir)).import_legacy(executor._anima_dir)

        with patch("core.tasks.pending_executor.asyncio.wait_for", side_effect=self._stop_after_first(executor)):
            await executor.watcher_loop()

        assert junk.read_text(encoding="utf-8") == "[]"

    async def test_stops_on_cancellation(self, tmp_path: Path) -> None:
        executor = _make_executor_with_anima(tmp_path)

        async def cancel_wait(coro, *, timeout):
            coro.close()
            raise asyncio.CancelledError()

        with patch("core.tasks.pending_executor.asyncio.wait_for", side_effect=cancel_wait):
            await executor.watcher_loop()


# ── TestExecutePendingTask ───────────────────────────────────


class TestExecutePendingTask:
    """Tests for execute_pending_task()."""

    async def test_calls_background_manager_submit(self, tmp_path: Path) -> None:
        """execute_pending_task submits the task to BackgroundTaskManager."""
        executor = _make_executor_with_anima(tmp_path)
        bg_mgr = executor._anima.agent.background_manager

        task_desc = {
            "task_id": "abc123def456",
            "tool_name": "image_gen",
            "subcommand": "3d",
            "raw_args": ["3d", "assets/avatar.png"],
            "anima_name": "test-anima",
            "anima_dir": str(executor._anima_dir),
            "submitted_at": 1739800000.0,
            "status": "pending",
        }

        await executor.execute_pending_task(task_desc)

        bg_mgr.submit.assert_called_once()
        call_args = bg_mgr.submit.call_args
        # First positional arg should be composite name "image_gen:3d"
        assert call_args[0][0] == "image_gen:3d"
        # Second positional arg should be the tool_args dict
        tool_args = call_args[0][1]
        assert tool_args["subcommand"] == "3d"
        assert tool_args["raw_args"] == ["3d", "assets/avatar.png"]

    async def test_composite_name_without_subcommand(self, tmp_path: Path) -> None:
        """When subcommand is empty, composite name is just the tool_name."""
        executor = _make_executor_with_anima(tmp_path)
        bg_mgr = executor._anima.agent.background_manager

        task_desc = {
            "task_id": "xyz789abc012",
            "tool_name": "transcribe",
            "subcommand": "",
            "raw_args": ["/path/to/audio.wav"],
            "anima_name": "test-anima",
            "anima_dir": str(executor._anima_dir),
        }

        await executor.execute_pending_task(task_desc)

        bg_mgr.submit.assert_called_once()
        composite_name = bg_mgr.submit.call_args[0][0]
        assert composite_name == "transcribe"

    async def test_missing_anima_is_reported_as_execution_failure(self, tmp_path: Path) -> None:
        executor = _make_executor(tmp_path)
        with pytest.raises(RuntimeError, match="anima not initialized"):
            await executor.execute_pending_task({"task_type": "command", "task_id": "cmd-1"})

    async def test_missing_background_manager_is_reported_as_execution_failure(self, tmp_path: Path) -> None:
        executor = _make_executor_with_anima(tmp_path)
        executor._anima.agent.background_manager = None
        with pytest.raises(RuntimeError, match="BackgroundTaskManager not available"):
            await executor.execute_pending_task({"task_type": "command", "task_id": "cmd-1"})
    async def test_passes_anima_dir_to_tool_args(self, tmp_path: Path) -> None:
        """anima_dir from the task descriptor is passed through to tool_args."""
        executor = _make_executor_with_anima(tmp_path)
        bg_mgr = executor._anima.agent.background_manager

        custom_dir = "/home/user/.animaworks/animas/custom-anima"
        task_desc = {
            "task_id": "abc123def456",
            "tool_name": "image_gen",
            "subcommand": "fullbody",
            "raw_args": ["fullbody", "--prompt", "test"],
            "anima_dir": custom_dir,
        }

        await executor.execute_pending_task(task_desc)

        tool_args = bg_mgr.submit.call_args[0][1]
        assert tool_args["anima_dir"] == custom_dir

    async def test_defaults_anima_dir_when_not_in_task(self, tmp_path: Path) -> None:
        """When anima_dir is not in task_desc, falls back to executor's _anima_dir."""
        executor = _make_executor_with_anima(tmp_path)
        bg_mgr = executor._anima.agent.background_manager

        task_desc = {
            "task_id": "abc123def456",
            "tool_name": "local_llm",
            "subcommand": "generate",
            "raw_args": ["generate", "hello"],
            # No "anima_dir" key
        }

        await executor.execute_pending_task(task_desc)

        tool_args = bg_mgr.submit.call_args[0][1]
        assert tool_args["anima_dir"] == str(executor._anima_dir)

    async def test_dispatch_fn_is_callable(self, tmp_path: Path) -> None:
        """The third argument to bg_mgr.submit() is a callable dispatch function."""
        executor = _make_executor_with_anima(tmp_path)
        bg_mgr = executor._anima.agent.background_manager

        task_desc = {
            "task_id": "abc123def456",
            "tool_name": "image_gen",
            "subcommand": "3d",
            "raw_args": ["3d", "test.png"],
            "anima_dir": str(executor._anima_dir),
        }

        await executor.execute_pending_task(task_desc)

        dispatch_fn = bg_mgr.submit.call_args[0][2]
        assert callable(dispatch_fn)


# ── TestDispatchFn ────────────────────────────────────────────


class TestDispatchFn:
    """Tests for the _dispatch_fn closure built inside execute_pending_task."""

    async def _capture_dispatch_fn(
        self,
        tmp_path: Path,
        task_desc: dict,
    ):
        """Run execute_pending_task and return the captured dispatch function."""
        executor = _make_executor_with_anima(tmp_path)
        bg_mgr = executor._anima.agent.background_manager

        await executor.execute_pending_task(task_desc)

        bg_mgr.submit.assert_called_once()
        dispatch_fn = bg_mgr.submit.call_args[0][2]
        return dispatch_fn, executor

    async def test_dispatch_fn_builds_correct_command(self, tmp_path: Path) -> None:
        """_dispatch_fn builds: animaworks-tool <tool> <subcmd> ...raw_args -j."""
        task_desc = {
            "task_id": "cmd_test_001",
            "tool_name": "image_gen",
            "subcommand": "3d",
            "raw_args": ["3d", "--model", "test"],
            "anima_dir": str(tmp_path),
        }

        dispatch_fn, _ = await self._capture_dispatch_fn(tmp_path, task_desc)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "result output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            dispatch_fn(
                "image_gen",
                {
                    "subcommand": "3d",
                    "raw_args": ["3d", "--model", "test"],
                    "anima_dir": str(tmp_path),
                },
            )

            mock_run.assert_called_once()
            cmd = mock_run.call_args[0][0]
            assert cmd == ["animaworks-tool", "image_gen", "3d", "--model", "test", "-j"]

    async def test_dispatch_fn_deduplicates_subcommand(self, tmp_path: Path) -> None:
        """When raw_args[0] == subcommand, subcommand does not appear twice."""
        task_desc = {
            "task_id": "dedup_test",
            "tool_name": "local_llm",
            "subcommand": "generate",
            "raw_args": ["generate", "hello"],
            "anima_dir": str(tmp_path),
        }

        dispatch_fn, _ = await self._capture_dispatch_fn(tmp_path, task_desc)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            dispatch_fn(
                "local_llm",
                {
                    "subcommand": "generate",
                    "raw_args": ["generate", "hello"],
                    "anima_dir": str(tmp_path),
                },
            )

            cmd = mock_run.call_args[0][0]
            # "generate" should appear only once, not twice
            assert cmd.count("generate") == 1
            assert cmd == ["animaworks-tool", "local_llm", "generate", "hello", "-j"]

    async def test_dispatch_fn_no_dedup_when_different(self, tmp_path: Path) -> None:
        """When raw_args[0] != subcommand, subcommand is prepended."""
        task_desc = {
            "task_id": "nodedup_test",
            "tool_name": "image_gen",
            "subcommand": "3d",
            "raw_args": ["--prompt", "1girl"],
            "anima_dir": str(tmp_path),
        }

        dispatch_fn, _ = await self._capture_dispatch_fn(tmp_path, task_desc)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            dispatch_fn(
                "image_gen",
                {
                    "subcommand": "3d",
                    "raw_args": ["--prompt", "1girl"],
                    "anima_dir": str(tmp_path),
                },
            )

            cmd = mock_run.call_args[0][0]
            assert cmd == [
                "animaworks-tool",
                "image_gen",
                "3d",
                "--prompt",
                "1girl",
                "-j",
            ]

    async def test_dispatch_fn_sets_anima_dir_env(self, tmp_path: Path) -> None:
        """_dispatch_fn sets ANIMAWORKS_ANIMA_DIR environment variable."""
        anima_dir = str(tmp_path / "animas" / "sakura")
        task_desc = {
            "task_id": "env_test_001",
            "tool_name": "transcribe",
            "subcommand": "",
            "raw_args": ["/path/to/audio.wav"],
            "anima_dir": anima_dir,
        }

        dispatch_fn, _ = await self._capture_dispatch_fn(tmp_path, task_desc)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "transcribed"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            dispatch_fn(
                "transcribe",
                {
                    "subcommand": "",
                    "raw_args": ["/path/to/audio.wav"],
                    "anima_dir": anima_dir,
                },
            )

            call_kwargs = mock_run.call_args[1]
            env = call_kwargs.get("env") or mock_run.call_args[1].get("env", {})
            assert env["ANIMAWORKS_ANIMA_DIR"] == anima_dir

    async def test_dispatch_fn_raises_on_nonzero_exit(self, tmp_path: Path) -> None:
        """Non-zero exit code from subprocess raises RuntimeError."""
        task_desc = {
            "task_id": "err_test_001",
            "tool_name": "image_gen",
            "subcommand": "3d",
            "raw_args": ["3d", "test.png"],
            "anima_dir": str(tmp_path),
        }

        dispatch_fn, _ = await self._capture_dispatch_fn(tmp_path, task_desc)

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "Something went wrong"

        with (
            patch("subprocess.run", return_value=mock_result),
            pytest.raises(ToolExecutionError, match="Tool image_gen failed"),
        ):
            dispatch_fn(
                "image_gen",
                {
                    "subcommand": "3d",
                    "raw_args": ["3d", "test.png"],
                    "anima_dir": str(tmp_path),
                },
            )

    async def test_dispatch_fn_returns_stdout(self, tmp_path: Path) -> None:
        """_dispatch_fn returns stripped stdout on success."""
        task_desc = {
            "task_id": "ret_test_001",
            "tool_name": "web_search",
            "subcommand": "search",
            "raw_args": ["search", "python asyncio"],
            "anima_dir": str(tmp_path),
        }

        dispatch_fn, _ = await self._capture_dispatch_fn(tmp_path, task_desc)

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  search results here  \n"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = dispatch_fn(
                "web_search",
                {
                    "subcommand": "search",
                    "raw_args": ["search", "python asyncio"],
                    "anima_dir": str(tmp_path),
                },
            )
            assert result == "search results here"
