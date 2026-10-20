from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""F22: housekeeping scheduler guard + config field.

- ``archive_superseded_retention_days`` is now configurable (was hardcoded 7).
- The cron run and the startup catch-up cannot run housekeeping concurrently.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.config.models import ActivityLogConfig
from core.config.schemas import HousekeepingConfig
from server.supervisor._mgr_scheduler import SchedulerMixin


def test_archive_superseded_retention_days_default() -> None:
    assert HousekeepingConfig().archive_superseded_retention_days == 7


def test_archive_superseded_retention_days_configurable() -> None:
    cfg = HousekeepingConfig.model_validate({"archive_superseded_retention_days": 14})
    assert cfg.archive_superseded_retention_days == 14


class _GuardHarness(SchedulerMixin):
    """Minimal SchedulerMixin subclass exercising only the housekeeping guard."""

    def __init__(self) -> None:
        self.impl_calls = 0
        self.impl_options: dict[str, object] = {}

    async def _run_housekeeping_impl(
        self,
        *,
        only: set[str] | None = None,
        mark_complete: bool = True,
    ) -> None:  # type: ignore[override]
        self.impl_calls += 1
        self.impl_options = {"only": only, "mark_complete": mark_complete}
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_concurrent_housekeeping_runs_are_mutually_exclusive() -> None:
    harness = _GuardHarness()
    # Cron run and catch-up firing together: the second must skip, not double-run.
    await asyncio.gather(harness._run_housekeeping(), harness._run_housekeeping())
    assert harness.impl_calls == 1


@pytest.mark.asyncio
async def test_housekeeping_lock_is_reused() -> None:
    harness = _GuardHarness()
    lock_a = harness._get_housekeeping_lock()
    lock_b = harness._get_housekeeping_lock()
    assert lock_a is lock_b


@pytest.mark.asyncio
async def test_sequential_housekeeping_runs_each_execute() -> None:
    harness = _GuardHarness()
    await harness._run_housekeeping()
    await harness._run_housekeeping()
    assert harness.impl_calls == 2


@pytest.mark.asyncio
async def test_workspace_sweep_uses_shared_housekeeping_lock_and_rules() -> None:
    harness = _GuardHarness()
    await asyncio.gather(harness._run_workspace_sweep(), harness._run_workspace_sweep())

    assert harness.impl_calls == 1
    assert harness.impl_options == {
        "only": {"codex_sessions", "anima_scratch", "shared_worktrees"},
        "mark_complete": False,
    }


@pytest.mark.parametrize("enabled", [True, False])
def test_workspace_sweep_job_registration(enabled: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    config = SimpleNamespace(
        consolidation=SimpleNamespace(
            daily_enabled=False,
            daily_time="05:00",
            weekly_enabled=False,
            weekly_time="sun:05:00",
            indexing_enabled=False,
            indexing_time="05:00",
        ),
        activity_log=ActivityLogConfig(rotation_enabled=False),
        housekeeping=HousekeepingConfig(enabled=False, workspace_sweep_enabled=enabled),
    )
    monkeypatch.setattr("core.config.load_config", lambda: config)

    harness = SchedulerMixin()
    harness.scheduler = MagicMock()
    harness._setup_system_crons()

    job_ids = {call.kwargs["id"] for call in harness.scheduler.add_job.call_args_list}
    assert ("system_workspace_sweep" in job_ids) is enabled
    assert "system_housekeeping" not in job_ids
