from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Root-owned interpretation and application of the global activity schedule."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from core.config.models import ActivityScheduleEntry, AnimaWorksConfig
from core.time_utils import now_local

logger = logging.getLogger(__name__)
_UNSET = object()


@dataclass(frozen=True)
class ActivityScheduleUpdate:
    """Result of applying a schedule mutation or the current time slot."""

    config: AnimaWorksConfig
    activity_level_changed: bool
    activity_schedule_changed: bool


def time_in_range(start: str, end: str, now: str) -> bool:
    """Check whether *now* (``HH:MM``) falls within [*start*, *end*)."""
    if start <= end:
        return start <= now < end
    return now >= start or now < end


def resolve_scheduled_level(schedule: Sequence[ActivityScheduleEntry], now_hhmm: str) -> int | None:
    """Return the first configured activity level matching *now_hhmm*."""
    for entry in schedule:
        if time_in_range(entry.start, entry.end, now_hhmm):
            return entry.level
    return None


def apply_activity_schedule(
    *,
    activity_level: int | object = _UNSET,
    activity_schedule: Sequence[ActivityScheduleEntry] | object = _UNSET,
    now_hhmm: str | None = None,
) -> ActivityScheduleUpdate:
    """Apply the current schedule slot and optional setting changes once on root.

    Setting ``activity_level`` also updates the currently-active schedule row,
    matching the existing settings API behavior. Replacing ``activity_schedule``
    immediately applies its matching row when one exists. A periodic root cron
    calls this with no overrides to advance the current level at schedule
    boundaries.
    """
    from core.anima.settings_store import update_config

    current_time = now_hhmm or now_local().strftime("%H:%M")
    level_changed = False
    schedule_changed = False

    def apply(config: AnimaWorksConfig) -> AnimaWorksConfig:
        nonlocal level_changed, schedule_changed
        old_level = config.activity_level
        old_schedule = [entry.model_dump(mode="json") for entry in config.activity_schedule]

        if activity_level is not _UNSET:
            config.activity_level = int(activity_level)
            for entry in config.activity_schedule:
                if time_in_range(entry.start, entry.end, current_time):
                    entry.level = int(activity_level)
                    break

        if activity_schedule is not _UNSET:
            config.activity_schedule = list(activity_schedule)  # type: ignore[arg-type]

        scheduled_level = resolve_scheduled_level(config.activity_schedule, current_time)
        if scheduled_level is not None:
            config.activity_level = scheduled_level

        level_changed = config.activity_level != old_level
        schedule_changed = [entry.model_dump(mode="json") for entry in config.activity_schedule] != old_schedule
        return config

    updated = update_config(apply)
    return ActivityScheduleUpdate(
        config=updated,
        activity_level_changed=level_changed,
        activity_schedule_changed=schedule_changed,
    )


__all__ = [
    "ActivityScheduleUpdate",
    "apply_activity_schedule",
    "resolve_scheduled_level",
    "time_in_range",
]
