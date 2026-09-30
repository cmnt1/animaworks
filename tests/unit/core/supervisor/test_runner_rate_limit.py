"""Unit tests for rate limiting in core/supervisor/inbox_rate_limiter.py."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.config.models import load_config
from core.supervisor.inbox_rate_limiter import InboxRateLimiter, _cascade_senders
from core.supervisor.scheduler_manager import SchedulerManager

# ── Helpers ──────────────────────────────────────────────────


def _make_limiter() -> InboxRateLimiter:
    """Create an InboxRateLimiter with minimal config for unit testing."""
    mock_anima = MagicMock()
    mock_anima.messenger = MagicMock()
    mock_anima._lock = asyncio.Lock()

    mock_scheduler_mgr = MagicMock(spec=SchedulerManager)
    mock_scheduler_mgr.heartbeat_running = False

    limiter = InboxRateLimiter(
        anima=mock_anima,
        anima_name="test",
        shutdown_event=asyncio.Event(),
        scheduler_mgr=mock_scheduler_mgr,
    )
    return limiter


# ── TestCooldown ─────────────────────────────────────────────


class TestCooldown:
    """Tests for is_in_cooldown() method."""

    def test_no_cooldown_initially(self):
        """is_in_cooldown() returns False when _last_msg_heartbeat_end is far in the past."""
        limiter = _make_limiter()
        # Ensure _last_msg_heartbeat_end is far enough in the past
        # (default 0.0 may be within cooldown on freshly booted CI runners
        # where time.monotonic() < cooldown_sec)
        limiter._last_msg_heartbeat_end = time.monotonic() - limiter._cooldown_sec - 1
        assert limiter.is_in_cooldown() is False

    def test_in_cooldown_within_60s(self):
        """Returns True when heartbeat ended less than 60s ago."""
        limiter = _make_limiter()
        limiter._last_msg_heartbeat_end = time.monotonic()
        assert limiter.is_in_cooldown() is True

    def test_cooldown_expired(self):
        """Returns False when cooldown period has passed since last heartbeat end."""
        limiter = _make_limiter()
        cooldown_s = load_config().heartbeat.msg_heartbeat_cooldown_s
        limiter._last_msg_heartbeat_end = time.monotonic() - cooldown_s - 1
        assert limiter.is_in_cooldown() is False


# ── TestCascadeDetection ─────────────────────────────────────


class TestCascadeDetection:
    """Tests for check_cascade() method."""

    def test_self_and_system_messages_are_not_cascade_senders(self):
        limiter = _make_limiter()
        self_messages = [SimpleNamespace(from_person="test", source="anima") for _ in range(3)]
        system_messages = [SimpleNamespace(from_person="github-gateway", source="system") for _ in range(3)]

        self_senders = _cascade_senders(self_messages, "test")
        system_senders = _cascade_senders(system_messages, "test")
        limiter.record_pair_heartbeat(self_senders | system_senders)

        assert limiter.check_cascade(self_senders | system_senders) is False
        assert limiter._pair_heartbeat_times == {}

    def test_internal_anima_exchange_still_triggers_cascade(self):
        limiter = _make_limiter()
        messages = [SimpleNamespace(from_person="alice", source="anima") for _ in range(3)]
        senders = _cascade_senders(messages, "test")
        for _ in range(load_config().heartbeat.cascade_threshold):
            limiter.record_pair_heartbeat(senders)

        assert senders == {"alice"}
        assert limiter.check_cascade(senders) is True

    def test_no_cascade_below_threshold(self):
        """check_cascade returns False when below cascade_threshold."""
        limiter = _make_limiter()
        threshold = load_config().heartbeat.cascade_threshold
        now = time.monotonic()
        key = ("test", "alice")
        # Add entries below threshold
        limiter._pair_heartbeat_times[key] = [now - (i + 1) for i in range(threshold - 1)]
        assert limiter.check_cascade({"alice"}) is False

    def test_cascade_detected_at_threshold(self):
        """Returns True when exactly cascade_threshold round-trips in window."""
        limiter = _make_limiter()
        threshold = load_config().heartbeat.cascade_threshold
        now = time.monotonic()
        key = ("test", "alice")
        limiter._pair_heartbeat_times[key] = [now - (i + 1) for i in range(threshold)]
        assert limiter.check_cascade({"alice"}) is True

    def test_cascade_entries_expire(self):
        """Old entries outside cascade window are evicted."""
        limiter = _make_limiter()
        cfg = load_config().heartbeat
        now = time.monotonic()
        key = ("test", "alice")
        # All entries are older than the cascade window
        limiter._pair_heartbeat_times[key] = [
            now - cfg.cascade_window_s - 100,
            now - cfg.cascade_window_s - 50,
            now - cfg.cascade_window_s - 20,
            now - cfg.cascade_window_s - 10,
        ]
        assert limiter.check_cascade({"alice"}) is False
        # Expired entries should have been evicted
        assert key not in limiter._pair_heartbeat_times


# ── TestRecordPairHeartbeat ──────────────────────────────────


class TestRecordPairHeartbeat:
    """Tests for record_pair_heartbeat() method."""

    def test_records_pair_timestamp(self):
        """Adds entry to _pair_heartbeat_times dict."""
        limiter = _make_limiter()
        before = time.monotonic()
        limiter.record_pair_heartbeat({"alice"})
        after = time.monotonic()

        key = ("test", "alice")
        assert key in limiter._pair_heartbeat_times
        times = limiter._pair_heartbeat_times[key]
        assert len(times) == 1
        assert before <= times[0] <= after

    def test_records_multiple_senders(self):
        """Records entries for each sender separately."""
        limiter = _make_limiter()
        limiter.record_pair_heartbeat({"alice", "bob"})

        assert ("test", "alice") in limiter._pair_heartbeat_times
        assert ("test", "bob") in limiter._pair_heartbeat_times

    def test_appends_to_existing(self):
        """Appends timestamps to existing entries rather than replacing."""
        limiter = _make_limiter()
        limiter.record_pair_heartbeat({"alice"})
        limiter.record_pair_heartbeat({"alice"})

        key = ("test", "alice")
        assert len(limiter._pair_heartbeat_times[key]) == 2


# ── TestInboxWatcher ─────────────────────────────────────────


class TestInboxWatcher:
    """Tests for inbox_watcher_loop() method."""

    @pytest.mark.asyncio
    async def test_skips_when_pending_trigger(self):
        """Loop continues without triggering when _pending_trigger is True."""
        limiter = _make_limiter()
        limiter._pending_trigger = True

        # Set shutdown after first iteration
        iteration_count = 0
        original_sleep = asyncio.sleep

        async def mock_sleep(duration):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 1:
                limiter._shutdown_event.set()
            await original_sleep(0)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await limiter.inbox_watcher_loop()

        # messenger.has_unread should never be called because
        # _pending_trigger short-circuits first
        limiter._anima.messenger.has_unread.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_in_cooldown(self):
        """Loop continues without triggering when in cooldown."""
        limiter = _make_limiter()
        limiter._last_msg_heartbeat_end = time.monotonic()  # Just ended
        limiter._anima.messenger.has_unread.return_value = True

        iteration_count = 0
        original_sleep = asyncio.sleep

        async def mock_sleep(duration):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 1:
                limiter._shutdown_event.set()
            await original_sleep(0)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await limiter.inbox_watcher_loop()

        # _pending_trigger should remain False — no heartbeat was triggered
        assert limiter._pending_trigger is False

    @pytest.mark.asyncio
    async def test_defers_when_inbox_job_in_flight(self):
        """Watcher defers the next trigger while an inbox job is in flight.

        Previously this was keyed off the anima's ``_inbox_lock``; after the
        inbox moved to isolated task runners the in-flight indicator is
        ``_pending_trigger``.
        """
        limiter = _make_limiter()
        limiter._anima.messenger.has_unread.return_value = True
        limiter._pending_trigger = True  # an inbox job is already running

        iteration_count = 0
        original_sleep = asyncio.sleep

        async def mock_sleep(duration):
            nonlocal iteration_count
            iteration_count += 1
            if iteration_count >= 1:
                limiter._shutdown_event.set()
            await original_sleep(0)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            await limiter.inbox_watcher_loop()

        # The in-flight job is still marked running; no new trigger was queued.
        assert limiter._pending_trigger is True
        limiter._anima.messenger.has_unread.assert_not_called()
