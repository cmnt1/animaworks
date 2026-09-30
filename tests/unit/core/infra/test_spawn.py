from __future__ import annotations

import asyncio
import gc
import weakref

import pytest

from core.infra.tasks import _background_tasks, spawn


@pytest.mark.asyncio
async def test_spawn_keeps_a_strong_reference_until_task_completes() -> None:
    started = asyncio.Event()
    blocker = asyncio.Event()

    async def wait_for_release() -> None:
        started.set()
        await blocker.wait()

    task = spawn(wait_for_release(), name="test-strong-reference")
    await started.wait()
    reference = weakref.ref(task)
    assert task in _background_tasks

    del task
    gc.collect()

    assert reference() is not None
    held_task = reference()
    assert held_task is not None
    held_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await held_task
    await asyncio.sleep(0)
    assert held_task not in _background_tasks


@pytest.mark.asyncio
async def test_spawn_logs_task_exception(caplog: pytest.LogCaptureFixture) -> None:
    async def fail() -> None:
        raise ValueError("background failure")

    task = spawn(fail(), name="test-failing-task")
    with pytest.raises(ValueError, match="background failure"):
        await task
    await asyncio.sleep(0)

    assert "Background task test-failing-task failed" in caplog.text
    assert "ValueError: background failure" in caplog.text


@pytest.mark.asyncio
async def test_spawn_does_not_log_cancelled_task(caplog: pytest.LogCaptureFixture) -> None:
    blocker = asyncio.Event()

    async def wait_forever() -> None:
        await blocker.wait()

    task = spawn(wait_forever(), name="test-cancelled-task")
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0)

    assert "test-cancelled-task" not in caplog.text
