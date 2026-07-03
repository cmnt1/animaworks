# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for core.execution.backoff — decorrelated jitter."""

from __future__ import annotations

from core.execution.backoff import decorrelated_jitter


def test_first_backoff_within_base_and_cap() -> None:
    for _ in range(200):
        delay = decorrelated_jitter(0.0, base=5.0, cap=120.0)
        assert 5.0 <= delay <= 120.0


def test_never_exceeds_cap() -> None:
    for _ in range(200):
        delay = decorrelated_jitter(1000.0, base=5.0, cap=120.0)
        assert delay <= 120.0


def test_grows_from_previous() -> None:
    # With a larger prev the upper bound (prev*3) rises, so the sampled range
    # includes values above base.  Over many samples the max should exceed base.
    samples = [decorrelated_jitter(40.0, base=5.0, cap=120.0) for _ in range(200)]
    assert max(samples) > 5.0
    assert min(samples) >= 5.0


def test_degenerate_base_and_cap() -> None:
    # cap below base is coerced up to base; result is deterministic base.
    assert decorrelated_jitter(0.0, base=10.0, cap=1.0) == 10.0
