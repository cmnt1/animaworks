"""Unified restart state machine for ProcessSupervisor.

Consolidates the previous four scattered counter families (health retries,
respawn-transaction retries, FAILED recovery cooldown, start-failure
cooldown) into a single, pure (asyncio-independent) state machine.

Design goals (user decision 2026-09-27):
- After ``failed_threshold`` consecutive failures, surface FAILED in the UI.
- Even after FAILED, keep attempting automatic recovery with exponential
  backoff (capped by ``max_delay_sec``) rather than parking the anima for
  manual intervention.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class RestartPhase(StrEnum):
    HEALTHY = "healthy"
    BACKOFF = "backoff"
    FAILED = "failed"


@dataclass
class RestartRecord:
    """Per-anima restart state.

    ``next_attempt_at`` is in monotonic clock (for ``is_due`` /
    ``seconds_until_due``), while ``next_attempt_wall`` is in epoch
    seconds (for API/UI display of the next retry time).
    """

    attempts: int = 0
    phase: RestartPhase = RestartPhase.HEALTHY
    next_attempt_at: float | None = None  # monotonic
    next_attempt_wall: float | None = None  # epoch seconds (API)
    last_error: str | None = None
    failed_since: float | None = None  # monotonic
    last_failed_log_at: float = float("-inf")  # monotonic; -inf = never logged

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"RestartRecord(attempts={self.attempts}, phase={self.phase.value}, "
            f"next_attempt_at={self.next_attempt_at}, last_error={self.last_error!r})"
        )


class RestartController:
    """Pure restart-state logic. Injects ``clock``/``wall_clock`` for tests."""

    def __init__(
        self,
        *,
        failed_threshold: int,
        base_delay_sec: float,
        max_delay_sec: float,
        stable_reset_sec: float,
        clock=time.monotonic,
        wall_clock=time.time,
    ):
        self.failed_threshold = max(1, int(failed_threshold))
        self.base_delay_sec = base_delay_sec
        self.max_delay_sec = max_delay_sec
        self.stable_reset_sec = stable_reset_sec
        self._clock = clock
        self._wall_clock = wall_clock
        self._records: dict[str, RestartRecord] = {}

    # ── Mutations ────────────────────────────────────────────────

    def record_failure(self, name: str, reason: str) -> float:
        """Record a failed restart attempt. Returns the next backoff delay."""
        rec = self._records.setdefault(name, RestartRecord())
        rec.attempts += 1
        delay = min(self.base_delay_sec * (2 ** (rec.attempts - 1)), self.max_delay_sec)
        now = self._clock()
        rec.next_attempt_at = now + delay
        rec.next_attempt_wall = self._wall_clock() + delay
        if rec.attempts >= self.failed_threshold:
            if rec.phase is not RestartPhase.FAILED:
                rec.failed_since = now
            rec.phase = RestartPhase.FAILED
        else:
            rec.phase = RestartPhase.BACKOFF
        rec.last_error = reason
        return delay

    def record_started(self, name: str) -> None:
        """Record a successful start. Attempts are retained (not reset)."""
        rec = self._records.setdefault(name, RestartRecord())
        rec.phase = RestartPhase.HEALTHY
        rec.next_attempt_at = None
        rec.next_attempt_wall = None

    def record_stable(self, name: str, uptime_sec: float) -> None:
        """Reset attempts after a stable uptime, per ``stable_reset_sec``."""
        rec = self._records.get(name)
        if rec is None:
            return
        if uptime_sec >= self.stable_reset_sec:
            rec.attempts = 0
            rec.last_error = None

    def reset(self, name: str) -> None:
        """Remove the record (manual restart / enable / RAG repair success)."""
        self._records.pop(name, None)

    def forget(self, name: str) -> None:
        """Remove the record (disabled / anima removed)."""
        self._records.pop(name, None)

    # ── Queries ─────────────────────────────────────────────────

    def is_failed(self, name: str) -> bool:
        rec = self._records.get(name)
        return bool(rec and rec.phase is RestartPhase.FAILED)

    def is_due(self, name: str) -> bool:
        rec = self._records.get(name)
        if rec is None or rec.next_attempt_at is None:
            return True
        return self._clock() >= rec.next_attempt_at

    def seconds_until_due(self, name: str) -> float:
        rec = self._records.get(name)
        if rec is None or rec.next_attempt_at is None:
            return 0.0
        return max(0.0, rec.next_attempt_at - self._clock())

    def get(self, name: str) -> RestartRecord | None:
        return self._records.get(name)

    def names(self) -> set[str]:
        return set(self._records)

    def should_log_failed(self, name: str, interval_sec: float = 300.0) -> bool:
        """Throttle repeated FAILED warnings to once per ``interval_sec``."""
        rec = self._records.get(name)
        if rec is None or rec.phase is not RestartPhase.FAILED:
            return False
        now = self._clock()
        if now - rec.last_failed_log_at >= interval_sec:
            rec.last_failed_log_at = now
            return True
        return False

    def snapshot(self, name: str) -> dict:
        """Return the API-facing status blend for ``get_process_status``."""
        rec = self._records.get(name)
        if rec is None:
            return {
                "restart_state": RestartPhase.HEALTHY.value,
                "restart_count": 0,
                "next_retry_at": None,
                "last_error": None,
            }
        next_retry_at = None
        if rec.next_attempt_wall is not None:
            next_retry_at = datetime.fromtimestamp(rec.next_attempt_wall, tz=UTC).isoformat()
        return {
            "restart_state": rec.phase.value,
            "restart_count": rec.attempts,
            "next_retry_at": next_retry_at,
            "last_error": rec.last_error,
        }
