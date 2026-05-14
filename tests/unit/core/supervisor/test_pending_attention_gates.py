from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.memory.task_queue import TaskQueueManager
from core.supervisor.pending_executor import _SENTINEL_CANCELLED, _SENTINEL_DEFERRED, PendingTaskExecutor
from core.taskboard.models import AttentionVisibility
from core.taskboard.store import TaskBoardStore


def _make_executor(tmp_path: Path) -> PendingTaskExecutor:
    data_dir = tmp_path / "data"
    anima_dir = data_dir / "animas" / "sakura"
    anima_dir.mkdir(parents=True, exist_ok=True)

    anima = MagicMock()
    anima.agent.background_manager = MagicMock()
    anima.agent.run_cycle_streaming = AsyncMock()
    anima._background_lock = asyncio.Lock()
    anima._status_slots = {"background": "idle"}
    anima._task_slots = {"background": ""}
    anima._task_semaphore = None
    anima.messenger = MagicMock()

    return PendingTaskExecutor(
        anima=anima,
        anima_name="sakura",
        anima_dir=anima_dir,
        shutdown_event=asyncio.Event(),
    )


def _stop_after_first(executor: PendingTaskExecutor):
    async def _mock(coro, *, timeout):
        coro.close()
        executor._shutdown_event.set()
        raise TimeoutError

    return _mock


