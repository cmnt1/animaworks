from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.lifecycle.scheduler import SchedulerMixin
from core.schemas import CronTask


class _FakeAnima:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def run_cron_task(self, *args: object, **kwargs: object) -> object:
        self.calls.append((args, kwargs))
        return SimpleNamespace(model_dump=lambda: {"summary": "done"})


@pytest.mark.asyncio
async def test_lifecycle_scheduler_passes_cron_task_skills() -> None:
    anima = _FakeAnima()
    scheduler = SimpleNamespace(_ws_broadcast=AsyncMock())
    task = CronTask(
        name="review",
        schedule="0 9 * * *",
        type="llm",
        description="Review PRs",
        skills=["github-pr-review"],
    )

    await SchedulerMixin._run_cron_and_broadcast(scheduler, anima, "alice", task)

    assert anima.calls == [(("review", "Review PRs"), {"skills": ["github-pr-review"]})]
    scheduler._ws_broadcast.assert_awaited_once()
