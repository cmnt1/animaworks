from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.
import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.anima import DigitalAnima
from core.config.models import load_config
from core.exceptions import AnimaWorksError  # noqa: F401
from core.schedule_parser import parse_cron_md as _parse_cron_md
from core.schedule_parser import parse_schedule as _parse_schedule
from core.time_utils import get_app_timezone

from .inbox_watcher import InboxWatcherMixin
from .rate_limiter import RateLimiterMixin
from .scheduler import SchedulerMixin
from .system_consolidation import SystemConsolidationMixin
from .system_crons import SystemCronsMixin

logger = logging.getLogger("animaworks.lifecycle")

BroadcastFn = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class LifecycleManager(
    SchedulerMixin,
    InboxWatcherMixin,
    RateLimiterMixin,
    SystemCronsMixin,
    SystemConsolidationMixin,
):
    """Manages heartbeat and cron for Digital Animas via APScheduler."""

    def __init__(self) -> None:
        self.scheduler = AsyncIOScheduler(timezone=get_app_timezone())
        self.animas: dict[str, DigitalAnima] = {}
        self._ws_broadcast: BroadcastFn | None = None
        self._inbox_watcher_task: asyncio.Task | None = None
        self._pending_triggers: set[str] = set()
        self._deferred_timers: dict[str, asyncio.Handle] = {}
        self._last_msg_heartbeat_end: dict[str, float] = {}
        self._pair_heartbeat_times: dict[tuple[str, str], list[float]] = {}
        self._schedule_mtimes: dict[str, tuple[float, float]] = {}
        # Cache heartbeat config at init time (refreshed on reload_anima_schedule)
        hb = load_config().heartbeat
        self._cooldown_s = hb.msg_heartbeat_cooldown_s
        self._cascade_window_s = hb.cascade_window_s
        self._cascade_threshold = hb.cascade_threshold
        self._actionable_intents = hb.actionable_intents

    def set_broadcast(self, fn: BroadcastFn) -> None:
        self._ws_broadcast = fn
        # Propagate to already-registered animas for bg task notifications
        for anima in self.animas.values():
            anima.set_ws_broadcast(fn)

    def register_anima(self, anima: DigitalAnima) -> None:
        self.animas[anima.name] = anima
        # Wire up lock-release callback for deferred inbox processing
        anima.set_on_lock_released(lambda n=anima.name: asyncio.ensure_future(self._on_anima_lock_released(n)))
        # Wire up schedule-changed callback for hot-reload
        anima.set_on_schedule_changed(self.reload_anima_schedule)
        # Wire up WebSocket broadcast for background task notifications
        if self._ws_broadcast:
            anima.set_ws_broadcast(self._ws_broadcast)
        self._setup_heartbeat(anima)
        self._setup_cron_tasks(anima)
        self._record_schedule_mtimes(anima.name, anima.memory.anima_dir)
        logger.info("Registered '%s' with lifecycle manager", anima.name)

    def unregister_anima(self, name: str) -> None:
        """Remove an anima and all their scheduled jobs."""
        anima = self.animas.pop(name, None)
        if anima:
            anima._session_compactor.cancel_all_for_anima(name)
        self._schedule_mtimes.pop(name, None)
        self._pending_triggers.discard(name)
        timer = self._deferred_timers.pop(name, None)
        if timer:
            timer.cancel()
        # Remove all scheduler jobs belonging to this anima
        for job in self.scheduler.get_jobs():
            if job.id.startswith(f"{name}_") or job.id == f"consolidation_retry_{name}":
                job.remove()
        logger.info("Unregistered '%s' from lifecycle manager", name)

    def reload_anima_schedule(self, name: str) -> dict[str, Any]:
        """Reload heartbeat and cron schedules for an anima from disk.

        Called when heartbeat.md or cron.md is modified at runtime.

        Args:
            name: The anima name whose schedule should be reloaded.

        Returns:
            A summary dict with keys ``reloaded``, ``removed``, ``new_jobs``
            (or ``error`` if the anima is not registered).
        """
        anima = self.animas.get(name)
        if not anima:
            logger.warning("reload_anima_schedule: '%s' not registered", name)
            return {"error": f"Anima '{name}' not registered"}

        # Refresh cached heartbeat config
        hb = load_config().heartbeat
        self._cooldown_s = hb.msg_heartbeat_cooldown_s
        self._cascade_window_s = hb.cascade_window_s
        self._cascade_threshold = hb.cascade_threshold
        self._actionable_intents = hb.actionable_intents

        # Remove existing heartbeat and cron jobs for this anima
        removed = 0
        for job in self.scheduler.get_jobs():
            if job.id.startswith(f"{name}_"):
                job.remove()
                removed += 1

        # Re-setup from current files on disk
        self._setup_heartbeat(anima)
        self._setup_cron_tasks(anima)
        self._record_schedule_mtimes(name, anima.memory.anima_dir)

        new_jobs = [j.id for j in self.scheduler.get_jobs() if j.id.startswith(f"{name}_")]
        logger.info(
            "Reloaded schedule for '%s': removed=%d, new_jobs=%s",
            name,
            removed,
            new_jobs,
        )
        return {"reloaded": name, "removed": removed, "new_jobs": new_jobs}

    def start(self) -> None:
        self.scheduler.start()
        self._setup_system_crons()
        self._inbox_watcher_task = asyncio.create_task(self._inbox_watcher_loop())
        logger.info("Lifecycle manager started (scheduler + inbox watcher + system crons)")

    def shutdown(self) -> None:
        if self._inbox_watcher_task:
            self._inbox_watcher_task.cancel()
        for timer in self._deferred_timers.values():
            timer.cancel()
        self._deferred_timers.clear()
        for anima in self.animas.values():
            anima._session_compactor.shutdown()
        self.scheduler.shutdown(wait=False)
        logger.info("Lifecycle manager stopped")


# Re-exports for backward compatibility (tests patch "core.lifecycle.load_config")
__all__ = [
    "LifecycleManager",
    "BroadcastFn",
    "_parse_cron_md",
    "_parse_schedule",
]
