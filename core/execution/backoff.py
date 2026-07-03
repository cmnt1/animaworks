# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Backoff timing helpers for coordinated LLM retry.

Decorrelated jitter spreads retries across processes so a shared credential is
not hammered in lockstep after a 429.  Kept as a pure function for testability;
callers seed ``prev`` with the previous delay (or ``0`` for the first retry).
"""

from __future__ import annotations

import random


def decorrelated_jitter(prev: float, base: float = 5.0, cap: float = 120.0) -> float:
    """Return the next decorrelated-jitter backoff delay in seconds.

    Uses the AWS "decorrelated jitter" recurrence
    ``sleep = min(cap, uniform(base, prev * 3))``.  The first call should pass
    ``prev=0`` (or ``prev=base``); the result is always within ``[base, cap]``.

    Args:
        prev: The previous backoff delay in seconds.
        base: Lower bound / initial delay in seconds.
        cap: Maximum delay in seconds.
    """
    if base <= 0:
        base = 0.0
    if cap < base:
        cap = base
    upper = max(prev, base) * 3.0
    if upper < base:
        upper = base
    return min(cap, random.uniform(base, upper))


__all__ = ["decorrelated_jitter"]
