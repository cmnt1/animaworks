"""Unit tests for LifecycleMixin cron command zombie prevention."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestRunCronCommandZombieReap:
    """Tests for run_cron_command() reaping subprocess on CancelledError."""

    def _make_anima_stub(self):
        """Build a minimal LifecycleMixin-compatible stub."""
        from core._anima_lifecycle import LifecycleMixin

        stub = MagicMock(spec=LifecycleMixin)
        stub.name = "test-anima"
        stub._background_lock = asyncio.Lock()
        stub._mark_busy_start = MagicMock()
        stub._cron_idle = asyncio.Event()
        stub._status_slots = {"background": "idle"}
        stub._task_slots = {"background": ""}
        stub._notify_lock_released = MagicMock()
        stub._last_activity = None

        mock_handler = MagicMock()
        mock_handler.set_active_session_type = MagicMock(return_value="token")
        mock_handler.set_session_origin = MagicMock()
        stub.agent = MagicMock()
        stub.agent._tool_handler = mock_handler

        stub.memory = MagicMock()
        stub._activity = MagicMock()

        return stub

    @pytest.mark.asyncio
    async def test_cron_command_reaps_on_cancellation(self):
        """When CancelledError interrupts communicate(), the subprocess is killed and waited."""
        stub = self._make_anima_stub()

        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.communicate = AsyncMock(side_effect=asyncio.CancelledError())
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("asyncio.create_subprocess_shell", return_value=mock_proc),
            patch("core.tooling.handler.active_session_type") as mock_ast,
        ):
            mock_ast.reset = MagicMock()
            from core._anima_lifecycle import LifecycleMixin

            try:
                await LifecycleMixin.run_cron_command(
                    stub,
                    task_name="test-task",
                    command="echo hello",
                )
            except (asyncio.CancelledError, Exception):
                pass

        mock_proc.kill.assert_called_once()
        mock_proc.wait.assert_awaited()

    @pytest.mark.asyncio
    async def test_cron_command_skips_reap_on_completed_process(self):
        """When process completes normally, the finally block does not kill/wait again."""
        stub = self._make_anima_stub()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"output", b""))

        with (
            patch("asyncio.create_subprocess_shell", return_value=mock_proc),
            patch("core.tooling.handler.active_session_type") as mock_ast,
        ):
            mock_ast.reset = MagicMock()
            from core._anima_lifecycle import LifecycleMixin

            result = await LifecycleMixin.run_cron_command(
                stub,
                task_name="test-task",
                command="echo hello",
            )

        mock_proc.kill.assert_not_called()
        assert result["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_cron_command_fails_when_success_path_missing(self):
        """A successful command is marked failed when required output is absent."""
        stub = self._make_anima_stub()

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"ok", b""))

        with (
            patch("asyncio.create_subprocess_shell", return_value=mock_proc),
            patch("core.tooling.handler.active_session_type") as mock_ast,
        ):
            mock_ast.reset = MagicMock()
            from core._anima_lifecycle import LifecycleMixin

            result = await LifecycleMixin.run_cron_command(
                stub,
                task_name="test-task",
                command="echo hello",
                success_paths=["Z:/definitely/missing/{YYYYMMDD}.md"],
            )

        assert result["exit_code"] == 1
        assert "Cron success path check failed" in result["stderr"]
