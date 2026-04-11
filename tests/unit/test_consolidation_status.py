"""Unit tests for core.lifecycle.system_status (consolidation job tracking)."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

# ── Helpers ──────────────────────────────────────────────

JST = timezone(timedelta(hours=9))


@pytest.fixture()
def status_dir(tmp_path):
    """Patch _status_path to use a temp directory."""
    status_file = tmp_path / "shared" / "system" / "consolidation_status.json"

    with patch("core.lifecycle.system_status._status_path", return_value=status_file):
        yield status_file


# ── load_status ──────────────────────────────────────────

class TestLoadStatus:
    def test_returns_defaults_when_file_missing(self, status_dir):
        from core.lifecycle.system_status import load_status

        result = load_status()
        assert "daily" in result
        assert "weekly" in result
        assert "monthly" in result
        assert result["daily"]["last_status"] == "never"
        assert result["daily"]["running"] is False

    def test_loads_existing_file(self, status_dir):
        from core.lifecycle.system_status import load_status

        status_dir.parent.mkdir(parents=True, exist_ok=True)
        status_dir.write_text(json.dumps({
            "daily": {"last_status": "success", "running": False},
        }))

        result = load_status()
        assert result["daily"]["last_status"] == "success"
        # weekly/monthly should still have defaults
        assert result["weekly"]["last_status"] == "never"

    def test_handles_corrupt_file(self, status_dir):
        from core.lifecycle.system_status import load_status

        status_dir.parent.mkdir(parents=True, exist_ok=True)
        status_dir.write_text("not json")

        result = load_status()
        assert result["daily"]["last_status"] == "never"


# ── mark_started / mark_succeeded / mark_failed ─────────

class TestStateTransitions:
    def test_mark_started(self, status_dir):
        from core.lifecycle.system_status import load_status, mark_started

        entry = mark_started("daily")
        assert entry["running"] is True
        assert entry["last_status"] == "running"
        assert entry["last_started_at"] is not None

        # Verify persisted
        status = load_status()
        assert status["daily"]["running"] is True

    def test_mark_succeeded(self, status_dir):
        from core.lifecycle.system_status import mark_started, mark_succeeded

        mark_started("weekly")
        entry = mark_succeeded("weekly")
        assert entry["running"] is False
        assert entry["last_status"] == "success"
        assert entry["last_success_at"] is not None
        assert entry["last_error"] is None

    def test_mark_failed(self, status_dir):
        from core.lifecycle.system_status import mark_failed, mark_started

        mark_started("monthly")
        entry = mark_failed("monthly", "something broke")
        assert entry["running"] is False
        assert entry["last_status"] == "failed"
        assert entry["last_error"] == "something broke"

    def test_mark_failed_truncates_long_error(self, status_dir):
        from core.lifecycle.system_status import mark_failed

        entry = mark_failed("daily", "x" * 1000)
        assert len(entry["last_error"]) == 500


# ── is_running ───────────────────────────────────────────

class TestIsRunning:
    def test_false_when_not_running(self, status_dir):
        from core.lifecycle.system_status import is_running

        assert is_running("daily") is False

    def test_true_when_running(self, status_dir):
        from core.lifecycle.system_status import is_running, mark_started

        mark_started("daily")
        assert is_running("daily") is True


# ── Missed Detection ─────────────────────────────────────

class TestIsDailyMissed:
    def test_not_missed_before_schedule(self, status_dir):
        from core.lifecycle.system_status import is_daily_missed

        now = datetime(2026, 4, 11, 1, 30, 0, tzinfo=JST)  # Before 02:00
        assert is_daily_missed(now) is False

    def test_missed_after_schedule_no_success(self, status_dir):
        from core.lifecycle.system_status import is_daily_missed

        now = datetime(2026, 4, 11, 3, 0, 0, tzinfo=JST)  # After 02:00
        assert is_daily_missed(now) is True

    def test_not_missed_with_today_success(self, status_dir):
        from core.lifecycle.system_status import is_daily_missed, mark_succeeded

        # Simulate success earlier today
        with patch("core.lifecycle.system_status.now_iso", return_value="2026-04-11T02:15:00+09:00"):
            mark_succeeded("daily")

        now = datetime(2026, 4, 11, 10, 0, 0, tzinfo=JST)
        assert is_daily_missed(now) is False

    def test_missed_with_yesterday_success(self, status_dir):
        from core.lifecycle.system_status import is_daily_missed, mark_succeeded

        with patch("core.lifecycle.system_status.now_iso", return_value="2026-04-10T02:15:00+09:00"):
            mark_succeeded("daily")

        now = datetime(2026, 4, 11, 10, 0, 0, tzinfo=JST)
        assert is_daily_missed(now) is True


class TestIsWeeklyMissed:
    def test_not_missed_before_sunday(self, status_dir):
        from core.lifecycle.system_status import is_weekly_missed

        # 2026-04-08 is Wednesday
        now = datetime(2026, 4, 8, 10, 0, 0, tzinfo=JST)
        assert is_weekly_missed(now) is False

    def test_missed_after_sunday(self, status_dir):
        from core.lifecycle.system_status import is_weekly_missed

        # 2026-04-12 is Sunday, after 03:00
        now = datetime(2026, 4, 12, 4, 0, 0, tzinfo=JST)
        assert is_weekly_missed(now) is True

    def test_not_missed_with_this_week_success(self, status_dir):
        from core.lifecycle.system_status import is_weekly_missed, mark_succeeded

        with patch("core.lifecycle.system_status.now_iso", return_value="2026-04-12T03:30:00+09:00"):
            mark_succeeded("weekly")

        now = datetime(2026, 4, 12, 10, 0, 0, tzinfo=JST)
        assert is_weekly_missed(now) is False


class TestIsMonthlyMissed:
    def test_not_missed_before_first(self, status_dir):
        from core.lifecycle.system_status import is_monthly_missed

        now = datetime(2026, 4, 1, 2, 0, 0, tzinfo=JST)  # Before 03:00 on 1st
        assert is_monthly_missed(now) is False

    def test_missed_after_first(self, status_dir):
        from core.lifecycle.system_status import is_monthly_missed

        now = datetime(2026, 4, 2, 10, 0, 0, tzinfo=JST)
        assert is_monthly_missed(now) is True

    def test_not_missed_with_this_month_success(self, status_dir):
        from core.lifecycle.system_status import is_monthly_missed, mark_succeeded

        with patch("core.lifecycle.system_status.now_iso", return_value="2026-04-01T03:30:00+09:00"):
            mark_succeeded("monthly")

        now = datetime(2026, 4, 15, 10, 0, 0, tzinfo=JST)
        assert is_monthly_missed(now) is False


# ── build_status_payload ─────────────────────────────────

class TestBuildStatusPayload:
    def test_includes_missed_flags(self, status_dir):
        from core.lifecycle.system_status import build_status_payload

        with patch("core.lifecycle.system_status.now_local", return_value=datetime(2026, 4, 11, 10, 0, 0, tzinfo=JST)):
            payload = build_status_payload()

        assert "missed" in payload["daily"]
        assert "missed" in payload["weekly"]
        assert "missed" in payload["monthly"]


# ── clear_stale_running ──────────────────────────────────

class TestClearStaleRunning:
    def test_resets_running_to_failed(self, status_dir):
        from core.lifecycle.system_status import clear_stale_running, load_status, mark_started

        mark_started("daily")
        mark_started("weekly")
        assert load_status()["daily"]["running"] is True

        clear_stale_running()

        status = load_status()
        assert status["daily"]["running"] is False
        assert status["daily"]["last_status"] == "failed"
        assert "server restart" in status["daily"]["last_error"]
        assert status["weekly"]["running"] is False

    def test_noop_when_none_running(self, status_dir):
        from core.lifecycle.system_status import clear_stale_running, load_status

        clear_stale_running()
        status = load_status()
        assert status["daily"]["last_status"] == "never"


# ── Lock-based double execution prevention ───────────────

class TestLockPreventsDoubleExecution:
    @pytest.mark.asyncio
    async def test_lock_prevents_concurrent_run(self, status_dir):
        """Verify that a locked job is skipped rather than blocked."""
        from core.lifecycle import LifecycleManager

        mgr = LifecycleManager.__new__(LifecycleManager)
        mgr._system_job_locks = {
            "daily": asyncio.Lock(),
            "weekly": asyncio.Lock(),
            "monthly": asyncio.Lock(),
        }
        mgr.animas = {}
        mgr._ws_broadcast = None

        call_count = 0

        async def fake_inner():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.1)

        mgr._handle_daily_consolidation_inner = fake_inner

        # Start first call in background
        task1 = asyncio.create_task(mgr._handle_daily_consolidation())
        await asyncio.sleep(0.01)  # Let it acquire the lock

        # Second call should skip
        await mgr._handle_daily_consolidation()

        await task1
        assert call_count == 1  # Only the first call executed


# ── Manual run returns already_running ────────────────────

class TestManualRunAlreadyRunning:
    @pytest.mark.asyncio
    async def test_returns_already_running(self, status_dir):
        from core.lifecycle.system_status import mark_started

        mark_started("daily")

        from core.lifecycle import LifecycleManager

        mgr = LifecycleManager.__new__(LifecycleManager)
        mgr._system_job_locks = {
            "daily": asyncio.Lock(),
            "weekly": asyncio.Lock(),
            "monthly": asyncio.Lock(),
        }
        mgr.animas = {}
        mgr._ws_broadcast = None

        result = await mgr.run_system_consolidation_now("daily")
        assert result.get("error") == "already_running"
