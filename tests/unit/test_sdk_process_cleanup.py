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
        from core.execution.agent_sdk import _extract_sdk_pid

        client = MagicMock()
        client._transport._process.pid = 12345
        assert _extract_sdk_pid(client) == 12345

    def test_returns_none_when_no_transport(self) -> None:
        from core.execution.agent_sdk import _extract_sdk_pid

        client = MagicMock(spec=[])
        assert _extract_sdk_pid(client) is None

    def test_returns_none_when_transport_is_none(self) -> None:
        from core.execution.agent_sdk import _extract_sdk_pid

        client = MagicMock()
        client._transport = None
        assert _extract_sdk_pid(client) is None

    def test_returns_none_when_process_is_none(self) -> None:
        from core.execution.agent_sdk import _extract_sdk_pid

        client = MagicMock()
        client._transport._process = None
        assert _extract_sdk_pid(client) is None

    def test_returns_none_when_pid_is_zero(self) -> None:
        from core.execution.agent_sdk import _extract_sdk_pid

        client = MagicMock()
        client._transport._process.pid = 0
        assert _extract_sdk_pid(client) is None

    def test_returns_none_when_pid_is_negative(self) -> None:
        from core.execution.agent_sdk import _extract_sdk_pid

        client = MagicMock()
        client._transport._process.pid = -1
        assert _extract_sdk_pid(client) is None

    def test_returns_none_on_exception(self) -> None:
        from core.execution.agent_sdk import _extract_sdk_pid

        client = MagicMock()
        type(client)._transport = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
        assert _extract_sdk_pid(client) is None


# ── Layer 1: _kill_sdk_process ───────────────────────────────


class TestKillSdkProcess:
    """Tests for _kill_sdk_process helper."""

    def test_noop_when_pid_is_none(self) -> None:
        from core.execution.agent_sdk import _kill_sdk_process

        _kill_sdk_process(None, None)

    def test_noop_when_process_not_found(self) -> None:
        from core.execution.agent_sdk import _kill_sdk_process

        with patch("core.execution.agent_sdk.psutil.Process", side_effect=psutil.NoSuchProcess(99999)):
            _kill_sdk_process(99999, None)

    def test_skips_kill_on_pid_reuse(self) -> None:
        from core.execution.agent_sdk import _kill_sdk_process

        mock_proc = MagicMock()
        mock_proc.create_time.return_value = 1000.0
        mock_proc.name.return_value = "claude"
        mock_proc.children.return_value = []

        with patch("core.execution.agent_sdk.psutil.Process", return_value=mock_proc):
            _kill_sdk_process(123, 900.0)

        mock_proc.kill.assert_not_called()

    def test_kills_process_when_create_time_matches(self) -> None:
        from core.execution.agent_sdk import _kill_sdk_process

        mock_proc = MagicMock()
        mock_proc.create_time.return_value = 1000.5
        mock_proc.name.return_value = "claude"
        mock_proc.children.return_value = []

        with patch("core.execution.agent_sdk.psutil.Process", return_value=mock_proc):
            _kill_sdk_process(123, 1000.0)

        mock_proc.kill.assert_called_once()

    def test_kills_process_without_create_time_check(self) -> None:
        from core.execution.agent_sdk import _kill_sdk_process

        mock_proc = MagicMock()
        mock_proc.name.return_value = "node"
        mock_proc.children.return_value = []

        with patch("core.execution.agent_sdk.psutil.Process", return_value=mock_proc):
            _kill_sdk_process(123, None)

        mock_proc.kill.assert_called_once()

    def test_skips_non_claude_process(self) -> None:
        from core.execution.agent_sdk import _kill_sdk_process

        mock_proc = MagicMock()
        mock_proc.create_time.return_value = 1000.0
        mock_proc.name.return_value = "python3"
        mock_proc.children.return_value = []

        with patch("core.execution.agent_sdk.psutil.Process", return_value=mock_proc):
            _kill_sdk_process(123, 1000.0)

        mock_proc.kill.assert_not_called()

    def test_kills_children_recursively(self) -> None:
        from core.execution.agent_sdk import _kill_sdk_process

        child1 = MagicMock()
        child1.pid = 200
        child2 = MagicMock()
        child2.pid = 201

        mock_proc = MagicMock()
        mock_proc.create_time.return_value = 1000.0
        mock_proc.name.return_value = "claude"
        mock_proc.children.return_value = [child1, child2]

        with patch("core.execution.agent_sdk.psutil.Process", return_value=mock_proc):
            _kill_sdk_process(123, 1000.0)

        child1.kill.assert_called_once()
        child2.kill.assert_called_once()
        mock_proc.kill.assert_called_once()

    def test_handles_child_already_dead(self) -> None:
        from core.execution.agent_sdk import _kill_sdk_process

        child = MagicMock()
        child.pid = 200
        child.kill.side_effect = psutil.NoSuchProcess(200)

        mock_proc = MagicMock()
        mock_proc.create_time.return_value = 1000.0
        mock_proc.name.return_value = "claude"
        mock_proc.children.return_value = [child]

        with patch("core.execution.agent_sdk.psutil.Process", return_value=mock_proc):
            _kill_sdk_process(123, 1000.0)

        mock_proc.kill.assert_called_once()


# ── Layer 2: _cleanup_orphaned_claude_processes ──────────────


class TestCleanupOrphanedClaudeProcesses:
    """Tests for AnimaRunner._cleanup_orphaned_claude_processes."""

    def _make_runner(self) -> "AnimaRunner":  # noqa: F821
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

        with patch("core.supervisor.runner.psutil.Process", return_value=current):
            runner._cleanup_orphaned_claude_processes()

        old_claude.kill.assert_called_once()

    def test_does_not_kill_young_claude_processes(self) -> None:
        runner = self._make_runner()

        young_claude = MagicMock()
        young_claude.name.return_value = "claude"
        young_claude.create_time.return_value = time.time() - 1000
        young_claude.pid = 501
        young_claude.children.return_value = []

        current = MagicMock()
        current.children.return_value = [young_claude]

        with patch("core.supervisor.runner.psutil.Process", return_value=current):
            runner._cleanup_orphaned_claude_processes()

        young_claude.kill.assert_not_called()

    def test_ignores_non_claude_processes(self) -> None:
        runner = self._make_runner()

        python_proc = MagicMock()
        python_proc.name.return_value = "python3"
        python_proc.create_time.return_value = time.time() - 9000
        python_proc.pid = 502

        current = MagicMock()
        current.children.return_value = [python_proc]

        with patch("core.supervisor.runner.psutil.Process", return_value=current):
            runner._cleanup_orphaned_claude_processes()

        python_proc.kill.assert_not_called()

    def test_kills_descendants_before_parent(self) -> None:
        runner = self._make_runner()

        grandchild = MagicMock()
        grandchild.pid = 601
        grandchild.name.return_value = "node"

        def _parent_depth(p: MagicMock) -> int:
            if p is grandchild:
                return 3
            return 2

        grandchild.parents.return_value = [MagicMock(), MagicMock(), MagicMock()]

        old_claude = MagicMock()
        old_claude.name.return_value = "claude"
        old_claude.create_time.return_value = time.time() - 8000
        old_claude.pid = 600
        old_claude.children.return_value = [grandchild]

        current = MagicMock()
        current.children.return_value = [old_claude]

        with patch("core.supervisor.runner.psutil.Process", return_value=current):
            runner._cleanup_orphaned_claude_processes()

        grandchild.kill.assert_called_once()
        old_claude.kill.assert_called_once()

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
        original_interval = runner_module._ORPHAN_CHECK_INTERVAL_SEC

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
