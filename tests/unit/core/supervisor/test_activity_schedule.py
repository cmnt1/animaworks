"""Tests for root-owned activity-schedule interpretation and application."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest

from core.config.io import invalidate_cache, load_config, save_config
from core.config.models import ActivityScheduleEntry, AnimaWorksConfig
from server.supervisor.activity_schedule import apply_activity_schedule, resolve_scheduled_level, time_in_range


@pytest.mark.parametrize(
    ("start", "end", "now", "expected"),
    [
        ("08:00", "22:00", "12:00", True),
        ("08:00", "22:00", "23:00", False),
        ("08:00", "22:00", "08:00", True),
        ("08:00", "22:00", "22:00", False),
        ("22:00", "08:00", "23:00", True),
        ("22:00", "08:00", "03:00", True),
        ("22:00", "08:00", "12:00", False),
    ],
)
def test_time_in_range(start: str, end: str, now: str, expected: bool) -> None:
    assert time_in_range(start, end, now) is expected


def test_resolve_scheduled_level_handles_midnight_wrap() -> None:
    schedule = [
        ActivityScheduleEntry(start="08:00", end="22:00", level=100),
        ActivityScheduleEntry(start="22:00", end="08:00", level=30),
    ]
    assert resolve_scheduled_level(schedule, "12:00") == 100
    assert resolve_scheduled_level(schedule, "23:00") == 30
    assert resolve_scheduled_level(schedule, "03:00") == 30
    assert resolve_scheduled_level([], "12:00") is None


def test_root_apply_updates_level_and_active_schedule_row(tmp_path, monkeypatch) -> None:
    from core.config.io import get_config_path

    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    invalidate_cache()
    config_path = get_config_path()
    save_config(
        AnimaWorksConfig(
            activity_level=100,
            activity_schedule=[
                ActivityScheduleEntry(start="08:00", end="22:00", level=100),
                ActivityScheduleEntry(start="22:00", end="08:00", level=30),
            ],
        ),
        config_path,
    )
    invalidate_cache()

    result = apply_activity_schedule(activity_level=50, now_hhmm="23:00")

    assert result.activity_level_changed is True
    assert result.activity_schedule_changed is True
    updated = load_config(config_path)
    assert updated.activity_level == 50
    assert updated.activity_schedule[1].level == 50


def test_root_apply_schedule_immediately_selects_current_slot(tmp_path, monkeypatch) -> None:
    from core.config.io import get_config_path

    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    invalidate_cache()
    config_path = get_config_path()
    save_config(AnimaWorksConfig(activity_level=100), config_path)
    invalidate_cache()

    result = apply_activity_schedule(
        activity_schedule=[
            ActivityScheduleEntry(start="08:00", end="22:00", level=90),
            ActivityScheduleEntry(start="22:00", end="08:00", level=25),
        ],
        now_hhmm="23:00",
    )

    assert result.activity_level_changed is True
    assert result.config.activity_level == 25
    assert result.config.activity_schedule[1].level == 25
