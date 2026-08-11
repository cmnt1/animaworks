from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.memory.task_queue import TaskQueueManager
from core.supervisor.pending_executor import PendingTaskExecutor, _is_waiting_session


def _make_executor(tmp_path: Path) -> PendingTaskExecutor:
    anima_dir = tmp_path / "animas" / "test-anima"
    (anima_dir / "state").mkdir(parents=True)
    anima = MagicMock()
    anima._background_lock = asyncio.Lock()
    anima._status_slots = {"background": "idle"}
    anima._task_slots = {"background": ""}
    anima._active_parallel_tasks = {}
    anima._active_background_workers = {}
    anima._keepalive_while_busy = None
    anima.agent.reset_reply_tracking = MagicMock()
    anima.agent.reset_read_paths = MagicMock()
    anima.agent.set_task_cwd = MagicMock()
    anima.agent.set_interrupt_event = MagicMock()
    return PendingTaskExecutor(
        anima=anima,
        anima_name="test-anima",
        anima_dir=anima_dir,
        shutdown_event=asyncio.Event(),
    )


def _task(task_id: str, **overrides: object) -> dict[str, object]:
    task: dict[str, object] = {
        "task_type": "llm",
        "task_id": task_id,
        "title": "Declaration probe test",
        "description": "finish the task",
        "context": "original context",
        "reply_to": None,
        "submitted_at": "",
    }
    task.update(overrides)
    return task


def _queue_task(executor: PendingTaskExecutor, task_id: str) -> TaskQueueManager:
    manager = TaskQueueManager(executor._anima_dir)
    manager.add_task(
        source="anima",
        original_instruction="finish the task",
        assignee="test-anima",
        summary="declaration probe test",
        task_id=task_id,
        status="in_progress",
    )
    return manager


async def _stream(
    records: list[dict[str, str]],
    before_done: Callable[[], None] | None = None,
) -> AsyncIterator[dict[str, object]]:
    if before_done:
        before_done()
    yield {
        "type": "cycle_done",
        "cycle_result": {
            "summary": "finished",
            "action": "complete",
            "tool_call_records": records,
        },
    }


async def _failing_stream() -> AsyncIterator[dict[str, object]]:
    raise RuntimeError("probe failed")
    yield {}


async def _execute(executor: PendingTaskExecutor, task: dict[str, object]) -> MagicMock:
    with (
        patch("core.paths.load_prompt", return_value="prompt"),
        patch("core.memory.activity.ActivityLogger") as activity,
        patch("core.supervisor.pending_executor._completion_declaration_required", return_value=True),
    ):
        await executor._execute_llm_task(task)
    return activity


@pytest.mark.parametrize(
    ("records", "expected"),
    [
        ([{"tool_name": "mcp__aw__Monitor"}], True),
        ([{"tool": "ScheduleWakeup"}], True),
        ([{"tool_name": "Bash"}], False),
        ([], False),
    ],
)
def test_is_waiting_session(records: list[dict[str, str]], expected: bool) -> None:
    assert _is_waiting_session(records) is expected


