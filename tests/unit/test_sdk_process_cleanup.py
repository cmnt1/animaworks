"""Tests for SDK subprocess PID tracking and orphan cleanup logic."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import psutil
import pytest

# ── Layer 1: _extract_sdk_pid ────────────────────────────────


class TestExtractSdkPid:
    """Tests for _extract_sdk_pid helper."""

    def test_returns_pid_from_valid_client(self) -> None:
        from core.execution.engines.claude.executor import _extract_sdk_pid

        client = MagicMock()
        client._transport._process.pid = 12345
        assert _extract_sdk_pid(client) == 12345

    def test_returns_none_when_no_transport(self) -> None:
        from core.execution.engines.claude.executor import _extract_sdk_pid

        client = MagicMock(spec=[])
        assert _extract_sdk_pid(client) is None

    def test_returns_none_when_transport_is_none(self) -> None:
        from core.execution.engines.claude.executor import _extract_sdk_pid

        client = MagicMock()
        client._transport = None
        assert _extract_sdk_pid(client) is None

    def test_returns_none_when_process_is_none(self) -> None:
        from core.execution.engines.claude.executor import _extract_sdk_pid

        client = MagicMock()
        client._transport._process = None
        assert _extract_sdk_pid(client) is None

    def test_returns_none_when_pid_is_zero(self) -> None:
        from core.execution.engines.claude.executor import _extract_sdk_pid

        client = MagicMock()
        client._transport._process.pid = 0
        assert _extract_sdk_pid(client) is None

    def test_returns_none_when_pid_is_negative(self) -> None:
        from core.execution.engines.claude.executor import _extract_sdk_pid

        client = MagicMock()
        client._transport._process.pid = -1
        assert _extract_sdk_pid(client) is None

    def test_returns_none_on_exception(self) -> None:
        from core.execution.engines.claude.executor import _extract_sdk_pid

        client = MagicMock()
        type(client)._transport = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        assert _extract_sdk_pid(client) is None


# ── Layer 1: _kill_sdk_process ───────────────────────────────


class TestKillSdkProcess:
    """Tests for _kill_sdk_process helper."""

    def test_noop_when_pid_is_none(self) -> None:
        from core.execution.engines.claude.executor import _kill_sdk_process

        _kill_sdk_process(None, None)

    def test_noop_when_process_not_found(self) -> None:
        from core.execution.engines.claude.executor import _kill_sdk_process

        with patch("core.execution.engines.claude.executor.psutil.Process", side_effect=psutil.NoSuchProcess(99999)):
            _kill_sdk_process(99999, None)

    def test_skips_kill_on_pid_reuse(self) -> None:
        from core.execution.engines.claude.executor import _kill_sdk_process

        mock_proc = MagicMock()
        mock_proc.create_time.return_value = 1000.0
        mock_proc.name.return_value = "claude"
        mock_proc.children.return_value = []

        with patch("core.execution.engines.claude.executor.psutil.Process", return_value=mock_proc):
            _kill_sdk_process(123, 900.0)

        mock_proc.kill.assert_not_called()

    def test_kills_process_when_create_time_matches(self) -> None:
        from core.execution.engines.claude.executor import _kill_sdk_process

        mock_proc = MagicMock()
        mock_proc.create_time.return_value = 1000.5
        mock_proc.name.return_value = "claude"
        mock_proc.children.return_value = []

        with patch("core.execution.engines.claude.executor.psutil.Process", return_value=mock_proc):
            _kill_sdk_process(123, 1000.0)

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_not_called()

    def test_kills_process_without_create_time_check(self) -> None:
        from core.execution.engines.claude.executor import _kill_sdk_process

        mock_proc = MagicMock()
        mock_proc.name.return_value = "node"
        mock_proc.children.return_value = []

        with patch("core.execution.engines.claude.executor.psutil.Process", return_value=mock_proc):
            _kill_sdk_process(123, None)

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_not_called()

    def test_skips_non_claude_process(self) -> None:
        from core.execution.engines.claude.executor import _kill_sdk_process

        mock_proc = MagicMock()
        mock_proc.create_time.return_value = 1000.0
        mock_proc.name.return_value = "python3"
        mock_proc.children.return_value = []

        with patch("core.execution.engines.claude.executor.psutil.Process", return_value=mock_proc):
            _kill_sdk_process(123, 1000.0)

        mock_proc.kill.assert_not_called()

    def test_terminates_children_recursively(self) -> None:
        from core.execution.engines.claude.executor import _kill_sdk_process

        child1 = MagicMock()
        child1.pid = 200
        child2 = MagicMock()
        child2.pid = 201

        mock_proc = MagicMock()
        mock_proc.create_time.return_value = 1000.0
        mock_proc.name.return_value = "claude"
        mock_proc.children.return_value = [child1, child2]

        with patch("core.execution.engines.claude.executor.psutil.Process", return_value=mock_proc):
            _kill_sdk_process(123, 1000.0)

        child1.terminate.assert_called_once()
        child2.terminate.assert_called_once()
        mock_proc.terminate.assert_called_once()

    def test_handles_child_already_dead(self) -> None:
        from core.execution.engines.claude.executor import _kill_sdk_process

        child = MagicMock()
        child.pid = 200
        child.terminate.side_effect = psutil.NoSuchProcess(200)

        mock_proc = MagicMock()
        mock_proc.create_time.return_value = 1000.0
        mock_proc.name.return_value = "claude"
        mock_proc.children.return_value = [child]

        with patch("core.execution.engines.claude.executor.psutil.Process", return_value=mock_proc):
            _kill_sdk_process(123, 1000.0)

        mock_proc.terminate.assert_called_once()


# ── Layer 2: _cleanup_orphaned_claude_processes ──────────────


class TestCleanupOrphanedClaudeProcesses:
    """Tests for AnimaRunner._cleanup_orphaned_claude_processes."""

    def _make_runner(self) -> AnimaRunner:  # noqa: F821
        from core.supervisor.runner import AnimaRunner

        runner = AnimaRunner.__new__(AnimaRunner)
        runner.anima_name = "test-anima"
        return runner

    def test_kills_old_claude_processes(self) -> None:
        runner = self._make_runner()

        old_claude = MagicMock()
        old_claude.name.return_value = "claude"
        old_claude.create_time.return_value = time.time() - 8000
        old_claude.pid = 500
        old_claude.children.return_value = []

        current = MagicMock()
        current.children.return_value = [old_claude]

        with (
            patch("core.supervisor.runner.psutil.Process", return_value=current),
            patch("core.supervisor.runner.kill_tree") as kill_tree,
        ):
            runner._cleanup_orphaned_claude_processes()

        kill_tree.assert_called_once_with(500, deepest_first=True)

    def test_does_not_kill_young_claude_processes(self) -> None:
        runner = self._make_runner()

        young_claude = MagicMock()
        young_claude.name.return_value = "claude"
        young_claude.create_time.return_value = time.time() - 1000
        young_claude.pid = 501
        young_claude.children.return_value = []

        current = MagicMock()
        current.children.return_value = [young_claude]

        with (
            patch("core.supervisor.runner.psutil.Process", return_value=current),
            patch("core.supervisor.runner.kill_tree") as kill_tree,
        ):
            runner._cleanup_orphaned_claude_processes()

        kill_tree.assert_not_called()

    def test_ignores_non_claude_processes(self) -> None:
        runner = self._make_runner()

        python_proc = MagicMock()
        python_proc.name.return_value = "python3"
        python_proc.create_time.return_value = time.time() - 9000
        python_proc.pid = 502

        current = MagicMock()
        current.children.return_value = [python_proc]

        with (
            patch("core.supervisor.runner.psutil.Process", return_value=current),
            patch("core.supervisor.runner.kill_tree") as kill_tree,
        ):
            runner._cleanup_orphaned_claude_processes()

        kill_tree.assert_not_called()

    def test_delegates_tree_cleanup_to_platform_helper(self) -> None:
        runner = self._make_runner()

        old_claude = MagicMock()
        old_claude.name.return_value = "claude"
        old_claude.create_time.return_value = time.time() - 8000
        old_claude.pid = 600

        current = MagicMock()
        current.children.return_value = [old_claude]

        with (
            patch("core.supervisor.runner.psutil.Process", return_value=current),
            patch("core.supervisor.runner.kill_tree") as kill_tree,
        ):
            runner._cleanup_orphaned_claude_processes()

        kill_tree.assert_called_once_with(600, deepest_first=True)

    def test_handles_nosuchprocess_gracefully(self) -> None:
        runner = self._make_runner()

        vanishing = MagicMock()
        vanishing.name.side_effect = psutil.NoSuchProcess(700)
        vanishing.pid = 700

        current = MagicMock()
        current.children.return_value = [vanishing]

        with patch("core.supervisor.runner.psutil.Process", return_value=current):
            runner._cleanup_orphaned_claude_processes()

    def test_handles_overall_exception(self) -> None:
        runner = self._make_runner()

        with patch("core.supervisor.runner.psutil.Process", side_effect=RuntimeError("unexpected")):
            runner._cleanup_orphaned_claude_processes()

    @staticmethod
    def _old_claude(pid: int):
        proc = MagicMock()
        proc.pid = pid
        proc.name.return_value = "claude"
        proc.create_time.return_value = time.time() - 10800  # 3 hours < 2-hour threshold
        proc.children.return_value = []
        return proc

    def test_does_not_kill_claude_under_registered_task_runner_job(self) -> None:
        """Task-runner (registered job pid) descendant Claude CLIs must survive."""
        from core.supervisor.runner import AnimaRunner

        runner = AnimaRunner.__new__(AnimaRunner)
        runner.anima_name = "test-anima"

        task_runner_root = MagicMock()
        task_runner_root.pid = 700
        task_runner_root.name.return_value = "python3"
        old_claude_under_runner = self._old_claude(701)
        root_claude = self._old_claude(800)

        current = MagicMock()
        current.children.return_value = [task_runner_root, old_claude_under_runner, root_claude]

        job = MagicMock()
        job.pid = 700
        supervisor = MagicMock()
        supervisor.jobs = {"job1": job}
        runner._scheduler_mgr = MagicMock()
        runner._scheduler_mgr._task_runner_supervisor = supervisor

        def proc_for(pid=None):
            if pid == 700:
                subtree = MagicMock()
                subtree.children.return_value = [old_claude_under_runner]
                return subtree
            return current

        with (
            patch("core.supervisor.runner.psutil.Process", side_effect=proc_for),
            patch("core.supervisor.runner.kill_tree") as kill_tree,
        ):
            runner._cleanup_orphaned_claude_processes()

        kill_tree.assert_called_once_with(800, deepest_first=True)

    def test_does_not_kill_claude_under_cmdline_task_runner(self) -> None:
        """Task-runner roots found by cmdline (spawned but not yet registered) are excluded too."""
        from core.supervisor.runner import AnimaRunner

        runner = AnimaRunner.__new__(AnimaRunner)
        runner.anima_name = "test-anima"
        runner._scheduler_mgr = MagicMock()
        runner._scheduler_mgr._task_runner_supervisor = MagicMock()
        runner._scheduler_mgr._task_runner_supervisor.jobs = {}

        task_runner_root = MagicMock()
        task_runner_root.pid = 710
        task_runner_root.name.return_value = "python3"
        task_runner_root.cmdline.return_value = [
            "python",
            "-m",
            "core.supervisor.task_runner",
            "--anima",
            "sakura",
        ]
        old_claude_under_runner = self._old_claude(711)
        root_claude = self._old_claude(810)

        current = MagicMock()
        current.children.return_value = [task_runner_root, old_claude_under_runner, root_claude]

        def proc_for(pid=None):
            if pid == 710:
                subtree = MagicMock()
                subtree.children.return_value = [old_claude_under_runner]
                return subtree
            return current

        with (
            patch("core.supervisor.runner.psutil.Process", side_effect=proc_for),
            patch("core.supervisor.runner.kill_tree") as kill_tree,
        ):
            runner._cleanup_orphaned_claude_processes()

        kill_tree.assert_called_once_with(810, deepest_first=True)


# ── Layer 2: _orphan_cleanup_loop ────────────────────────────


class TestOrphanCleanupLoop:
    """Tests for AnimaRunner._orphan_cleanup_loop."""

    @pytest.mark.asyncio
    async def test_exits_on_shutdown_event(self) -> None:
        import asyncio

        from core.supervisor.runner import AnimaRunner

        runner = AnimaRunner.__new__(AnimaRunner)
        runner.anima_name = "test-anima"
        runner.shutdown_event = asyncio.Event()

        with patch.object(runner, "_cleanup_orphaned_claude_processes") as mock_cleanup:
            runner.shutdown_event.set()
            await runner._orphan_cleanup_loop()

        mock_cleanup.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_cleanup_on_timeout(self) -> None:
        import asyncio

        from core.supervisor import runner as runner_module
        from core.supervisor.runner import AnimaRunner

        runner = AnimaRunner.__new__(AnimaRunner)
        runner.anima_name = "test-anima"
        runner.shutdown_event = asyncio.Event()

        call_count = 0

        with (
            patch.object(runner_module, "_ORPHAN_CHECK_INTERVAL_SEC", 0.01),
            patch.object(runner, "_cleanup_orphaned_claude_processes") as mock_cleanup,
        ):

            async def _set_shutdown_after_calls():
                nonlocal call_count
                while call_count < 2:
                    await asyncio.sleep(0.05)
                    call_count = mock_cleanup.call_count
                runner.shutdown_event.set()

            task = asyncio.create_task(_set_shutdown_after_calls())
            await runner._orphan_cleanup_loop()
            await task

        assert mock_cleanup.call_count >= 1
