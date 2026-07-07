"""Unit tests for ProcessSupervisor zombie reaper loop."""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from core.supervisor.manager import ProcessSupervisor


@pytest.fixture
def supervisor(tmp_path: Path) -> ProcessSupervisor:
    """Create a minimal ProcessSupervisor."""
    return ProcessSupervisor(
        animas_dir=tmp_path / "animas",
        shared_dir=tmp_path / "shared",
        run_dir=tmp_path / "run",
        log_dir=tmp_path / "logs",
    )


class TestZombieReaperLoop:
    """Tests for _zombie_reaper_loop() in ProcessSupervisor."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(os.name == "nt", reason="os.WNOHANG not available on Windows")
    async def test_reaper_reaps_zombies(self, supervisor: ProcessSupervisor):
        """Zombie reaper should call os.waitpid and log reaped count."""
        call_count = 0

        def mock_waitpid(pid, options):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return (12344 + call_count, 0)
            return (0, 0)

        original_sleep = asyncio.sleep

        async def shutdown_after_one_cycle(duration):
            supervisor._shutdown = True
            await original_sleep(0)

        with (
            patch("os.waitpid", side_effect=mock_waitpid),
            patch.object(asyncio, "sleep", side_effect=shutdown_after_one_cycle),
        ):
            await supervisor._zombie_reaper_loop()

        assert call_count == 3

    @pytest.mark.asyncio
    async def test_reaper_handles_no_children(self, supervisor: ProcessSupervisor):
        """Zombie reaper should handle ChildProcessError (no children) gracefully."""
        original_sleep = asyncio.sleep

        async def shutdown_after_one_cycle(duration):
            supervisor._shutdown = True
            await original_sleep(0)

        with (
            patch("os.waitpid", side_effect=ChildProcessError("No child processes")),
            patch.object(asyncio, "sleep", side_effect=shutdown_after_one_cycle),
        ):
            await supervisor._zombie_reaper_loop()

    @pytest.mark.asyncio
    async def test_reaper_stops_on_cancel(self, supervisor: ProcessSupervisor):
        """Zombie reaper should exit cleanly on CancelledError."""

        async def cancel_sleep(_duration):
            raise asyncio.CancelledError()

        with patch.object(asyncio, "sleep", side_effect=cancel_sleep):
            await supervisor._zombie_reaper_loop()

    @pytest.mark.asyncio
    async def test_reaper_survives_unexpected_exception(self, supervisor: ProcessSupervisor):
        """Zombie reaper should continue after unexpected exceptions in waitpid."""
        cycle_count = 0
        original_sleep = asyncio.sleep

        async def counting_sleep(_duration):
            nonlocal cycle_count
            cycle_count += 1
            if cycle_count >= 2:
                supervisor._shutdown = True
            await original_sleep(0)

        with (
            patch("os.waitpid", side_effect=OSError("unexpected")),
            patch.object(asyncio, "sleep", side_effect=counting_sleep),
        ):
            await supervisor._zombie_reaper_loop()

        assert cycle_count >= 2

    @pytest.mark.asyncio
    async def test_shutdown_all_cancels_reaper(self, supervisor: ProcessSupervisor):
        """shutdown_all() should cancel the zombie reaper task."""
        reaper_running = asyncio.Event()

        async def slow_reaper():
            reaper_running.set()
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                pass

        supervisor._zombie_reaper_task = asyncio.create_task(slow_reaper())
        await reaper_running.wait()

        await supervisor.shutdown_all()

        assert supervisor._zombie_reaper_task.done()
