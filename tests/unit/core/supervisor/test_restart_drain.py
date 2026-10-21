from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.runtime.inbox_rate_limiter import InboxRateLimiter
from core.runtime.runner import AnimaRunner
from core.runtime.scheduler_manager import SchedulerManager
from core.schemas import CronTask
from core.tasks.pending_executor import PendingTaskExecutor
from server.supervisor.manager import HealthConfig, ProcessSupervisor, RestartPolicy
from server.supervisor.process_handle import ProcessState


class _FakeProcess:
    def poll(self) -> None:
        return None


class _FakeHandle:
    def __init__(self, events: list[str], busy_results: list[dict[str, bool]] | None = None) -> None:
        self.anima_name = "aoi"
        self.process = _FakeProcess()
        self.state = ProcessState.RUNNING
        self.is_streaming = False
        self.events = events
        self.busy_results = busy_results or []

    async def send_request(self, method: str, params: dict, timeout: float = 60.0) -> SimpleNamespace:
        self.events.append(method)
        return SimpleNamespace(error=None)

    async def ping(self, *, return_details: bool = False) -> dict[str, bool]:
        self.events.append("ping")
        return self.busy_results.pop(0) if self.busy_results else {"success": True, "is_busy": False}

    async def stop(self, **kwargs: object) -> None:
        self.events.append("stop")


def _make_supervisor(tmp_path: Path, timeout: float = 600.0) -> ProcessSupervisor:
    config = SimpleNamespace(
        server=SimpleNamespace(
            restart_drain_timeout_seconds=timeout,
            anima_startup_ready_timeout=120,
            anima_stop_timeout=60,
            spawn_timeout=300,
        ),
    )
    with patch("core.config.load_config", return_value=config):
        return ProcessSupervisor(
            animas_dir=tmp_path / "animas",
            shared_dir=tmp_path / "shared",
            run_dir=tmp_path / "run",
            restart_policy=RestartPolicy(),
            health_config=HealthConfig(),
        )


@pytest.mark.asyncio
async def test_shutdown_quiesces_all_animas_then_drains_before_stopping(tmp_path: Path) -> None:
    supervisor = _make_supervisor(tmp_path)
    events: list[str] = []
    handle = _FakeHandle(events, [{"success": True, "is_busy": True}, {"success": True, "is_busy": False}])
    supervisor.processes["aoi"] = handle  # type: ignore[assignment]

    with patch("server.supervisor.manager.asyncio.sleep", new_callable=AsyncMock):
        await supervisor.shutdown_all()

    assert events.index("quiesce") < events.index("ping") < events.index("stop")


@pytest.mark.asyncio
async def test_shutdown_timeout_zero_quiesces_without_waiting(tmp_path: Path) -> None:
    supervisor = _make_supervisor(tmp_path, timeout=0)
    events: list[str] = []
    supervisor.processes["aoi"] = _FakeHandle(events)  # type: ignore[assignment]

    await supervisor.shutdown_all()

    assert events == ["quiesce", "stop"]


@pytest.mark.asyncio
async def test_shutdown_timeout_proceeds_to_stop_when_work_remains(tmp_path: Path) -> None:
    supervisor = _make_supervisor(tmp_path, timeout=0.05)
    events: list[str] = []
    handle = _FakeHandle(events, [{"success": True, "is_busy": True}])
    supervisor.processes["aoi"] = handle  # type: ignore[assignment]

    original_sleep = asyncio.sleep

    async def finish_timeout(seconds: float) -> None:
        await original_sleep(seconds)

    with patch("server.supervisor.manager.asyncio.sleep", side_effect=finish_timeout):
        await supervisor.shutdown_all()

    assert events[0] == "quiesce"
    assert "ping" in events
    assert events[-1] == "stop"


@pytest.mark.asyncio
async def test_shutdown_keeps_waiting_when_busy_status_is_unavailable(tmp_path: Path, caplog) -> None:
    supervisor = _make_supervisor(tmp_path)
    events: list[str] = []
    handle = _FakeHandle(events, [{"success": False, "is_busy": False}])
    supervisor.processes["aoi"] = handle  # type: ignore[assignment]
    original_sleep = asyncio.sleep

    async def finish_timeout(seconds: float) -> None:
        await original_sleep(seconds)

    with patch("server.supervisor.manager.asyncio.sleep", side_effect=finish_timeout) as sleep:
        await supervisor._wait_for_processes_to_drain(0.05)

    assert events and set(events) == {"ping"}
    sleep.assert_awaited()
    assert "Shutdown work drain timed out" in caplog.text
    assert "status unavailable" in caplog.text


@pytest.mark.asyncio
async def test_anima_restart_quiesces_before_process_handle_drain(tmp_path: Path) -> None:
    supervisor = _make_supervisor(tmp_path, timeout=0)
    events: list[str] = []
    supervisor.processes["aoi"] = _FakeHandle(events)  # type: ignore[assignment]
    supervisor.start_anima = AsyncMock()

    await supervisor.restart_anima("aoi")

    assert events[0] == "quiesce"
    assert events[-1] == "stop"
    supervisor.start_anima.assert_awaited_once_with("aoi")


@pytest.mark.asyncio
async def test_quiesce_blocks_cron_inbox_start_and_pending_claim(tmp_path: Path) -> None:
    anima = MagicMock()
    anima.name = "aoi"
    anima.shared_dir = tmp_path / "shared"
    anima._background_worker_pool_size = 1
    anima._chat_max_concurrency = 1
    config = SimpleNamespace(server=SimpleNamespace(runner_liveness_timeout=900))

    with patch("core.runtime.scheduler_manager.load_config", return_value=config):
        scheduler = SchedulerManager(anima, "aoi", tmp_path / "animas" / "aoi", MagicMock())
    scheduler._task_runner_supervisor.run_cron = AsyncMock()
    scheduler._task_runner_supervisor.run_heartbeat = AsyncMock()
    scheduler._task_runner_supervisor.run_inbox = AsyncMock()
    inbox = InboxRateLimiter(anima, "aoi", asyncio.Event(), scheduler)
    pending = PendingTaskExecutor(
        anima,
        "aoi",
        tmp_path / "animas" / "aoi",
        asyncio.Event(),
        task_runner_supervisor=scheduler._task_runner_supervisor,
    )
    runner = AnimaRunner(
        anima_name="aoi",
        socket_path=tmp_path / "aoi.sock",
        animas_dir=tmp_path / "animas",
        shared_dir=tmp_path / "shared",
    )
    runner._scheduler_mgr = scheduler
    runner._inbox_limiter = inbox
    runner._pending_executor = pending
    assert runner._get_handler("quiesce") is not None

    result = await runner._handle_quiesce({})
    await scheduler.cron_tick(CronTask(name="report", schedule="0 9 * * *"))
    await scheduler.heartbeat_tick()
    await inbox.message_triggered_inbox()
    claims = pending._claim_canonical_pending_tasks()

    assert result == {"status": "quiescing"}
    assert claims == []
    scheduler._task_runner_supervisor.run_cron.assert_not_awaited()
    scheduler._task_runner_supervisor.run_heartbeat.assert_not_awaited()
    scheduler._task_runner_supervisor.run_inbox.assert_not_awaited()
