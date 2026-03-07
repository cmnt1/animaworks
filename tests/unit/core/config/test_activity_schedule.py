"""Unit tests for ActivityScheduleEntry and activity_schedule in AnimaWorksConfig."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config.models import ActivityScheduleEntry, AnimaWorksConfig

# ── ActivityScheduleEntry ─────────────────────────────────────


class TestActivityScheduleEntryValid:
    """Tests for valid ActivityScheduleEntry creation."""

    def test_valid_night_mode_entry(self) -> None:
        """Valid entry with midnight wrap (22:00–08:00, level 30)."""
        entry = ActivityScheduleEntry(start="22:00", end="08:00", level=30)
        assert entry.start == "22:00"
        assert entry.end == "08:00"
        assert entry.level == 30

    def test_valid_daytime_entry(self) -> None:
        """Valid entry with normal range (08:00–22:00, level 100)."""
        entry = ActivityScheduleEntry(start="08:00", end="22:00", level=100)
        assert entry.start == "08:00"
        assert entry.end == "22:00"
        assert entry.level == 100

    def test_valid_level_boundaries(self) -> None:
        """Level 10 and 400 are valid boundaries."""
        assert ActivityScheduleEntry(start="00:00", end="23:59", level=10).level == 10
        assert ActivityScheduleEntry(start="00:00", end="12:00", level=400).level == 400


class TestActivityScheduleEntryInvalidStart:
    """Tests for invalid start time format."""

    @pytest.mark.parametrize("invalid_start", ["24:00", "25:00", "9:00", "07:60", "abc", "12:99"])
    def test_invalid_start_raises_validation_error(self, invalid_start: str) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ActivityScheduleEntry(start=invalid_start, end="08:00", level=30)
        assert "start" in str(exc_info.value).lower() or "Invalid" in str(exc_info.value)


class TestActivityScheduleEntryInvalidEnd:
    """Tests for invalid end time format."""

    @pytest.mark.parametrize("invalid_end", ["24:00", "25:00", "9:00", "07:60", "xyz"])
    def test_invalid_end_raises_validation_error(self, invalid_end: str) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ActivityScheduleEntry(start="22:00", end=invalid_end, level=30)
        assert "end" in str(exc_info.value).lower() or "Invalid" in str(exc_info.value)


class TestActivityScheduleEntryStartEqualsEnd:
    """Tests for start == end validation."""

    def test_start_equals_end_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ActivityScheduleEntry(start="22:00", end="22:00", level=30)
        assert "start and end must differ" in str(exc_info.value)


class TestActivityScheduleEntryLevelBounds:
    """Tests for level validation (10–400)."""

    def test_level_below_10_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            ActivityScheduleEntry(start="22:00", end="08:00", level=9)

    def test_level_zero_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            ActivityScheduleEntry(start="22:00", end="08:00", level=0)

    def test_level_above_400_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            ActivityScheduleEntry(start="22:00", end="08:00", level=401)


# ── AnimaWorksConfig with activity_schedule ───────────────────


class TestAnimaWorksConfigActivitySchedule:
    """Tests for activity_schedule in AnimaWorksConfig."""

    def test_empty_activity_schedule_default(self) -> None:
        """Default config has empty activity_schedule list."""
        config = AnimaWorksConfig()
        assert config.activity_schedule == []

    def test_activity_schedule_with_entries(self) -> None:
        """Config with activity_schedule list serializes and deserializes."""
        entries = [
            {"start": "08:00", "end": "22:00", "level": 100},
            {"start": "22:00", "end": "08:00", "level": 30},
        ]
        config = AnimaWorksConfig(activity_schedule=entries)
        assert len(config.activity_schedule) == 2
        assert config.activity_schedule[0].start == "08:00"
        assert config.activity_schedule[0].end == "22:00"
        assert config.activity_schedule[0].level == 100
        assert config.activity_schedule[1].start == "22:00"
        assert config.activity_schedule[1].end == "08:00"
        assert config.activity_schedule[1].level == 30

    def test_activity_schedule_serialization_roundtrip(self) -> None:
        """activity_schedule survives JSON roundtrip."""
        entries = [
            ActivityScheduleEntry(start="08:00", end="22:00", level=100),
            ActivityScheduleEntry(start="22:00", end="08:00", level=30),
        ]
        config = AnimaWorksConfig(activity_schedule=entries)
        data = config.model_dump(mode="json")
        assert "activity_schedule" in data
        assert len(data["activity_schedule"]) == 2
        restored = AnimaWorksConfig.model_validate(data)
        assert restored.activity_schedule[0].start == "08:00"
        assert restored.activity_schedule[0].level == 100
        assert restored.activity_schedule[1].start == "22:00"
        assert restored.activity_schedule[1].level == 30

    def test_activity_schedule_from_json(self) -> None:
        """Config loads activity_schedule from JSON dict."""
        raw = {
            "version": 1,
            "activity_schedule": [
                {"start": "22:00", "end": "08:00", "level": 30},
            ],
        }
        config = AnimaWorksConfig.model_validate(raw)
        assert len(config.activity_schedule) == 1
        assert config.activity_schedule[0].start == "22:00"
        assert config.activity_schedule[0].end == "08:00"
        assert config.activity_schedule[0].level == 30
