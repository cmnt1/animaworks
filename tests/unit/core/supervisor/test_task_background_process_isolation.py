"""Feature flag and crash semantics for TaskExec / background process isolation."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.memory.conversation.streaming_journal import StreamingJournal
from core.runtime.ipc_v2 import IPCV2ConnectionState, IPCV2Identity
from core.runtime.task_runner_supervisor import (
    TaskRunnerError,
    TaskRunnerJob,
    TaskRunnerSupervisor,
)
from core.tasks.pending_executor import PendingTaskExecutor


def _anima_double(tmp_path: Path, *, pool_size: int = 1) -> MagicMock:
    anima = MagicMock()
    anima.shared_dir = tmp_path / "shared"
    anima.shared_dir.mkdir(parents=True, exist_ok=True)
    anima._background_worker_pool_size = pool_size
    anima._background_lock = asyncio.Lock()
    anima._mark_busy_start = MagicMock()
    anima._clear_busy_status_sidecar_if_idle = MagicMock()
    anima._status_slots = {"background": "idle"}
    anima._task_slots = {"background": ""}
    anima._active_background_workers = {}
    anima._keepalive_while_busy = None
    return anima


def _executor(
    tmp_path: Path,
    *,
    with_supervisor: bool = False,
    pool_size: int = 1,
) -> tuple[PendingTaskExecutor, MagicMock, Path]:
    anima_dir = tmp_path / "animas" / "sakura"
    anima_dir.mkdir(parents=True)
    anima = _anima_double(tmp_path, pool_size=pool_size)
    supervisor = None
    if with_supervisor:
        supervisor = TaskRunnerSupervisor(
            "sakura",
            anima_dir,
            anima.shared_dir,
            max_concurrent=pool_size,
        )
    shutdown = asyncio.Event()
    executor = PendingTaskExecutor(
        anima,
        "sakura",
        anima_dir,
        shutdown,
        task_runner_supervisor=supervisor,
    )
    return executor, anima, anima_dir


async def test_isolated_task_journal_recovery_clears_the_orphan(tmp_path: Path) -> None:
    anima_dir = tmp_path / "animas" / "sakura"
    anima_dir.mkdir(parents=True)
    journal = StreamingJournal(anima_dir, session_type="task", thread_id="task-1")
    journal.open(trigger="task:task-1")
    journal.write_text("partial task output")
    journal.close()
    owner = SimpleNamespace(_pending_executor=MagicMock())
    supervisor = TaskRunnerSupervisor(
        "sakura",
        anima_dir,
        tmp_path / "shared",
        busy_status_owner=owner,
    )

    await supervisor._recover_task_journals(("task",))

    # The journal is collected; no checkpoint is injected into any descriptor.
    assert not StreamingJournal.has_orphan(anima_dir, "task")
    owner._pending_executor.add_recovered_task_checkpoint.assert_not_called()


@pytest.mark.parametrize("lane", ["task", "chat", "heartbeat", "cron"])
async def test_journal_recovery_preserves_active_sibling_lane(tmp_path: Path, lane: str) -> None:
    anima_dir = tmp_path / "animas" / "sakura"
    anima_dir.mkdir(parents=True)
    supervisor = TaskRunnerSupervisor("sakura", anima_dir, tmp_path / "shared")
    journal = StreamingJournal(anima_dir, session_type=lane, thread_id="live")
    journal.open(trigger=f"{lane}:live")
    journal.write_text("still running")
    journal.close()
    journal_path = anima_dir / "shortterm" / lane / "live" / "streaming_journal.jsonl"
    original = journal_path.read_bytes()
    supervisor.jobs["live-job"] = SimpleNamespace(identity=SimpleNamespace(lane=lane))

    await supervisor._recover_task_journals((lane,))

    assert journal_path.read_bytes() == original
    supervisor.jobs.clear()
    await supervisor._recover_task_journals((lane,))
    assert not journal_path.exists()


async def test_journal_recovery_keeps_registration_locked_until_disk_work_finishes(tmp_path: Path) -> None:
    import threading

    supervisor = TaskRunnerSupervisor("sakura", tmp_path / "sakura", tmp_path / "shared")
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()

    def slow_has_orphan(*args, **kwargs):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=5)
        return False

    with patch.object(StreamingJournal, "has_orphan", side_effect=slow_has_orphan):
        recovery = asyncio.create_task(supervisor._recover_task_journals(("task",)))
        await asyncio.wait_for(started.wait(), timeout=5)
        registration = asyncio.create_task(supervisor._journal_recovery_lock.acquire())
        try:
            recovery.cancel()
            await asyncio.sleep(0)
            assert not registration.done()
            assert not recovery.done()
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await recovery
        await asyncio.wait_for(registration, timeout=5)
        supervisor._journal_recovery_lock.release()


@pytest.mark.asyncio
async def test_task_flag_true_uses_child_result_without_root_llm(tmp_path: Path) -> None:
    executor, anima, _anima_dir = _executor(tmp_path, with_supervisor=True)
    assert executor._task_isolated is True
    assert executor._task_runner_supervisor is not None

    executor._task_runner_supervisor.run_task = AsyncMock(
        return_value={"task_type": "llm", "result": "child-done", "success": True}
    )
    # Avoid real worker pool acquire on MagicMock.
    anima._acquire_background_worker = None
    type(anima)._acquire_background_worker = None  # type: ignore[attr-defined]

    task_desc = {
        "task_id": "t-iso",
        "title": "isolated",
        "description": "work",
        "task_type": "llm",
    }
    with (
        patch.object(executor, "_run_llm_task", new=AsyncMock()) as run_llm,
        patch.object(executor, "_sync_task_queue") as sync,
    ):
        await executor._execute_llm_task(task_desc)

    run_llm.assert_not_awaited()
    executor._task_runner_supervisor.run_task.assert_awaited_once()
    sync.assert_called()
    # Result path classified as done.
    assert sync.call_args[0][1] == "done"


@pytest.mark.asyncio
async def test_child_crash_returns_task_to_pending_and_root_continues(tmp_path: Path) -> None:
    executor, anima, anima_dir = _executor(tmp_path, with_supervisor=True)
    assert executor._task_runner_supervisor is not None
    type(anima)._acquire_background_worker = None  # type: ignore[attr-defined]

    executor._task_runner_supervisor.run_task = AsyncMock(
        side_effect=TaskRunnerError("task runner exited before returning a result (exit=-9)")
    )
    task_desc = {
        "task_id": "t-crash",
        "title": "crash",
        "description": "work",
        "task_type": "llm",
    }
    with (
        patch.object(executor, "_save_task_result") as save_result,
        patch.object(executor, "_record_run_ended") as record_end,
        patch.object(executor, "_sync_task_queue") as sync,
    ):
        await executor._execute_llm_task(task_desc)

    save_result.assert_called_once()
    assert record_end.call_args[0] == ("t-crash", "crash")
    sync.assert_called()
    assert sync.call_args[0][1] == "pending"
    note = str(record_end.call_args.kwargs.get("note", ""))
    assert "INTERRUPTED" in note
    # The original TaskRunnerError must survive into the run note (no flattening).
    assert "exit=-9" in note


@pytest.mark.asyncio
async def test_queue_cancelled_child_is_reported_as_cancel_not_crash(tmp_path: Path, caplog) -> None:
    from core.runtime.task_runner_supervisor import TaskRunnerCancelled

    executor, anima, _anima_dir = _executor(tmp_path, with_supervisor=True)
    assert executor._task_runner_supervisor is not None
    type(anima)._acquire_background_worker = None  # type: ignore[attr-defined]

    executor._task_runner_supervisor.run_task = AsyncMock(
        side_effect=TaskRunnerCancelled("task runner stopped because the task was cancelled (exit=-15)")
    )
    task_desc = {"task_id": "t-cancel", "title": "cancel", "description": "work", "task_type": "llm"}
    with (
        patch.object(executor, "_save_task_result"),
        patch.object(executor, "_record_run_ended") as record_end,
        patch.object(executor, "_sync_task_queue"),
        caplog.at_level("INFO", logger="core.tasks.pending_executor"),
    ):
        await executor._execute_llm_task(task_desc)

    assert not any("Isolated TaskExec child failed" in r.getMessage() for r in caplog.records)
    assert any("stopped by queue cancel" in r.getMessage() for r in caplog.records)
    note = str(record_end.call_args.kwargs.get("note", "")) if record_end.call_args else ""
    assert "PARTIALLY EXECUTED" not in note


@pytest.mark.asyncio
async def test_child_crash_during_shutdown_stays_for_startup_recovery(tmp_path: Path) -> None:
    from core.tasks.board.tasks import process_identity
    from core.tasks.dispatch import publish_tasks
    from core.tasks.queue import TaskQueueManager

    executor, anima, anima_dir = _executor(tmp_path, with_supervisor=True)
    assert executor._task_runner_supervisor is not None
    type(anima)._acquire_background_worker = None  # type: ignore[attr-defined]

    async def crash_after_spawn(task_desc, *, attempt, display_lane, on_spawned):
        await on_spawned(
            SimpleNamespace(
                pid=os.getpid() + 1000000,
                pgid=os.getpid() + 1000000,
                process_start_time=123.45,
                identity=SimpleNamespace(job_id="shutdown-job", root_epoch="shutdown-epoch"),
            )
        )
        raise TaskRunnerError("task runner exited during shutdown")

    executor._task_runner_supervisor.run_task = AsyncMock(side_effect=crash_after_spawn)
    task_desc = {
        "task_id": "t-shutdown-crash",
        "title": "shutdown crash",
        "description": "work",
        "task_type": "llm",
    }
    publish_tasks(anima_dir, [task_desc])
    store = TaskQueueManager(anima_dir).store
    claim = store.claim("sakura", task_desc["task_id"], process_identity())
    assert claim is not None
    executor._shutdown_event.set()
    with patch("core.tasks.board.tasks.identity_liveness", return_value="unknown"):
        await executor._execute_canonical_task(claim)
        executor._recover_task_attempts(store)
    # An owner with uncertain liveness retains its exact attempt fence.
    assert store.active_attempts("sakura")[0]["token"] == claim["_attempt_token"]
    assert store.get("sakura", task_desc["task_id"]).status == "in_progress"
    assert store.claim("sakura", task_desc["task_id"], process_identity()) is None
    assert store.wakeups("sakura") == []
    anima.messenger.send.assert_not_called()
    with patch("core.tasks.board.tasks.identity_liveness", return_value="dead"):
        executor._recover_task_attempts(store)
    # Proven death ends ownership, preserves input, and requests attention;
    # it does not automatically replay possibly completed side effects.
    assert store.active_attempts("sakura") == []
    assert store.get("sakura", task_desc["task_id"]).status == "pending"
    assert store.get_input("sakura", task_desc["task_id"]) == task_desc
    assert store.claim("sakura", task_desc["task_id"], process_identity()) is None
    assert len(store.wakeups("sakura")) == 1
    executor._task_runner_supervisor.run_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_background_flag_true_spawns_child(tmp_path: Path) -> None:
    from core.tasks.background import BackgroundTaskManager, TaskStatus

    executor, anima, anima_dir = _executor(tmp_path, with_supervisor=True)
    manager = BackgroundTaskManager(anima_dir)
    manager.on_complete = AsyncMock()
    anima.agent.background_manager = manager
    assert executor._background_isolated is True
    assert executor._task_runner_supervisor is not None
    executor._task_runner_supervisor.run_background = AsyncMock(
        return_value={"task_type": "command", "result": "ok", "success": True}
    )
    await executor.execute_pending_task(
        {
            "task_id": "cmd-iso",
            "task_type": "command",
            "tool_name": "echo",
            "subcommand": "hi",
            "raw_args": [],
        }
    )
    executor._task_runner_supervisor.run_background.assert_awaited_once()
    kwargs = executor._task_runner_supervisor.run_background.await_args
    assert (
        kwargs.kwargs["kind"] == "command"
        or kwargs[1].get("kind") == "command"
        or (kwargs.args and kwargs.args[0] == "command")
        or kwargs.kwargs.get("kind") == "command"
    )
    # Prefer kwargs form
    assert executor._task_runner_supervisor.run_background.await_args.kwargs["kind"] == "command"
    task = manager.get_task("cmd-iso")
    assert task is not None
    assert task.status == TaskStatus.COMPLETED
    assert task.result == "ok"
    assert json.loads((anima_dir / "state/background_tasks/cmd-iso.json").read_text())["result"] == "ok"
    manager.on_complete.assert_awaited_once_with(task)


@pytest.mark.asyncio
async def test_isolated_command_failure_is_saved_and_notified(tmp_path: Path) -> None:
    from core.tasks.background import BackgroundTaskManager, TaskStatus

    executor, anima, anima_dir = _executor(tmp_path, with_supervisor=True)
    manager = BackgroundTaskManager(anima_dir)
    manager.on_complete = AsyncMock()
    anima.agent.background_manager = manager
    executor._task_runner_supervisor.run_background = AsyncMock(
        side_effect=TaskRunnerError("image service unavailable")
    )
    await executor.execute_pending_task({"task_id": "failed-image", "tool_name": "image_gen"})
    task = manager.get_task("failed-image")
    assert task is not None
    assert task.status == TaskStatus.FAILED
    assert "image service unavailable" in task.error
    manager.on_complete.assert_awaited_once_with(task)


@pytest.mark.asyncio
async def test_background_pool_limit_caps_concurrent_children(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    shared.mkdir()
    anima_dir = tmp_path / "animas" / "sakura"
    anima_dir.mkdir(parents=True)
    supervisor = TaskRunnerSupervisor("sakura", anima_dir, shared, max_concurrent=1)

    started = asyncio.Event()
    release = asyncio.Event()
    in_flight = 0
    max_seen = 0

    async def _slow_spawn_and_await(**kwargs):
        nonlocal in_flight, max_seen
        in_flight += 1
        max_seen = max(max_seen, in_flight)
        started.set()
        await release.wait()
        in_flight -= 1
        return {"ok": True}

    with (
        patch.object(supervisor, "_spawn_and_await", new=AsyncMock(side_effect=_slow_spawn_and_await)),
        patch.object(
            TaskRunnerSupervisor,
            "_required_url_environment",
            return_value={
                "ANIMAWORKS_EMBED_URL": "http://embed.test",
                "ANIMAWORKS_VECTOR_URL": "http://vector.test",
                "ANIMAWORKS_RERANK_URL": "http://rerank.test",
            },
        ),
    ):
        first = asyncio.create_task(supervisor.run_background(kind="command", payload={"tool_name": "a"}))
        await started.wait()
        second = asyncio.create_task(supervisor.run_background(kind="command", payload={"tool_name": "b"}))
        await asyncio.sleep(0.05)
        assert max_seen == 1
        assert not second.done()
        release.set()
        await asyncio.gather(first, second)
        assert max_seen == 1


@pytest.mark.asyncio
@pytest.mark.skipif(__import__("os").name == "nt", reason="Requires POSIX process groups")
async def test_sigkill_only_reaps_task_group_and_root_survives(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    anima_dir = tmp_path / "animas" / "sakura"
    shared.mkdir(parents=True)
    anima_dir.mkdir(parents=True)
    supervisor = TaskRunnerSupervisor("sakura", anima_dir, shared)
    identity = IPCV2Identity(
        job_id="job-kill-task",
        root_epoch=supervisor.root_epoch,
        attempt=1,
        lane="task",
        display_lane="background",
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        "import time; time.sleep(60)",
        start_new_session=True,
    )
    job = TaskRunnerJob(
        identity=identity,
        request_id="run-kill-task",
        params={},
        result=asyncio.get_running_loop().create_future(),
        peer_state=IPCV2ConnectionState(identity),
        process=process,
        pid=process.pid,
        pgid=process.pid,
    )
    supervisor.jobs[identity.job_id] = job
    root_pid = os.getpid()

    os.killpg(process.pid, 9)
    return_code = await asyncio.wait_for(process.wait(), timeout=2)
    supervisor.jobs.pop(identity.job_id)

    assert return_code == -9
    assert os.getpid() == root_pid
    assert supervisor._accepting is True
    assert not supervisor.jobs


@pytest.mark.asyncio
async def test_grace_sends_event_and_waits_for_ack(tmp_path: Path) -> None:
    shared = tmp_path / "shared"
    anima_dir = tmp_path / "animas" / "sakura"
    shared.mkdir(parents=True)
    anima_dir.mkdir(parents=True)
    supervisor = TaskRunnerSupervisor("sakura", anima_dir, shared)
    identity = IPCV2Identity(
        job_id="job-grace",
        root_epoch=supervisor.root_epoch,
        attempt=1,
        lane="task",
        display_lane="background",
    )
    connection = AsyncMock()
    connection.send_event = AsyncMock()
    job = TaskRunnerJob(
        identity=identity,
        request_id="run-grace",
        params={},
        result=asyncio.get_running_loop().create_future(),
        peer_state=IPCV2ConnectionState(identity),
        connection=connection,
        process=None,
    )
    # Pre-set grace_acked so close() does not wait forever.
    job.grace_acked.set()
    supervisor.jobs[identity.job_id] = job

    await supervisor.close()

    connection.send_event.assert_awaited()
    assert connection.send_event.await_args.args[0] == "grace"
    assert supervisor._accepting is False
