"""Registration-time diagnostics for cron schedules that waste LLM runs.

The diagnostics are advisory: they never reject or alter a cron registration.
They are computed from the APScheduler trigger itself so expressions such as
``*/15 * * * *`` and ``0,15,30,45 * * * *`` are treated identically.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from apscheduler.triggers.base import BaseTrigger

from core.schemas import CronTask
from core.time_utils import now_local

HIGH_FREQUENCY_LLM = "high_frequency_llm"
COMMAND_WITHOUT_SKIP = "command_without_skip"

HIGH_FREQUENCY_THRESHOLD_MINUTES = 30.0
_INTERVAL_PROBES = 10


def minimum_fire_interval_minutes(
    trigger: BaseTrigger,
    *,
    base_time: datetime | None = None,
    probes: int = _INTERVAL_PROBES,
) -> float | None:
    """Return the smallest interval between consecutive upcoming fires.

    Starting from *base_time*, advance ``get_next_fire_time()`` up to *probes*
    times. ``None`` means the trigger will not fire again, so it cannot be
    diagnosed as high-frequency.
    """
    current = trigger.get_next_fire_time(None, base_time or now_local())
    if current is None:
        return None
    intervals: list[float] = []
    for _ in range(max(probes, 1)):
        following = trigger.get_next_fire_time(current, current + timedelta(microseconds=1))
        if following is None:
            break
        intervals.append((following - current).total_seconds() / 60.0)
        current = following
    return min(intervals) if intervals else None


def diagnose_cron_task(
    task: CronTask,
    trigger: BaseTrigger,
    *,
    base_time: datetime | None = None,
) -> list[str]:
    """Return diagnostic codes for one cron task (empty = healthy)."""
    if task.type not in {"llm", "command"}:
        return []
    interval = minimum_fire_interval_minutes(trigger, base_time=base_time)
    if interval is None or interval > HIGH_FREQUENCY_THRESHOLD_MINUTES:
        return []
    if task.type == "llm":
        return [HIGH_FREQUENCY_LLM]
    if task.trigger_heartbeat and not task.skip_pattern:
        return [COMMAND_WITHOUT_SKIP]
    return []


def cron_diagnostics_digest(diagnostics: Mapping[str, Sequence[str]]) -> str:
    """Return a canonical digest for a task-name -> diagnostic-code mapping."""
    canonical = {name: sorted(codes) for name, codes in diagnostics.items() if codes}
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "COMMAND_WITHOUT_SKIP",
    "HIGH_FREQUENCY_LLM",
    "HIGH_FREQUENCY_THRESHOLD_MINUTES",
    "cron_diagnostics_digest",
    "diagnose_cron_task",
    "minimum_fire_interval_minutes",
]
