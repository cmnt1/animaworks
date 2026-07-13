from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from core.anima import BackgroundWorkerSlot, DigitalAnima
from core.supervisor.pending_executor import PendingTaskExecutor


def _slot(slot_id: int) -> BackgroundWorkerSlot:
    return BackgroundWorkerSlot(
        slot_id=slot_id,
        agent=MagicMock(name=f"worker_agent_{slot_id}"),
        session_lock=asyncio.Lock(),
        interrupt_event=asyncio.Event(),
    )


def _bare_pool_anima(pool_size: int) -> DigitalAnima:
    anima = DigitalAnima.__new__(DigitalAnima)
    anima.name = "pool-test"
    anima._background_worker_pool_size = pool_size
    anima._background_worker_slots = [_slot(slot_id) for slot_id in range(pool_size)]
    anima._background_worker_queue = asyncio.Queue()
    for slot in anima._background_worker_slots:
        anima._background_worker_queue.put_nowait(slot)
    anima._active_background_workers = {}
    anima._background_worker_gate_lock = asyncio.Lock()
    anima._background_worker_gate_count = 0
    anima._background_lock = asyncio.Lock()
    anima._mark_busy_start = MagicMock()
    anima._mark_busy_progress = MagicMock()
    anima._clear_busy_status_sidecar_if_idle = MagicMock()
    anima._on_lock_released = None
    return anima


async def test_worker_lease_waits_at_capacity_and_release_unblocks() -> None:
    anima = _bare_pool_anima(pool_size=2)

    first = await anima._acquire_background_worker("task-one")
    second = await anima._acquire_background_worker("task-two")
    waiting = asyncio.create_task(anima._acquire_background_worker("task-three"))
    await asyncio.sleep(0)

    assert not waiting.done()
    assert anima._background_lock.locked()
    assert set(anima._active_background_workers.values()) == {"task-one", "task-two"}

    await anima._release_background_worker(first)
    third = await asyncio.wait_for(waiting, timeout=1)

    assert third is first
    assert anima._background_lock.locked()
    assert set(anima._active_background_workers.values()) == {"task-two", "task-three"}

    await anima._release_background_worker(second)
    assert anima._background_lock.locked()
    await anima._release_background_worker(third)

    assert not anima._background_lock.locked()
    assert anima._background_worker_queue.qsize() == 2
    anima._mark_busy_start.assert_called_once_with()


def test_pool_size_one_reuses_legacy_background_agent_and_session() -> None:
    anima = DigitalAnima.__new__(DigitalAnima)
    background_agent = MagicMock(name="legacy_background_agent")
    background_session_lock = asyncio.Lock()
    anima._background_worker_pool_size = 1
    anima._lane_agents = {"background": background_agent}
    anima._agent_session_locks = {"background": background_session_lock}
    anima._interrupt_events = {}
    anima._background_worker_slots = []
    anima._background_worker_queue = asyncio.Queue()

    anima._initialize_background_worker_pool()

    assert len(anima._background_worker_slots) == 1
    slot = anima._background_worker_slots[0]
    assert slot.slot_id == 0
    assert slot.agent is background_agent
    assert slot.session_lock is background_session_lock
    assert slot.interrupt_event is anima._get_interrupt_event("_background")
    assert anima._background_worker_queue.get_nowait() is slot


class _PoolStub:
    def __init__(self, pool_size: int) -> None:
        self._background_worker_pool_size = pool_size
        self._available: asyncio.Queue[BackgroundWorkerSlot] = asyncio.Queue()
        for slot_id in range(pool_size):
            self._available.put_nowait(_slot(slot_id))

    async def _acquire_background_worker(self, task_id: str) -> BackgroundWorkerSlot:
        return await self._available.get()

    async def _release_background_worker(self, slot: BackgroundWorkerSlot) -> None:
        self._available.put_nowait(slot)


def _executor(tmp_path: Path, *, pool_size: int = 2) -> PendingTaskExecutor:
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()
    return PendingTaskExecutor(
        anima=_PoolStub(pool_size),
        anima_name="pool-test",
        anima_dir=anima_dir,
        shutdown_event=asyncio.Event(),
    )


async def _measure_workspace_concurrency(
    executor: PendingTaskExecutor,
    task_descriptions: list[dict[str, str]],
) -> int:
    active = 0
    maximum_active = 0

    async def fake_run_llm_task(*args, **kwargs) -> str:
        nonlocal active, maximum_active
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.03)
        active -= 1
        return "ok"

    executor._run_llm_task = fake_run_llm_task  # type: ignore[method-assign]
    await asyncio.gather(*(executor._run_task_in_worker(task) for task in task_descriptions))
    return maximum_active


async def test_same_resolved_workspace_is_exclusive(tmp_path: Path) -> None:
    executor = _executor(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    maximum_active = await _measure_workspace_concurrency(
        executor,
        [
            {"task_id": "same-one", "working_directory": str(workspace)},
            {"task_id": "same-two", "working_directory": str(workspace / ".")},
        ],
    )

    assert maximum_active == 1
    assert len(executor._workspace_locks) == 1


async def test_distinct_workspaces_can_overlap(tmp_path: Path) -> None:
    executor = _executor(tmp_path)
    first_workspace = tmp_path / "workspace-one"
    second_workspace = tmp_path / "workspace-two"
    first_workspace.mkdir()
    second_workspace.mkdir()

    maximum_active = await _measure_workspace_concurrency(
        executor,
        [
            {"task_id": "distinct-one", "working_directory": str(first_workspace)},
            {"task_id": "distinct-two", "working_directory": str(second_workspace)},
        ],
    )

    assert maximum_active == 2
    assert len(executor._workspace_locks) == 2


def test_active_worker_is_busy_and_drives_primary_status() -> None:
    anima = DigitalAnima.__new__(DigitalAnima)
    anima._conversation_locks = {}
    anima._background_lock = asyncio.Lock()
    anima._inbox_lock = asyncio.Lock()
    anima._active_background_workers = {1: "worker-task"}
    anima._status_slots = {"inbox": "idle", "background": "idle"}
    anima._task_slots = {"inbox": "", "background": ""}

    assert anima._has_active_busy_lock() is True
    assert anima.primary_status == "task_exec"
    assert anima.primary_task == "worker-task"

    anima._active_background_workers.clear()

    assert anima._has_active_busy_lock() is False
    assert anima.primary_status == "idle"
    assert anima.primary_task == ""
