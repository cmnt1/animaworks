"""Unit tests for activity schedule (night mode) in SchedulerManager."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from core.config.models import ActivityScheduleEntry
from core.supervisor.scheduler_manager import (
    SchedulerManager,
    _time_in_range,
)

# ── _time_in_range ─────────────────────────────────────────────


@pytest.mark.parametrize(
    ("start", "end", "now", "expected"),
    [
        # Normal range (08:00–22:00)
        ("08:00", "22:00", "12:00", True),  # inside
        ("08:00", "22:00", "23:00", False),  # outside
        ("08:00", "22:00", "08:00", True),  # boundary start inclusive
        ("08:00", "22:00", "22:00", False),  # boundary end exclusive
        # Midnight wrap (22:00–08:00)
        ("22:00", "08:00", "23:00", True),  # inside night
        ("22:00", "08:00", "03:00", True),  # inside early morning
        ("22:00", "08:00", "12:00", False),  # daytime outside
    ],
)
def test_time_in_range(start: str, end: str, now: str, expected: bool) -> None:
    """Parametrized tests for _time_in_range."""
    assert _time_in_range(start, end, now) is expected


# ── resolve_scheduled_level ───────────────────────────────────


class TestResolveScheduledLevel:
    """Tests for SchedulerManager.resolve_scheduled_level."""

    def test_two_entry_schedule_daytime(self) -> None:
        """Daytime (12:00) returns daytime level (100)."""
        schedule = [
            ActivityScheduleEntry(start="08:00", end="22:00", level=100),
            ActivityScheduleEntry(start="22:00", end="08:00", level=30),
        ]
        result = SchedulerManager.resolve_scheduled_level(schedule, "12:00")
        assert result == 100

    def test_two_entry_schedule_nighttime(self) -> None:
        """Nighttime (23:00) returns nighttime level (30)."""
        schedule = [
            ActivityScheduleEntry(start="08:00", end="22:00", level=100),
            ActivityScheduleEntry(start="22:00", end="08:00", level=30),
        ]
        result = SchedulerManager.resolve_scheduled_level(schedule, "23:00")
        assert result == 30

    def test_two_entry_schedule_early_morning(self) -> None:
        """Early morning (03:00) returns nighttime level (30)."""
        schedule = [
            ActivityScheduleEntry(start="08:00", end="22:00", level=100),
            ActivityScheduleEntry(start="22:00", end="08:00", level=30),
        ]
        result = SchedulerManager.resolve_scheduled_level(schedule, "03:00")
        assert result == 30

    def test_empty_schedule_returns_none(self) -> None:
        """Empty schedule returns None."""
        result = SchedulerManager.resolve_scheduled_level([], "12:00")
        assert result is None
