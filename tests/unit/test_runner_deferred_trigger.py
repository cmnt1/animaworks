"""Unit tests for deferred Inbox wakeups and lock-release notification."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.supervisor.inbox_rate_limiter import InboxRateLimiter
from core.supervisor.scheduler_manager import SchedulerManager


def _make_limiter(tmp_path: Path) -> InboxRateLimiter:
    anima = MagicMock()
    anima.anima_dir = tmp_path / "animas" / "defer-test"
    anima.messenger.has_unread.return_value = False
    scheduler_mgr = MagicMock(spec=SchedulerManager)
    scheduler_mgr.heartbeat_running = False
    return InboxRateLimiter(
        anima=anima,
        anima_name="defer-test",
        shutdown_event=asyncio.Event(),
        scheduler_mgr=scheduler_mgr,
    )


class TestScheduleDeferredTrigger:
    @pytest.mark.asyncio
    async def test_schedules_one_timer_that_wakes_the_watcher(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path)
        limiter._failure_retry_until = asyncio.get_running_loop().time() + 0.05

        limiter.schedule_deferred_trigger()
        timer = limiter._deferred_timer
        assert timer is not None
        limiter.schedule_deferred_trigger()
        assert limiter._deferred_timer is timer

        await asyncio.wait_for(limiter._inbox_wake_event.wait(), timeout=3.0)
        assert limiter._deferred_timer is None


class TestOnAnimaLockReleased:
    def test_unread_messages_wake_the_watcher(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path)
        limiter._anima.messenger.has_unread.return_value = True

        limiter.on_anima_lock_released()

        assert limiter._inbox_wake_event.is_set()
        assert limiter._deferred_timer is None

    def test_no_wake_when_there_are_no_unread_messages(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path)

        limiter.on_anima_lock_released()

        limiter._anima.messenger.has_unread.assert_called_once_with()
        assert not limiter._inbox_wake_event.is_set()

    def test_no_duplicate_wake_when_a_job_is_pending(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path)
        limiter._anima.messenger.has_unread.return_value = True
        limiter._pending_trigger = True

        limiter.on_anima_lock_released()

        assert not limiter._inbox_wake_event.is_set()

    def test_no_action_when_anima_is_unavailable(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path)
        limiter._anima = None

        limiter.on_anima_lock_released()

        assert not limiter._inbox_wake_event.is_set()


class TestDeferredTimerCleanup:
    def test_cancel_deferred_timer(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path)
        mock_timer = MagicMock()
        limiter._deferred_timer = mock_timer

        limiter.cancel_deferred_timer()

        mock_timer.cancel.assert_called_once()
        assert limiter._deferred_timer is None

    def test_cancel_noop_when_no_timer(self, tmp_path: Path) -> None:
        limiter = _make_limiter(tmp_path)

        limiter.cancel_deferred_timer()

        assert limiter._deferred_timer is None
