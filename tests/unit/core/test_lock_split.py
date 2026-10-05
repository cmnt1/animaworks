from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.anima.digital_anima import BackgroundWorkerSlot, DigitalAnima
from core.anima.lifecycle import LifecycleMixin
from core.schemas import CycleResult
from core.tasks.pending_executor import PendingTaskExecutor


def _worker_anima() -> DigitalAnima:
    anima = DigitalAnima.__new__(DigitalAnima)
    anima.name = "lock-split-test"
    anima._background_lock = asyncio.Lock()
    anima._inbox_lock = asyncio.Lock()
    anima._conversation_locks = {}
    anima._active_background_workers = {}
    anima._background_worker_gate_lock = asyncio.Lock()
    anima._background_worker_gate_count = 0
    anima._background_worker_queue = asyncio.Queue()
    anima._on_lock_released = None
    anima._mark_busy_start = MagicMock()
    anima._mark_busy_progress = MagicMock()
    anima._notify_lock_released = MagicMock()
    anima._isolated_busy_jobs_provider = None
    slot = BackgroundWorkerSlot(0, MagicMock(), asyncio.Lock(), asyncio.Event())
    anima._background_worker_queue.put_nowait(slot)
    anima._status_slots = {"inbox": "idle", "background": "idle"}
    anima._task_slots = {"inbox": "", "background": ""}
    return anima


@pytest.mark.asyncio
async def test_taskexec_worker_does_not_hold_scheduled_lock_or_block_heartbeat() -> None:
    anima = _worker_anima()
    slot = await anima._acquire_background_worker("task-1")
    assert not anima._background_lock.locked()

    heartbeat_started = asyncio.Event()
    finish_heartbeat = asyncio.Event()
    events: dict[str, asyncio.Event] = {}
    anima._interrupt_events = events
    anima._get_interrupt_event = lambda name: events.setdefault(name, asyncio.Event())
    anima._keepalive_while_busy = AsyncMock()
    anima._build_heartbeat_prompt = AsyncMock(return_value=["heartbeat prompt"])
    anima._run_heartbeat_agent_session = AsyncMock()
    anima._finalize_session_if_ended = AsyncMock()
    anima._trigger_pending_task_execution = MagicMock()
    anima._last_heartbeat = None
    anima.messenger = MagicMock()
    anima.messenger.has_unread.return_value = False
    anima._activity = MagicMock()
    anima._activity.alog = AsyncMock()

    async def run_agent(_prompt: str, _keepalive) -> CycleResult:
        heartbeat_started.set()
        await finish_heartbeat.wait()
        return CycleResult(trigger="heartbeat", action="completed")

    anima._run_heartbeat_agent_session.side_effect = run_agent
    heartbeat = asyncio.create_task(LifecycleMixin.run_heartbeat(anima))
    await asyncio.wait_for(heartbeat_started.wait(), timeout=1)

    assert anima._status_slots["background"] == "checking"
    assert anima._background_lock.locked()
    await anima._release_background_worker(slot)
    # Releasing TaskExec must not overwrite the scheduled heartbeat status.
    assert anima._status_slots["background"] == "checking"

    finish_heartbeat.set()
    await asyncio.wait_for(heartbeat, timeout=1)
    assert anima._status_slots["background"] == "idle"


@pytest.mark.asyncio
async def test_busy_lock_reports_worker_and_scheduled_work_independently() -> None:
    anima = _worker_anima()

    anima._active_background_workers[0] = "task-1"
    assert anima._has_active_busy_lock()
    anima._active_background_workers.clear()

    async with anima._background_lock:
        assert anima._has_active_busy_lock()


def test_pool_size_one_taskexec_session_is_separate_from_background_lane() -> None:
    anima = DigitalAnima.__new__(DigitalAnima)
    anima._background_worker_pool_size = 1
    anima._lane_agents = {"background": MagicMock()}
    anima._agent_session_locks = {"background": asyncio.Lock()}
    anima._interrupt_events = {}
    anima._background_worker_slots = []
    anima._background_worker_queue = asyncio.Queue()

    anima._initialize_background_worker_pool()

    slot = anima._background_worker_slots[0]
    assert slot.session_lock is not anima._agent_session_locks["background"]
    assert slot.interrupt_event is anima._get_interrupt_event("_taskexec")


@pytest.mark.asyncio
async def test_slotless_taskexec_can_be_interrupted_by_task_id(tmp_path: Path) -> None:
    anima_dir = tmp_path / "anima"
    anima_dir.mkdir()
    interrupt_events: dict[str, asyncio.Event] = {}
    taskexec_event = asyncio.Event()
    agent = MagicMock()
    anima = SimpleNamespace(
        name="interrupt-test",
        agent=agent,
        messenger=MagicMock(),
        _interrupt_events=interrupt_events,
        _taskexec_session_lock=asyncio.Lock(),
        _get_interrupt_event=lambda name: taskexec_event,
    )
    executor = PendingTaskExecutor(
        anima=anima,
        anima_name="interrupt-test",
        anima_dir=anima_dir,
        shutdown_event=asyncio.Event(),
    )
    executor._sync_task_queue = MagicMock()  # type: ignore[method-assign]
    executor._get_task_queue_entry = MagicMock(return_value=None)  # type: ignore[method-assign]
    agent.reset_reply_tracking = MagicMock()
    agent.reset_read_paths = MagicMock()
    agent.set_task_cwd = MagicMock()
    agent.set_interrupt_event = MagicMock()
    started = asyncio.Event()
    continue_stream = asyncio.Event()

    async def stream(*_args, **_kwargs):
        started.set()
        await continue_stream.wait()
        assert taskexec_event.is_set()
        yield {
            "type": "cycle_done",
            "cycle_result": {"action": "responded", "summary": "interrupted task"},
        }

    agent.run_cycle_streaming = stream
    task = asyncio.create_task(
        executor._run_llm_task({"task_id": "task-interrupt", "title": "Interrupt me", "description": "work"})
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("core.paths.load_prompt", lambda *_args, **_kwargs: "test task prompt")
        mp.setattr("core.tasks.pending_executor._resolve_default_workspace", lambda _path: "")
        await asyncio.wait_for(started.wait(), timeout=1)
        assert interrupt_events["task-interrupt"] is taskexec_event
        await DigitalAnima.interrupt(anima, thread_id="task-interrupt")
        assert taskexec_event.is_set()
        continue_stream.set()
        result = await asyncio.wait_for(task, timeout=2)

    assert result == "interrupted task"
    assert "task-interrupt" not in interrupt_events