@pytest.mark.asyncio
async def test_monitor_waiting_reenqueue_does_not_consume_continuation(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    manager = _queue_task(executor, "monitor-wait")
    executor._anima.agent.run_cycle_streaming = MagicMock(
        side_effect=lambda *_args, **_kwargs: _stream([{"tool_name": "mcp__aw__Monitor"}])
    )

    activity = await _execute(executor, _task("monitor-wait"))

    pending = json.loads(
        (executor._anima_dir / "state" / "pending" / "monitor-wait.json").read_text(encoding="utf-8")
    )
    assert pending["waiting_reenqueue_count"] == 1
    assert pending["continuation_count"] == 0
    assert pending["continuation_not_before"] == pytest.approx(time.time() + 300.0, abs=5.0)
    assert manager.get_task_by_id("monitor-wait").status == "in_progress"
    assert activity.return_value.log.call_args_list[-1].kwargs["meta"]["status"] == "waiting"
    executor._anima.agent.run_cycle_streaming.assert_called_once()


@pytest.mark.asyncio
async def test_waiting_limit_falls_back_to_normal_continuation(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    _queue_task(executor, "wait-limit")
    executor._anima.agent.run_cycle_streaming = MagicMock(
        side_effect=lambda *_args, **_kwargs: _stream([{"tool": "ScheduleWakeup"}])
    )

    await _execute(executor, _task("wait-limit", waiting_reenqueue_count=12))

    pending = json.loads(
        (executor._anima_dir / "state" / "pending" / "wait-limit.json").read_text(encoding="utf-8")
    )
    assert pending["waiting_reenqueue_count"] == 12
    assert pending["continuation_count"] == 1
    executor._anima.agent.run_cycle_streaming.assert_called_once()


@pytest.mark.asyncio
async def test_probe_done_declaration_completes_without_reenqueue(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    manager = _queue_task(executor, "probe-done")
    calls = 0

    def run_stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _stream([{"tool_name": "Bash"}])

        def declare_done() -> None:
            manager.update_status("probe-done", "done", summary="verified result")
            manager.update_meta(
                "probe-done",
                {"completed_by": "agent_declaration", "result_note": "verified result"},
            )

        return _stream([{"tool_name": "mcp__aw__update_task"}], declare_done)

    executor._anima.agent.run_cycle_streaming = MagicMock(side_effect=run_stream)

    await _execute(executor, _task("probe-done"))

    entry = manager.get_task_by_id("probe-done")
    assert entry is not None
    assert entry.status == "done"
    assert entry.summary == "verified result"
    assert calls == 2
    assert not (executor._anima_dir / "state" / "pending" / "probe-done.json").exists()


@pytest.mark.asyncio
async def test_probe_in_progress_declaration_reenqueues_as_waiting(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    manager = _queue_task(executor, "probe-wait")
    calls = 0

    def run_stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _stream([{"tool_name": "Bash"}])
        return _stream(
            [{"tool_name": "mcp__aw__update_task"}],
            lambda: manager.update_status("probe-wait", "in_progress", summary="[waiting] CI"),
        )

    executor._anima.agent.run_cycle_streaming = MagicMock(side_effect=run_stream)

    await _execute(executor, _task("probe-wait"))

    pending = json.loads(
        (executor._anima_dir / "state" / "pending" / "probe-wait.json").read_text(encoding="utf-8")
    )
    assert pending["waiting_reenqueue_count"] == 1
    assert pending["continuation_count"] == 0
    assert calls == 2


@pytest.mark.asyncio
async def test_probe_without_declaration_consumes_continuation(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    _queue_task(executor, "probe-empty")
    executor._anima.agent.run_cycle_streaming = MagicMock(
        side_effect=lambda *_args, **_kwargs: _stream([{"tool_name": "Bash"}])
    )

    await _execute(executor, _task("probe-empty"))

    pending = json.loads(
        (executor._anima_dir / "state" / "pending" / "probe-empty.json").read_text(encoding="utf-8")
    )
    assert pending["continuation_count"] == 1
    assert "waiting_reenqueue_count" not in pending
    assert executor._anima.agent.run_cycle_streaming.call_count == 2


@pytest.mark.asyncio
async def test_probe_exception_falls_back_to_continuation(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    manager = _queue_task(executor, "probe-error")
    calls = 0

    def run_stream(*_args: object, **_kwargs: object) -> AsyncIterator[dict[str, object]]:
        nonlocal calls
        calls += 1
        return _stream([{"tool_name": "Bash"}]) if calls == 1 else _failing_stream()

    executor._anima.agent.run_cycle_streaming = MagicMock(side_effect=run_stream)

    await _execute(executor, _task("probe-error"))

    pending = json.loads(
        (executor._anima_dir / "state" / "pending" / "probe-error.json").read_text(encoding="utf-8")
    )
    assert pending["continuation_count"] == 1
    assert manager.get_task_by_id("probe-error").status == "in_progress"
    assert calls == 2
