# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Event-driven inbox wakeups and deferred trigger management."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from core.config.models import load_config
from core.platform.tasks import spawn

if TYPE_CHECKING:
    from core.anima.digital_anima import DigitalAnima
    from core.runtime.scheduler_manager import SchedulerManager

logger = logging.getLogger(__name__)

_INBOX_RECHECK_INTERVAL_SEC = 45.0
_DISABLED_SKIP_LOG_COOLDOWN_SEC = 30.0
_PROVIDER_FAILURE_RETRY_MIN_SEC = 30.0


def _read_anima_enabled(anima_dir: Path) -> bool:
    """Read status.json ``enabled`` flag (default True if missing/unreadable)."""
    from core.platform.status_store import read_status

    return bool(read_status(anima_dir).get("enabled", True))


class InboxRateLimiter:
    """Coordinate one-at-a-time inbox jobs, filesystem wakeups, and provider backoff."""

    def __init__(
        self,
        anima: DigitalAnima,
        anima_name: str,
        shutdown_event: asyncio.Event,
        scheduler_mgr: SchedulerManager,
    ) -> None:
        self._anima = anima
        self._anima_name = anima_name
        self._shutdown_event = shutdown_event
        self._scheduler_mgr = scheduler_mgr

        self._pending_trigger = False
        self._inbox_run_lock = asyncio.Lock()
        self._inbox_wake_event = asyncio.Event()
        self._deferred_timer: asyncio.Handle | None = None
        self._last_disabled_skip_log = 0.0
        self._failure_retry_until = 0.0

    def _retry_is_delayed(self) -> bool:
        """Provider failures retain unread messages without hot-looping them."""
        return time.monotonic() < self._failure_retry_until

    def _record_processing_failure(self) -> None:
        delay = _PROVIDER_FAILURE_RETRY_MIN_SEC
        try:
            from core.config.model_config import _guard_key_for_model_config, resolve_effective_model_config
            from core.llm.guard.rate_guard import get_rate_guard
            from core.schemas import ModelConfig

            config = self._anima.agent.model_config
            if isinstance(config, ModelConfig):
                effective = resolve_effective_model_config(config)
                # When every candidate is blocked, wait for the earliest
                # recovery candidate instead of issuing repeated provider calls.
                key = _guard_key_for_model_config(effective, load_config())
                delay = max(delay, get_rate_guard().blocked_remaining(key))
        except Exception:
            logger.debug("Could not inspect provider retry guard; retaining minimum inbox backoff", exc_info=True)
        self._failure_retry_until = time.monotonic() + delay

    def _start_inbox_observer(self, loop: asyncio.AbstractEventLoop):
        """Watch top-level inbox JSON files and forward changes to the event loop."""
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer

            inbox_dir = Path(self._anima.messenger.inbox_dir).resolve()
            limiter = self

            class InboxEventHandler(FileSystemEventHandler):
                def on_any_event(self, event) -> None:
                    if event.is_directory:
                        return
                    candidates = [getattr(event, "src_path", ""), getattr(event, "dest_path", "")]
                    for candidate in candidates:
                        if not candidate:
                            continue
                        path = Path(candidate)
                        if path.suffix == ".json" and path.parent.resolve() == inbox_dir:
                            try:
                                loop.call_soon_threadsafe(limiter._inbox_wake_event.set)
                            except RuntimeError:
                                logger.debug("Inbox wake arrived after the event loop closed")
                            return

            observer = Observer()
            observer.schedule(InboxEventHandler(), str(inbox_dir), recursive=False)
            observer.start()
            logger.info("Inbox filesystem watcher started for %s", self._anima_name)
            return observer
        except Exception:
            logger.warning(
                "Inbox filesystem watcher unavailable for %s; using %.0fs safety rechecks",
                self._anima_name,
                _INBOX_RECHECK_INTERVAL_SEC,
                exc_info=True,
            )
            return None

    def on_anima_lock_released(self) -> None:
        """Wake the inbox watcher after the Anima releases its processing lock."""
        if self._anima and self._anima.messenger.has_unread() and not self._pending_trigger:
            self._inbox_wake_event.set()

    def schedule_deferred_trigger(self) -> None:
        """Recheck unread messages after provider backoff or a busy heartbeat."""
        if self._deferred_timer is not None:
            return
        remaining = max(self._failure_retry_until - time.monotonic(), 0.0)
        delay = max(remaining, 2.0)
        loop = asyncio.get_running_loop()

        def wake_inbox() -> None:
            self._deferred_timer = None
            self._inbox_wake_event.set()

        self._deferred_timer = loop.call_later(delay, wake_inbox)
        logger.debug("Deferred inbox check scheduled for %s in %.1fs", self._anima_name, delay)

    async def message_triggered_inbox(self) -> None:
        """Run one inbox job; arrivals during it are coalesced into the next job."""
        if self._inbox_run_lock.locked():
            # The active job checks for unread messages on exit and raises one
            # wake for the next batch, so parallel triggers need not queue here.
            return

        async with self._inbox_run_lock:
            if not self._anima:
                self._pending_trigger = False
                return
            self._pending_trigger = True

            if self._retry_is_delayed():
                self._pending_trigger = False
                self.schedule_deferred_trigger()
                return

            # Disabled animas keep messages unread until re-enabled.
            if not _read_anima_enabled(self._anima.anima_dir):
                now = time.monotonic()
                if now - self._last_disabled_skip_log >= _DISABLED_SKIP_LOG_COOLDOWN_SEC:
                    logger.info(
                        "Inbox processing skip: anima disabled (%s); messages left unread",
                        self._anima_name,
                    )
                    self._last_disabled_skip_log = now
                self._pending_trigger = False
                return

            if self._scheduler_mgr.heartbeat_running:
                logger.info("Message-triggered inbox deferred (heartbeat already running): %s", self._anima_name)
                self._pending_trigger = False
                self.schedule_deferred_trigger()
                return

            self._scheduler_mgr.heartbeat_running = True
            try:
                logger.info("Message-triggered inbox: %s", self._anima_name)
                isolated = await self._scheduler_mgr._task_runner_supervisor.run_inbox()
                result = isolated.get("result")
                if not isinstance(result, dict):
                    raise ValueError("isolated inbox result must be an object")
                if (
                    not isolated.get("success")
                    or result.get("action") == "error"
                    or isinstance(result.get("reason"), str)
                    and result.get("reason")
                ):
                    self._record_processing_failure()
                else:
                    self._failure_retry_until = 0.0
            except Exception:
                self._record_processing_failure()
                logger.exception("Message-triggered inbox failed: %s", self._anima_name)
            finally:
                self._scheduler_mgr.heartbeat_running = False
                self._pending_trigger = False
                try:
                    if self._anima.messenger.has_unread():
                        if self._retry_is_delayed():
                            self.schedule_deferred_trigger()
                        else:
                            self._inbox_wake_event.set()
                except Exception:
                    logger.debug("Could not check inbox after processing", exc_info=True)

    async def inbox_watcher_loop(self) -> None:
        """Wake on inbox file changes, with an infrequent safety rescan."""
        if not self._anima:
            return

        logger.info("Inbox watcher started for %s", self._anima_name)
        observer = self._start_inbox_observer(asyncio.get_running_loop())
        # Reconcile messages already present at startup, even if they predate
        # the filesystem observer.
        self._inbox_wake_event.set()
        try:
            while not self._shutdown_event.is_set():
                try:
                    try:
                        await asyncio.wait_for(
                            self._inbox_wake_event.wait(),
                            timeout=_INBOX_RECHECK_INTERVAL_SEC,
                        )
                    except TimeoutError:
                        # Filesystem notifications can be missed on some mounts.
                        pass
                    self._inbox_wake_event.clear()

                    if self._shutdown_event.is_set() or self._pending_trigger:
                        continue
                    if not self._anima.messenger.has_unread():
                        continue
                    if self._retry_is_delayed():
                        self.schedule_deferred_trigger()
                        continue

                    # Only read status.json when unread messages exist.
                    if not _read_anima_enabled(self._anima.anima_dir):
                        now = time.monotonic()
                        if now - self._last_disabled_skip_log >= _DISABLED_SKIP_LOG_COOLDOWN_SEC:
                            logger.info(
                                "Inbox watcher skip: anima disabled (%s); messages left unread",
                                self._anima_name,
                            )
                            self._last_disabled_skip_log = now
                        continue

                    self._pending_trigger = True
                    try:
                        spawn(self.message_triggered_inbox(), name=f"inbox-trigger-{self._anima.name}")
                    except Exception:
                        self._pending_trigger = False
                        logger.exception("Failed to start inbox processing for %s", self._anima_name)
                        self.schedule_deferred_trigger()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("Error in inbox watcher for %s", self._anima_name)
                    self.schedule_deferred_trigger()
        finally:
            if observer is not None:
                observer.stop()
                await asyncio.to_thread(observer.join, 2.0)

        logger.info("Inbox watcher stopped for %s", self._anima_name)

    def cancel_deferred_timer(self) -> None:
        """Cancel deferred trigger timer if active."""
        if self._deferred_timer is not None:
            self._deferred_timer.cancel()
            self._deferred_timer = None
