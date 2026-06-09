"""
Health check mixin for ProcessSupervisor.
"""

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime as _dt
from pathlib import Path
from typing import Any

from core.supervisor.process_handle import ProcessHandle, ProcessState
from core.time_utils import ensure_aware, now_local

logger = logging.getLogger(__name__)


class HealthMixin:
    """Health-check loop, failure handling, and hang detection."""

    def is_bootstrapping(self, anima_name: str) -> bool:
        """Return True if the anima is currently in bootstrap mode."""
        return anima_name in getattr(self, "_bootstrapping", set())

    def is_consolidating(self, anima_name: str) -> bool:
        """Return True if the anima is currently running daily/weekly consolidation."""
        return anima_name in getattr(self, "_consolidating", set())

    def _busy_sidecar_path(self, anima_name: str) -> Path | None:
        """Return the IPC-independent busy marker path, if run_dir is available."""
        run_dir = getattr(self, "run_dir", None)
        if run_dir is None:
            return None
        return Path(run_dir) / "animas" / f"{anima_name}.busy.json"

    def _read_busy_sidecar(self, anima_name: str, handle: ProcessHandle) -> dict[str, Any] | None:
        """Read a child-written busy marker for ping-timeout fallback.

        The marker is trusted only when it names the current child PID.  This
        prevents stale files from a killed/restarted process from suppressing
        real hang recovery.
        """
        path = self._busy_sidecar_path(anima_name)
        if path is None or not path.exists():
            return None

        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or not data.get("is_busy"):
            return None

        marker_pid = data.get("pid")
        current_pid = handle.get_pid()
        if marker_pid is None or current_pid is None:
            return None
        try:
            if int(marker_pid) != int(current_pid):
                return None
        except (TypeError, ValueError):
            return None

        last_progress = data.get("last_progress_at") or data.get("updated_at")
        if last_progress:
            data["last_progress_at"] = last_progress
        return data

    def _handle_busy_health(
        self,
        anima_name: str,
        handle: ProcessHandle,
        *,
        last_progress_iso: Any,
    ) -> None:
        """Apply progress-aware hang detection for a known-busy process."""
        handle.stats.missed_pings = 0
        # Skip hang detection during bootstrap (LLM may take a long time)
        if self.is_bootstrapping(anima_name):
            logger.debug(
                "Skipping hang detection for %s (bootstrapping)",
                anima_name,
            )
            return
        # Skip hang detection during daily/weekly consolidation
        if self.is_consolidating(anima_name):
            logger.debug(
                "Skipping hang detection for %s (consolidating)",
                anima_name,
            )
            return
        if last_progress_iso:
            try:
                last_progress = ensure_aware(_dt.fromisoformat(str(last_progress_iso)))
            except (ValueError, TypeError):
                logger.warning(
                    "Invalid last_progress_at from %s: %r",
                    anima_name,
                    last_progress_iso,
                )
                last_progress = None

            if last_progress is not None:
                idle_sec = (now_local() - last_progress).total_seconds()
                if idle_sec > self.health_config.busy_hang_threshold_sec:
                    logger.error(
                        "Process busy hang (no progress): %s (idle=%.0fs > %ds)",
                        anima_name,
                        idle_sec,
                        int(self.health_config.busy_hang_threshold_sec),
                    )
                    asyncio.create_task(self._handle_process_hang(anima_name, handle))
                return
        if handle.stats.last_busy_since is None:
            handle.stats.last_busy_since = now_local()
        busy_duration = (now_local() - handle.stats.last_busy_since).total_seconds()
        if busy_duration > self.health_config.busy_hang_threshold_sec:
            logger.error(
                "Process busy hang (no progress info, fallback): %s (busy=%.0fs > %ds)",
                anima_name,
                busy_duration,
                int(self.health_config.busy_hang_threshold_sec),
            )
            asyncio.create_task(self._handle_process_hang(anima_name, handle))

    async def _health_check_loop(self) -> None:
        """Periodically pings all processes and handles failures."""
        logger.info("Health check loop started")

        while not self._shutdown:
            try:
                await asyncio.sleep(self.health_config.ping_interval_sec)

                # Poll and broadcast child process events
                await self._poll_anima_events()

                await self._poll_requested_rag_repairs()

                # Check all processes in parallel
                checks = [
                    self._check_process_health(anima_name, handle)
                    for anima_name, handle in list(self.processes.items())
                ]
                await asyncio.gather(*checks, return_exceptions=True)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in health check loop: %s", e)

        logger.info("Health check loop stopped")

    async def _check_process_health(
        self,
        anima_name: str,
        handle: ProcessHandle,
    ) -> None:
        """Check health of a single process."""
        # Skip permanently failed processes (log at WARNING every 5 minutes)
        if anima_name in self._permanently_failed:
            now = asyncio.get_running_loop().time()
            last_log = self._failed_log_times.get(anima_name, 0)
            if now - last_log >= 300:
                logger.warning(
                    "Process still in FAILED state: %s (awaiting reconciliation recovery)",
                    anima_name,
                )
                self._failed_log_times[anima_name] = now
            return

        # Detect handles stuck in STOPPING state (e.g. after failed shutdown)
        if handle.state == ProcessState.STOPPING:
            if not handle.stopping_since:
                return
            stopping_duration = (now_local() - ensure_aware(handle.stopping_since)).total_seconds()
            if stopping_duration > 30:
                logger.error(
                    "Process stuck in STOPPING state: %s (%.0fs)",
                    anima_name,
                    stopping_duration,
                )
                handle.state = ProcessState.FAILED
                asyncio.create_task(self._handle_process_failure(anima_name, handle))
            return

        # RESTARTING 状態ならヘルスチェックをスキップ
        if handle.state == ProcessState.RESTARTING:
            return

        # During streaming: skip ping (IPC lock held) but still check
        # process liveness and streaming duration timeout.
        if handle.is_streaming:
            # Detect process death during streaming
            if handle.state == ProcessState.FAILED:
                logger.error(
                    "Process FAILED during streaming: %s",
                    anima_name,
                )
                asyncio.create_task(self._handle_process_failure(anima_name, handle))
                return
            if not handle.is_alive():
                logger.error(
                    "Process died during streaming: %s (exit_code=%s)",
                    anima_name,
                    handle.stats.exit_code,
                )
                asyncio.create_task(self._handle_process_failure(anima_name, handle))
                return
            # Streaming duration timeout
            started_at = handle.streaming_started_at
            if started_at is not None:
                streaming_sec = (now_local() - ensure_aware(started_at)).total_seconds()
                if streaming_sec > self._max_streaming_duration_sec:
                    logger.error(
                        "Streaming timeout for %s (%.0fs > %ds)",
                        anima_name,
                        streaming_sec,
                        self._max_streaming_duration_sec,
                    )
                    asyncio.create_task(self._handle_process_hang(anima_name, handle))
            return

        # Skip if in startup grace period
        uptime = (now_local() - ensure_aware(handle.stats.started_at)).total_seconds()
        if uptime < self.health_config.startup_grace_sec:
            logger.debug("Skipping health check for %s (startup grace)", anima_name)
            return

        # Reset restart counter after stable uptime
        if uptime > self.restart_policy.reset_after_sec:
            if self._restart_counts.get(anima_name, 0) > 0:
                self._restart_counts[anima_name] = 0
                logger.info(
                    "Restart counter reset for %s (stable for %.0fs)",
                    anima_name,
                    uptime,
                )

        # Direct state check: detect IPC connection loss
        if handle.state == ProcessState.FAILED:
            logger.error(
                "Process in FAILED state (IPC connection lost): %s",
                anima_name,
            )
            asyncio.create_task(self._handle_process_failure(anima_name, handle))
            return

        # Check if process is alive
        if not handle.is_alive():
            actual_rc = handle.process.returncode if handle.process else None
            handle.stats.exit_code = actual_rc
            logger.error(
                "Process exited unexpectedly: %s (exit_code=%s, signal=%s)",
                anima_name,
                actual_rc,
                -actual_rc if actual_rc is not None and actual_rc < 0 else "N/A",
            )
            asyncio.create_task(self._handle_process_failure(anima_name, handle))
            return

        # Ping process
        ping_result = await handle.ping(
            timeout=self.health_config.ping_timeout_sec,
            return_details=True,
        )
        success = bool(ping_result.get("success"))
        is_busy = bool(ping_result.get("is_busy"))

        # Transport error fallback (Windows IPC): don't count as missed ping
        if not success and ping_result.get("transport_error"):
            if handle.is_alive():
                handle.stats.missed_pings = 0
                if not getattr(handle, "_transport_error_logged", False):
                    logger.warning(
                        "IPC transport unavailable for %s — falling back to liveness check only",
                        anima_name,
                    )
                    handle._transport_error_logged = True  # type: ignore[attr-defined]
                return
            # Process dead despite transport error
            actual_rc = handle.process.returncode if handle.process else None
            handle.stats.exit_code = actual_rc
            logger.error(
                "Process dead with transport error: %s (exit_code=%s)",
                anima_name,
                actual_rc,
            )
            asyncio.create_task(self._handle_process_failure(anima_name, handle))
            return

        if success:
            if is_busy:
                self._handle_busy_health(
                    anima_name,
                    handle,
                    last_progress_iso=ping_result.get("last_progress_at"),
                )
                return

            if handle.stats.missed_pings > 0 or handle.stats.last_busy_since is not None:
                logger.info("Process recovered: %s", anima_name)
            handle.stats.last_busy_since = None
            return

        # Ping failed
        busy_sidecar = self._read_busy_sidecar(anima_name, handle)
        if busy_sidecar is not None:
            logger.debug(
                "Ping failed for %s, but busy sidecar is present; using progress-aware health check",
                anima_name,
            )
            self._handle_busy_health(
                anima_name,
                handle,
                last_progress_iso=busy_sidecar.get("last_progress_at"),
            )
            return

        handle.stats.last_busy_since = None
        logger.warning(
            "Health check failed: %s (missed=%d/%d)",
            anima_name,
            handle.stats.missed_pings,
            self.health_config.max_missed_pings,
        )

        # Check if hang threshold exceeded
        if handle.stats.missed_pings >= self.health_config.max_missed_pings:
            logger.error(
                "Process hang detected: %s (PID %s)",
                anima_name,
                handle.get_pid(),
            )
            asyncio.create_task(self._handle_process_hang(anima_name, handle))

    async def _handle_process_failure(
        self,
        anima_name: str,
        handle: ProcessHandle,
    ) -> None:
        """Handle process exit/crash.

        Runs as an independent task so the health-check loop is not blocked
        by backoff sleeps.  A per-anima guard prevents duplicate restarts.
        """
        if anima_name in self._restarting:
            return
        self._restarting.add(anima_name)

        # リスタート中であることをハンドルに反映
        handle.state = ProcessState.RESTARTING

        try:
            # Check restart count (supervisor-level, survives handle recreation)
            count = self._restart_counts.get(anima_name, 0)
            if count >= self.restart_policy.max_retries:
                logger.error(
                    "Max restart retries exceeded for %s. Manual intervention required.",
                    anima_name,
                )
                handle.state = ProcessState.FAILED
                self._permanently_failed.add(anima_name)
                self._failed_log_times[anima_name] = asyncio.get_running_loop().time()
                return

            repaired = await self._maybe_repair_rag_before_restart(anima_name, handle)
            if repaired:
                count = 0

            # Calculate backoff delay
            backoff = min(
                self.restart_policy.backoff_base_sec * (2**count),
                self.restart_policy.backoff_max_sec,
            )

            logger.info(
                "Scheduling restart for %s (retry %d/%d, delay=%.1fs)",
                anima_name,
                count + 1,
                self.restart_policy.max_retries,
                backoff,
            )

            # Wait and restart
            await asyncio.sleep(backoff)

            self._restart_counts[anima_name] = count + 1
            await self.restart_anima(anima_name, _reset_counters=False)

            new_handle = self.processes.get(anima_name)
            if new_handle:
                logger.info(
                    "Process restarted: %s (PID %s, retry=%d/%d)",
                    anima_name,
                    new_handle.get_pid(),
                    count + 1,
                    self.restart_policy.max_retries,
                )
            else:
                logger.error(
                    "Restart completed but no handle found: %s",
                    anima_name,
                )

        except Exception as e:
            logger.error("Failed to restart %s: %s", anima_name, e)
            handle.state = ProcessState.FAILED
        finally:
            self._restarting.discard(anima_name)

    async def _handle_process_hang(
        self,
        anima_name: str,
        handle: ProcessHandle,
    ) -> None:
        """Handle hung process (kill and restart)."""
        logger.warning("Killing hung process: %s", anima_name)

        # Kill process
        await handle.kill()

        # Restart
        await self._handle_process_failure(anima_name, handle)

    # ── Reconciliation helper ────────────────────────────────────

    @staticmethod
    def read_anima_enabled(anima_dir: Path) -> bool:
        """Read the enabled flag from an anima's status.json.

        Returns True (enabled) when:
        - status.json does not exist (backward compatibility)
        - status.json exists with ``enabled: true``

        Returns False when status.json exists with ``enabled: false``.
        """
        status_file = anima_dir / "status.json"
        if not status_file.exists():
            return True  # Backward compatibility: no file = enabled
        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
            return bool(data.get("enabled", True))
        except (json.JSONDecodeError, OSError):
            return True  # Treat unreadable file as enabled