def _write_pending(anima_dir: Path, task_id: str) -> Path:
    pending_dir = anima_dir / "state" / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    path = pending_dir / f"{task_id}.json"
    path.write_text(
        json.dumps(
            {
                "task_type": "llm",
                "task_id": task_id,
                "title": "title",
                "description": "description",
                "submitted_at": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    return path


def _store_for(executor: PendingTaskExecutor) -> TaskBoardStore:
    return TaskBoardStore(executor._anima_dir.parent.parent / "shared" / "taskboard.sqlite3")


def _queue_task(executor: PendingTaskExecutor, task_id: str) -> None:
    TaskQueueManager(executor._anima_dir).add_task(
        source="human",
        original_instruction="work",
        assignee="sakura",
        summary="work",
        task_id=task_id,
    )


@pytest.mark.asyncio
async def test_watcher_creates_deferred_and_suppressed_dirs(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)

    with patch("core.supervisor.pending_executor.asyncio.wait_for", side_effect=_stop_after_first(executor)):
        await executor.watcher_loop()

    assert (executor._anima_dir / "state" / "pending" / "deferred").is_dir()
    assert (executor._anima_dir / "state" / "pending" / "suppressed").is_dir()


@pytest.mark.asyncio
async def test_future_snoozed_pending_moves_to_deferred_without_execution(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    _queue_task(executor, "snoozed1234")
    _write_pending(executor._anima_dir, "snoozed1234")
    _store_for(executor).upsert_metadata(
        anima_name="sakura",
        task_id="snoozed1234",
        visibility=AttentionVisibility.SNOOZED,
        snoozed_until=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )

    with (
        patch.object(executor, "execute_pending_task", new_callable=AsyncMock) as execute,
        patch("core.supervisor.pending_executor.asyncio.wait_for", side_effect=_stop_after_first(executor)),
    ):
        await executor.watcher_loop()

    assert not execute.called
    assert (executor._anima_dir / "state" / "pending" / "deferred" / "snoozed1234.json").exists()
    assert not (executor._anima_dir / "state" / "pending" / "snoozed1234.json").exists()


@pytest.mark.asyncio
async def test_elapsed_snoozed_deferred_returns_to_pending_and_executes(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    _queue_task(executor, "elapsed1234")
    deferred = executor._anima_dir / "state" / "pending" / "deferred"
    deferred.mkdir(parents=True, exist_ok=True)
    (_write_pending(executor._anima_dir, "elapsed1234")).rename(deferred / "elapsed1234.json")
    _store_for(executor).upsert_metadata(
        anima_name="sakura",
        task_id="elapsed1234",
        visibility=AttentionVisibility.SNOOZED,
        snoozed_until=(datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    )

    with (
        patch.object(executor, "execute_pending_task", new_callable=AsyncMock) as execute,
        patch("core.supervisor.pending_executor.asyncio.wait_for", side_effect=_stop_after_first(executor)),
    ):
        await executor.watcher_loop()

    execute.assert_awaited_once()
    assert not (deferred / "elapsed1234.json").exists()
    assert _store_for(executor).get_metadata("sakura", "elapsed1234").visibility == AttentionVisibility.ACTIVE


@pytest.mark.asyncio
async def test_archived_pending_moves_to_suppressed_and_cancels_queue(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    _queue_task(executor, "archived1234")
    _write_pending(executor._anima_dir, "archived1234")
    _store_for(executor).upsert_metadata(
        anima_name="sakura",
        task_id="archived1234",
        visibility=AttentionVisibility.ARCHIVED,
    )

    with (
        patch.object(executor, "execute_pending_task", new_callable=AsyncMock) as execute,
        patch("core.supervisor.pending_executor.asyncio.wait_for", side_effect=_stop_after_first(executor)),
    ):
        await executor.watcher_loop()

    assert not execute.called
    assert (executor._anima_dir / "state" / "pending" / "suppressed" / "archived1234.json").exists()
    entry = TaskQueueManager(executor._anima_dir).get_task_by_id("archived1234")
    assert entry is not None
    assert entry.status == "cancelled"
    assert entry.summary == "archived by TaskBoard"


@pytest.mark.asyncio
async def test_run_llm_task_final_defense_skips_suppressed_task(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    _queue_task(executor, "blocked1234")
    _store_for(executor).upsert_metadata(
        anima_name="sakura",
        task_id="blocked1234",
        visibility=AttentionVisibility.TOMBSTONED,
    )

    result = await executor._run_llm_task(
        {
            "task_id": "blocked1234",
            "task_type": "llm",
            "title": "title",
            "description": "description",
            "submitted_at": datetime.now(UTC).isoformat(),
        }
    )

    assert result == _SENTINEL_CANCELLED
    assert not executor._anima.agent.run_cycle_streaming.called


@pytest.mark.asyncio
async def test_run_llm_task_final_defense_defers_snoozed_task(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    _queue_task(executor, "snoozed1234")
    _store_for(executor).upsert_metadata(
        anima_name="sakura",
        task_id="snoozed1234",
        visibility=AttentionVisibility.SNOOZED,
        snoozed_until=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )

    result = await executor._run_llm_task(
        {
            "task_id": "snoozed1234",
            "task_type": "llm",
            "title": "title",
            "description": "description",
            "submitted_at": datetime.now(UTC).isoformat(),
        }
    )

    assert result == _SENTINEL_DEFERRED
    assert not executor._anima.agent.run_cycle_streaming.called
    assert (executor._anima_dir / "state" / "pending" / "deferred" / "snoozed1234.json").exists()
    entry = TaskQueueManager(executor._anima_dir).get_task_by_id("snoozed1234")
    assert entry is not None
    assert entry.status == "pending"


@pytest.mark.asyncio
async def test_batch_dependency_suppressed_fails_dependent(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    _queue_task(executor, "parent1234")
    _queue_task(executor, "child1234")
    _store_for(executor).upsert_metadata(
        anima_name="sakura",
        task_id="parent1234",
        visibility=AttentionVisibility.ARCHIVED,
    )

    with patch.object(executor, "_run_llm_task", new_callable=AsyncMock) as run_llm_task:
        await executor._dispatch_batch(
            "batch-1",
            [
                {"task_id": "parent1234", "task_type": "llm", "parallel": False},
                {"task_id": "child1234", "task_type": "llm", "parallel": False, "depends_on": ["parent1234"]},
            ],
        )

    assert not run_llm_task.called
    queue = TaskQueueManager(executor._anima_dir)
    parent = queue.get_task_by_id("parent1234")
    child = queue.get_task_by_id("child1234")
    assert parent is not None
    assert child is not None
    assert parent.status == "cancelled"
    assert parent.summary == "archived by TaskBoard"
    assert child.status == "failed"
    assert child.summary == "FAILED: dependency_suppressed"


@pytest.mark.asyncio
async def test_batch_snoozed_task_is_deferred_not_cancelled(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    _queue_task(executor, "snoozed1234")
    _queue_task(executor, "child1234")
    _store_for(executor).upsert_metadata(
        anima_name="sakura",
        task_id="snoozed1234",
        visibility=AttentionVisibility.SNOOZED,
        snoozed_until=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    )

    with patch.object(executor, "_run_llm_task", new_callable=AsyncMock) as run_llm_task:
        await executor._dispatch_batch(
            "batch-1",
            [
                {"task_id": "snoozed1234", "task_type": "llm", "parallel": False},
                {"task_id": "child1234", "task_type": "llm", "parallel": False, "depends_on": ["snoozed1234"]},
            ],
        )

    assert not run_llm_task.called
    queue = TaskQueueManager(executor._anima_dir)
    snoozed = queue.get_task_by_id("snoozed1234")
    child = queue.get_task_by_id("child1234")
    assert snoozed is not None
    assert child is not None
    assert snoozed.status == "pending"
    assert snoozed.summary == "snoozed by TaskBoard"
    assert (executor._anima_dir / "state" / "pending" / "deferred" / "snoozed1234.json").exists()
    assert child.status == "failed"
    assert child.summary == "FAILED: failed_dependency"


@pytest.mark.asyncio
async def test_batch_dependency_suppressed_before_grouping_still_fails_dependent(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    _queue_task(executor, "parent1234")
    _queue_task(executor, "child1234")
    _store_for(executor).upsert_metadata(
        anima_name="sakura",
        task_id="parent1234",
        visibility=AttentionVisibility.ARCHIVED,
    )

    with patch.object(executor, "_run_llm_task", new_callable=AsyncMock) as run_llm_task:
        await executor._dispatch_batch(
            "batch-1",
            [
                {"task_id": "child1234", "task_type": "llm", "parallel": False, "depends_on": ["parent1234"]},
            ],
        )

    assert not run_llm_task.called
    queue = TaskQueueManager(executor._anima_dir)
    parent = queue.get_task_by_id("parent1234")
    child = queue.get_task_by_id("child1234")
    assert parent is not None
    assert child is not None
    assert parent.status == "cancelled"
    assert parent.summary == "archived by TaskBoard"
    assert child.status == "failed"
    assert child.summary == "FAILED: dependency_suppressed"
