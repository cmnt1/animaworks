# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for the unified RestartController state machine.

The controller is pure logic (asyncio-independent) with injectable clocks so
time can be advanced deterministically.
"""

from __future__ import annotations

from server.supervisor.restart_state import RestartController, RestartPhase


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class FakeWall:
    def __init__(self) -> None:
        self.t = 1_700_000_000.0

    def __call__(self) -> float:
        return self.t


def make_controller(**kwargs) -> tuple[RestartController, FakeClock]:
    clock = FakeClock()
    defaults = dict(
        failed_threshold=3,
        base_delay_sec=30.0,
        max_delay_sec=1800.0,
        stable_reset_sec=300.0,
        clock=clock,
        wall_clock=FakeWall(),
    )
    defaults.update(kwargs)
    return RestartController(**defaults), clock


def test_phases_progress_to_failed_after_threshold():
    ctl, _ = make_controller(failed_threshold=3)
    assert ctl.record_failure("a", "e1") == 30.0
    assert ctl.get("a").phase is RestartPhase.BACKOFF
    assert ctl.record_failure("a", "e2") == 60.0
    assert ctl.get("a").phase is RestartPhase.BACKOFF
    assert ctl.record_failure("a", "e3") == 120.0
    assert ctl.get("a").phase is RestartPhase.FAILED
    assert ctl.is_failed("a")


def test_delay_sequence_caps_at_max():
    ctl, _ = make_controller(base_delay_sec=30.0, max_delay_sec=1800.0, failed_threshold=100)
    deltas = [ctl.record_failure("a", f"e{i}") for i in range(9)]
    assert deltas == [30, 60, 120, 240, 480, 960, 1800, 1800, 1800]


def test_failed_still_becomes_due_for_auto_recovery():
    ctl, clock = make_controller(failed_threshold=3, base_delay_sec=30.0, max_delay_sec=1800.0)
    ctl.record_failure("a", "e1")
    ctl.record_failure("a", "e2")
    ctl.record_failure("a", "e3")
    assert ctl.is_failed("a")
    assert not ctl.is_due("a")
    assert ctl.seconds_until_due("a") > 0
    # advance past the capped backoff -> due again (auto-recovery continues)
    clock.advance(1800.0 + 1.0)
    assert ctl.is_due("a")
    assert ctl.seconds_until_due("a") == 0


def test_record_started_keeps_attempts_then_stable_resets():
    ctl, clock = make_controller(stable_reset_sec=300.0, failed_threshold=3)
    ctl.record_failure("a", "e1")
    ctl.record_failure("a", "e2")
    assert ctl.get("a").attempts == 2

    # Immediate restart after record_started continues counting from 2.
    ctl.record_started("a")
    assert ctl.get("a").phase is RestartPhase.HEALTHY
    clock.advance(1.0)
    ctl.record_failure("a", "e3")
    assert ctl.get("a").attempts == 3
    assert ctl.is_failed("a")

    # A stable uptime resets attempts back to 0.
    ctl.record_stable("a", 300.0)
    assert ctl.get("a").attempts == 0
    assert ctl.get("a").last_error is None

    # Below stable threshold does not reset.
    ctl.record_failure("a", "e4")
    ctl.record_stable("a", 10.0)
    assert ctl.get("a").attempts == 1


def test_reset_and_forget_remove_record():
    ctl, _ = make_controller()
    ctl.record_failure("a", "e1")
    assert ctl.get("a") is not None
    ctl.reset("a")
    assert ctl.get("a") is None
    ctl.record_failure("a", "e1")
    ctl.forget("a")
    assert ctl.get("a") is None
    assert ctl.snapshot("a")["restart_state"] == "healthy"


def test_should_log_failed_throttles_interval():
    ctl, clock = make_controller()
    ctl.record_failure("a", "e1")
    ctl.record_failure("a", "e2")
    ctl.record_failure("a", "e3")
    assert ctl.should_log_failed("a") is True
    # within 300s -> suppressed
    clock.advance(100.0)
    assert ctl.should_log_failed("a") is False
    # after 300s -> allowed again
    clock.advance(300.0)
    assert ctl.should_log_failed("a") is True
    # non-failed record -> never logs
    ctl.record_started("a")
    assert ctl.should_log_failed("a") is False


def test_snapshot_shape():
    ctl, _ = make_controller(failed_threshold=2)
    ctl.record_failure("a", "boom")
    snap = ctl.snapshot("a")
    assert snap["restart_state"] == "backoff"
    assert snap["restart_count"] == 1
    assert snap["last_error"] == "boom"
    assert "T" in snap["next_retry_at"]  # ISO8601
    ctl.record_failure("a", "boom2")
    snap = ctl.snapshot("a")
    assert snap["restart_state"] == "failed"
    assert snap["last_error"] == "boom2"
