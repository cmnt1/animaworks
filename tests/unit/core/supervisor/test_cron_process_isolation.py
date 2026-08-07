"""Feature flag and crash semantics for cron process isolation."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.schemas import CronTask, CycleResult
from core.supervisor.ipc_v2 import IPCV2ConnectionState, IPCV2Identity
from core.supervisor.scheduler_manager import SchedulerManager
from core.supervisor.task_runner_supervisor import TaskRunnerJob, TaskRunnerSupervisor


def _manager(tmp_path: Path, *, isolated: bool) -> tuple[SchedulerManager, MagicMock]:
    anima_dir = tmp_path / "animas" / "sakura"
    anima_dir.mkdir(parents=True)
    (tmp_path / "shared").mkdir()
    (anima_dir / "status.json").write_text(
        json.dumps(
            {
                "process_model": "phase2",
                "task_process_isolation": {"cron": isolated},
            }
        ),
        encoding="utf-8",
    )
    anima = MagicMock()
    anima.shared_dir = tmp_path / "shared"
    anima.run_cron_task = AsyncMock(
        return_value=CycleResult(trigger="cron:daily", action="completed", summary="done")
    )
    anima.run_cron_command = AsyncMock()
    emit = MagicMock()
    manager = SchedulerManager(anima, "sakura", anima_dir, emit)
    manager._record_cron_result = MagicMock()
    return manager, anima


@pytest.mark.asyncio
async def test_flag_false_preserves_legacy_path_without_spawn(tmp_path: Path) -> None:
    manager, anima = _manager(tmp_path, isolated=False)
    task = CronTask(name="daily", schedule="0 9 * * *", description="daily work")

    await manager._run_cron_task(task)

    assert manager._task_runner_supervisor is None
    anima.run_cron_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_flag_true_uses_child_result_without_root_llm(tmp_path: Path) -> None:
    manager, anima = _manager(tmp_path, isolated=True)
    task = CronTask(name="daily", schedule="0 9 * * *", description="daily work")
    assert manager._task_runner_supervisor is not None
    manager._task_runner_supervisor.run_cron = AsyncMock(
        return_value={
            "task_type": "llm",
            "result": {"action": "completed", "summary": "child result"},
            "success": True,
            "usage": {"input_tokens": 10},
        }
    )

    await manager._run_cron_task(task)

    anima.run_cron_task.assert_not_awaited()
    manager._task_runner_supervisor.run_cron.assert_awaited_once_with(task)
    manager._emit_event.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.skipif(os.name == "nt", reason="process groups / os.killpg are POSIX-only")
async def test_sigkill_only_reaps_task_group_and_root_can_continue(tmp_path: Path) -> None:
    shared_dir = tmp_path / "shared"
    anima_dir = tmp_path / "animas" / "sakura"
    shared_dir.mkdir(parents=True)
    anima_dir.mkdir(parents=True)
    supervisor = TaskRunnerSupervisor("sakura", anima_dir, shared_dir)
    identity = IPCV2Identity(
        job_id="job-kill",
        root_epoch=supervisor.root_epoch,
        attempt=1,
        lane="cron",
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
        request_id="run-kill",
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

