"""Live fact extraction is scheduled by the long-lived parent after isolated jobs."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core.runtime.task_runner_supervisor import TaskRunnerSupervisor


@pytest.fixture
def scheduled(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, str]]:
    calls: list[tuple[Path, str]] = []

    def _schedule(anima_dir: Path, *, trigger: str, session_started_at: str | None = None) -> bool:
        assert session_started_at
        calls.append((anima_dir, trigger))
        return True

    monkeypatch.setattr("core.memory.facts.live.schedule_live_fact_extraction", _schedule)
    return calls


def _supervisor(tmp_path: Path) -> TaskRunnerSupervisor:
    supervisor = TaskRunnerSupervisor("sakura", tmp_path / "animas" / "sakura", tmp_path / "shared")
    supervisor._run_isolated_job = AsyncMock(return_value={"response": "ok"})
    return supervisor


@pytest.mark.asyncio
async def test_inbox_task_and_chat_schedule_live_facts(tmp_path: Path, scheduled: list[tuple[Path, str]]) -> None:
    supervisor = _supervisor(tmp_path)

    await supervisor.run_inbox()
    await supervisor.run_task({"task_id": "t1"})
    await supervisor.run_chat(kind="greet", payload={})

    assert [trigger for _, trigger in scheduled] == ["inbox", "task", "chat"]
    assert all(anima_dir == supervisor.anima_dir for anima_dir, _ in scheduled)


@pytest.mark.asyncio
async def test_heartbeat_and_background_do_not_schedule(tmp_path: Path, scheduled: list[tuple[Path, str]]) -> None:
    supervisor = _supervisor(tmp_path)

    await supervisor.run_heartbeat()
    await supervisor.run_background(kind="command", payload={})

    assert scheduled == []


@pytest.mark.asyncio
async def test_scheduler_failure_does_not_affect_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr("core.memory.facts.live.schedule_live_fact_extraction", _boom)
    supervisor = _supervisor(tmp_path)

    assert await supervisor.run_inbox() == {"response": "ok"}
