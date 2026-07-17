# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for concurrent stop_anima race condition fix.

Verifies that per-anima stop locks serialize concurrent stop_anima calls,
that handle.stop() runs only once, and that late arrivals are no-ops.
Also checks that restart_anima (stop→start) does not deadlock with the lock.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.supervisor.manager import ProcessSupervisor


@pytest.fixture
def supervisor(tmp_path: Path) -> ProcessSupervisor:
    """Create a ProcessSupervisor with test paths."""
    animas_dir = tmp_path / "animas"
    animas_dir.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()

    return ProcessSupervisor(
        animas_dir=animas_dir,
        shared_dir=shared_dir,
        run_dir=run_dir,
    )


class TestConcurrentStopAnima:
    """Concurrent stop_anima calls on the same anima must be safe."""

    @pytest.mark.asyncio
    async def test_concurrent_stop_serializes_and_pops_once(
        self, supervisor: ProcessSupervisor
    ):
        """Two parallel stop_anima calls: both succeed, stop once, process removed."""
        stop_started = asyncio.Event()
        allow_stop_finish = asyncio.Event()
        stop_call_count = 0

        async def slow_stop(*_args, **_kwargs):
            nonlocal stop_call_count
            stop_call_count += 1
            stop_started.set()
            await allow_stop_finish.wait()

        handle = MagicMock()
        handle.stop = AsyncMock(side_effect=slow_stop)
        supervisor.processes["test-anima"] = handle

        async def run_stop():
            await supervisor.stop_anima("test-anima")

        task1 = asyncio.create_task(run_stop())
        # Wait until first stop is in-flight (holding the lock during await)
        await asyncio.wait_for(stop_started.wait(), timeout=2.0)
        task2 = asyncio.create_task(run_stop())
        # Give task2 a chance to queue on the lock
        await asyncio.sleep(0.05)

        allow_stop_finish.set()
        results = await asyncio.gather(task1, task2, return_exceptions=True)

        assert all(r is None for r in results), f"unexpected results: {results}"
        assert stop_call_count == 1
        handle.stop.assert_awaited_once()
        assert "test-anima" not in supervisor.processes
        assert "test-anima" in supervisor._recently_stopped

    @pytest.mark.asyncio
    async def test_concurrent_stop_via_gather(
        self, supervisor: ProcessSupervisor
    ):
        """asyncio.gather of two stop_anima calls: no KeyError, stop once."""
        stop_gate = asyncio.Event()
        entered = 0

        async def slow_stop(*_args, **_kwargs):
            nonlocal entered
            entered += 1
            # First caller holds; second waits on lock before re-check
            await stop_gate.wait()

        handle = MagicMock()
        handle.stop = AsyncMock(side_effect=slow_stop)
        supervisor.processes["sakura"] = handle

        async def release_after_queued():
            # Allow both tasks to be scheduled; first holds lock inside stop
            await asyncio.sleep(0.05)
            stop_gate.set()

        release_task = asyncio.create_task(release_after_queued())
        results = await asyncio.gather(
            supervisor.stop_anima("sakura"),
            supervisor.stop_anima("sakura"),
            return_exceptions=True,
        )
        await release_task

        assert all(r is None for r in results), f"unexpected results: {results}"
        assert entered == 1
        handle.stop.assert_awaited_once()
        assert "sakura" not in supervisor.processes

    @pytest.mark.asyncio
    async def test_late_stop_is_noop(self, supervisor: ProcessSupervisor):
        """After a successful stop, a subsequent stop_anima is a no-op."""
        handle = MagicMock()
        handle.stop = AsyncMock()
        supervisor.processes["test-anima"] = handle

        await supervisor.stop_anima("test-anima")
        assert "test-anima" not in supervisor.processes
        handle.stop.assert_awaited_once()

        # Second call after completion — no exception, stop not called again
        await supervisor.stop_anima("test-anima")
        handle.stop.assert_awaited_once()
        assert "test-anima" not in supervisor.processes


class TestRestartAnimaWithStopLock:
    """restart_anima must not deadlock with per-anima stop locks."""

    @pytest.mark.asyncio
    async def test_restart_anima_does_not_deadlock(
        self, supervisor: ProcessSupervisor
    ):
        """restart_anima (stop→start) completes with the new stop lock."""
        handle = MagicMock()
        handle.stop = AsyncMock()
        supervisor.processes["test-anima"] = handle

        with patch.object(
            supervisor, "start_anima", new_callable=AsyncMock
        ) as mock_start:
            await asyncio.wait_for(
                supervisor.restart_anima("test-anima"),
                timeout=2.0,
            )

        handle.stop.assert_awaited_once()
        mock_start.assert_awaited_once_with("test-anima")
        assert "test-anima" not in supervisor.processes
        assert "test-anima" not in supervisor._restarting
        assert "test-anima" in supervisor._recently_stopped
