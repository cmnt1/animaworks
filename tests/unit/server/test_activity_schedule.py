from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from core.config.io import get_config_path, invalidate_cache, load_config, save_config
from core.config.models import ActivityScheduleEntry, AnimaWorksConfig
from core.platform.process_role import PROCESS_ROLE_ENV
from server.supervisor._mgr_scheduler import SchedulerMixin


@pytest.mark.asyncio
async def test_root_cron_applies_level_once_and_notifies_all_running_animas(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(PROCESS_ROLE_ENV, "root")
    config_path = get_config_path()
    save_config(
        AnimaWorksConfig(
            activity_level=100,
            activity_schedule=[ActivityScheduleEntry(start="22:00", end="08:00", level=40)],
        ),
        config_path,
    )
    invalidate_cache()
    fixed_now = datetime(2026, 10, 1, 23, 0, tzinfo=UTC)
    handles = {
        name: SimpleNamespace(send_request=AsyncMock(return_value=SimpleNamespace(error=None))) for name in ("a", "b")
    }
    supervisor = SimpleNamespace(processes=handles)

    with patch("server.supervisor.activity_schedule.now_local", return_value=fixed_now):
        await SchedulerMixin._apply_activity_schedule_tick(supervisor)
        assert load_config(config_path).activity_level == 40
        for handle in handles.values():
            handle.send_request.assert_awaited_once_with("reschedule_heartbeat", {}, timeout=10.0)

        await SchedulerMixin._apply_activity_schedule_tick(supervisor)

    for handle in handles.values():
        handle.send_request.assert_awaited_once()
    assert load_config(config_path).activity_level == 40
