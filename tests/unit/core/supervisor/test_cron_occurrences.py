from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.runtime.scheduler_manager import SchedulerManager
from core.schemas import CronTask


def _make_manager(tmp_path: Path) -> SchedulerManager:
    anima = MagicMock()
    anima.shared_dir = tmp_path / "shared"
    anima._background_worker_pool_size = 1
    anima._chat_max_concurrency = 1
    config = SimpleNamespace(server=SimpleNamespace(runner_liveness_timeout=900))
    with patch("core.runtime.scheduler_manager.load_config", return_value=config):
        return SchedulerManager(anima, "aoi", tmp_path / "animas" / "aoi", MagicMock())


def _write_running_occurrence(
    manager: SchedulerManager, task_name: str, started_at: datetime, *, rerun: bool = False
) -> None:
    manager._write_cron_occurrences(
        {
            task_name: {
                "task_name": task_name,
                "scheduled_at": started_at.isoformat(),
                "started_at": started_at.isoformat(),
                "status": "running",
                "rerun": rerun,
            },
        },
    )


def _read_occurrence(manager: SchedulerManager, task_name: str) -> dict[str, object]:
    payload = json.loads(manager._cron_occurrences_path.read_text(encoding="utf-8"))
    return payload["occurrences"][task_name]


def _job(task: CronTask, next_run: datetime) -> SimpleNamespace:
    return SimpleNamespace(args=(task,), next_run_time=next_run)


@pytest.mark.asyncio
async def test_cron_run_writes_running_occurrence_before_dispatch(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager._awaiting_initial_setup = lambda: False
    manager._check_schedule_freshness = lambda: False
    task = CronTask(name="weekly-report", schedule="0 9 * * 1")
    scheduled: list[str] = []

    def fake_spawn(coro: object, *, name: str) -> None:
        scheduled.append(name)
        coro.close()  # type: ignore[attr-defined]

    with patch("core.runtime.scheduler_manager.spawn", side_effect=fake_spawn):
        await manager.cron_tick(task)

    occurrence = _read_occurrence(manager, task.name)
    assert scheduled == ["cron-aoi-weekly-report"]
    assert occurrence["task_name"] == task.name
    assert occurrence["status"] == "running"
    assert occurrence["rerun"] is False
    assert isinstance(occurrence["scheduled_at"], str)
    assert isinstance(occurrence["started_at"], str)


def test_interrupted_cron_is_rerun_once_and_marked_before_spawn(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    task = CronTask(name="weekly-report", schedule="0 9 * * 1")
    now = datetime(2026, 10, 19, 12, tzinfo=UTC)
    _write_running_occurrence(manager, task.name, now - timedelta(hours=1))
    manager.scheduler = SimpleNamespace(get_jobs=lambda: [_job(task, now + timedelta(hours=1))])
    scheduled: list[str] = []

    def fake_spawn(coro: object, *, name: str) -> None:
        scheduled.append(name)
        coro.close()  # type: ignore[attr-defined]

    with (
        patch("core.runtime.scheduler_manager.now_local", return_value=now),
        patch("core.runtime.scheduler_manager.spawn", side_effect=fake_spawn),
    ):
        manager._recover_interrupted_crons()
        marked = _read_occurrence(manager, task.name)
        manager._recover_interrupted_crons()

    assert scheduled == ["cron-rerun-aoi-weekly-report"]
    assert marked["status"] == "running"
    assert marked["rerun"] is True
    assert _read_occurrence(manager, task.name)["status"] == "abandoned"


@pytest.mark.asyncio
async def test_scheduler_setup_recovers_interrupted_cron(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    task = CronTask(name="annual-report", schedule="0 0 1 1 *", description="Prepare the report")
    now = datetime(2026, 10, 19, 12, tzinfo=UTC)
    _write_running_occurrence(manager, task.name, now - timedelta(hours=1))
    manager._anima.memory.read_heartbeat_config.return_value = ""
    manager._anima.memory.read_cron_config.return_value = """## annual-report
schedule: 0 0 1 1 *
type: llm
Prepare the report
"""
    manager._anima.set_on_schedule_changed = MagicMock()
    config = SimpleNamespace(
        activity_level=100,
        activity_schedule=[],
        server=SimpleNamespace(runner_liveness_timeout=900),
    )
    scheduled: list[str] = []

    def fake_spawn(coro: object, *, name: str) -> None:
        scheduled.append(name)
        coro.close()  # type: ignore[attr-defined]

    with (
        patch("core.runtime.scheduler_manager.load_config", return_value=config),
        patch("core.runtime.scheduler_manager.now_local", return_value=now),
        patch("core.runtime.scheduler_manager.spawn", side_effect=fake_spawn),
    ):
        manager.setup()

    try:
        assert manager.scheduler is not None and manager.scheduler.running
        assert scheduled == ["cron-rerun-aoi-annual-report"]
        assert _read_occurrence(manager, task.name)["rerun"] is True
    finally:
        manager.shutdown()
        await asyncio.sleep(0.1)


@pytest.mark.parametrize(
    ("age", "next_run_minutes", "rerun"),
    [
        (timedelta(hours=6, seconds=1), 60, False),
        (timedelta(hours=1), 30, False),
        (timedelta(hours=1), 60, True),
    ],
)
def test_ineligible_cron_occurrence_is_abandoned(
    tmp_path: Path, age: timedelta, next_run_minutes: int, rerun: bool
) -> None:
    manager = _make_manager(tmp_path)
    task = CronTask(name="weekly-report", schedule="0 9 * * 1")
    now = datetime(2026, 10, 19, 12, tzinfo=UTC)
    _write_running_occurrence(manager, task.name, now - age, rerun=rerun)
    manager.scheduler = SimpleNamespace(
        get_jobs=lambda: [_job(task, now + timedelta(minutes=next_run_minutes))],
    )
    with patch("core.runtime.scheduler_manager.now_local", return_value=now):
        manager._recover_interrupted_crons()

    assert _read_occurrence(manager, task.name)["status"] == "abandoned"


@pytest.mark.asyncio
async def test_rerun_records_activity_and_finishes_even_on_failure(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    task = CronTask(name="weekly-report", schedule="0 9 * * 1")
    now = datetime(2026, 10, 19, 12, tzinfo=UTC)
    _write_running_occurrence(manager, task.name, now - timedelta(hours=1))
    manager._record_cron_occurrence(task, rerun=True)
    manager._task_runner_supervisor = SimpleNamespace(run_cron=AsyncMock(side_effect=RuntimeError("failed")))
    manager._anima._activity.alog = AsyncMock()

    with patch("core.runtime.scheduler_manager.now_local", return_value=now):
        await manager._run_cron_task(task, rerun=True)

    manager._anima._activity.alog.assert_awaited_once()
    assert _read_occurrence(manager, task.name)["status"] == "finished"


@pytest.mark.asyncio
async def test_cancelled_cron_remains_running_for_startup_recovery(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    task = CronTask(name="weekly-report", schedule="0 9 * * 1")
    manager._record_cron_occurrence(task)

    async def wait_forever(_task: CronTask) -> dict[str, object]:
        await asyncio.Event().wait()
        return {"success": True, "result": {}}

    manager._task_runner_supervisor = SimpleNamespace(run_cron=wait_forever)
    running = asyncio.create_task(manager._run_cron_task(task))
    await asyncio.sleep(0)
    running.cancel()

    with pytest.raises(asyncio.CancelledError):
        await running

    assert _read_occurrence(manager, task.name)["status"] == "running"
