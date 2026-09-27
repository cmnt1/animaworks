# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""E2E tests for the unified restart state machine and worker.

Verifies:
- Reaching the failure threshold surfaces FAILED in get_process_status
- Auto-recovery continues past the threshold (no cap that stops retries)
- The `_restarting` set is cleaned up after the worker finishes
- A duplicate failure while the worker is running is skipped by the guard
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.supervisor.manager import ProcessSupervisor, RestartPolicy
from core.supervisor.process_handle import ProcessState


@pytest.fixture
def supervisor(tmp_path: Path) -> ProcessSupervisor:
    """Create a ProcessSupervisor with test paths and a small backoff policy."""
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
        restart_policy=RestartPolicy(
            max_retries=3,
            backoff_base_sec=1.0,
            backoff_max_sec=10.0,
            reset_after_sec=300.0,
        ),
    )


class _FakeTime:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _patch_sleep(ft: _FakeTime):
    async def _fast_sleep(duration: float) -> None:
        ft.t += duration

    return patch("core.supervisor._mgr_health.asyncio.sleep", _fast_sleep)


class TestFailureToRestartFlow:
    async def test_failure_ensures_worker_and_surfaces_failed(self, supervisor: ProcessSupervisor):
        """Reaching the threshold surfaces FAILED; a restart worker is ensured."""
        name = "test-anima"
        ctl = supervisor._restart_ctl
        handle = MagicMock()
        handle.state = ProcessState.RUNNING
        supervisor.processes[name] = handle
        supervisor._maybe_repair_rag_before_restart = AsyncMock(return_value=False)
        supervisor._ensure_restart_worker = MagicMock()
        for _ in range(2):
            ctl.record_failure(name, "e")

        await supervisor._handle_process_failure(name, handle, reason="boom")

        assert ctl.is_failed(name)
        supervisor._ensure_restart_worker.assert_called_once_with(name)

        # FAILED remains visible in status even after the process is gone.
        supervisor.processes.pop(name, None)
        status = supervisor.get_process_status(name)
        assert status["status"] == "error"
        assert status["restart_state"] == "failed"
        assert status["last_error"] == "boom"

    async def test_auto_recovery_continues_past_threshold(self, supervisor: ProcessSupervisor):
        """The worker keeps retrying beyond max_retries (FAILED never stops it)."""
        ft = _FakeTime()
        supervisor._restart_ctl._clock = ft  # inject fake monotonic clock
        name = "persistent"
        start = AsyncMock(
            side_effect=[
                RuntimeError("d1"),
                RuntimeError("d2"),
                RuntimeError("d3"),
                RuntimeError("d4"),
                RuntimeError("d5"),
                None,  # 6th attempt succeeds
            ],
        )
        supervisor.start_anima = start  # type: ignore[method-assign]

        with _patch_sleep(ft):
            await supervisor._restart_worker(name)

        # 6 attempts, well past threshold=3 — auto-recovery continued.
        assert start.await_count == 6
        assert supervisor._restart_ctl.get(name).phase.value == "healthy"
        # _restarting is cleaned up after the worker finishes.
        assert name not in supervisor._restarting

    async def test_restarting_set_cleaned_even_on_worker_error(self, supervisor: ProcessSupervisor):
        """The worker's finally block clears _restarting even on persistent error."""
        ft = _FakeTime()
        supervisor._restart_ctl._clock = ft
        name = "crash-anima"
        supervisor.start_anima = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]

        # Run the worker but limit it to a few loop iterations, then cancel.
        task = asyncio.create_task(supervisor._restart_worker(name))
        with _patch_sleep(ft):
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert name not in supervisor._restarting

    async def test_duplicate_failure_is_skipped_by_restarting_guard(self, supervisor: ProcessSupervisor):
        """A second call while the worker is running must return immediately."""
        name = "double-fail"
        ctl = supervisor._restart_ctl
        supervisor._restarting.add(name)  # simulate an in-flight worker

        handle = MagicMock()
        await supervisor._handle_process_failure(name, handle)

        # Guard returned before recording anything.
        assert ctl.get(name) is None
        supervisor._restarting.discard(name)
