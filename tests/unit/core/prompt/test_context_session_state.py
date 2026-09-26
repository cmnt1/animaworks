"""Regression tests for resumed-session context tracking."""

from __future__ import annotations

import logging
from unittest.mock import patch

from core.prompt.context import ContextTracker

_PATCH_TARGET = "core.config.model_mode._match_models_json"


def _tracker(**kwargs: object) -> ContextTracker:
    with patch(_PATCH_TARGET, return_value={"mode": "S", "context_window": 200_000}):
        return ContextTracker(model="claude-sonnet-4-20250514", **kwargs)


def test_resumed_baseline_triggers_on_real_context_growth() -> None:
    tracker = _tracker(baseline_tokens=30_000, absolute_ceiling=0.95)

    assert tracker.update_from_usage({"input_tokens": 150_000}) is True
    assert tracker.threshold_exceeded is True
    assert tracker.baseline_tokens == 30_000


def test_implicit_baseline_retains_legacy_behavior() -> None:
    tracker = _tracker(absolute_ceiling=0.95)

    tracker.update_from_usage({"input_tokens": 30_000})
    assert tracker.baseline_tokens == 30_000
    tracker.update_from_usage({"input_tokens": 40_000})
    assert tracker.baseline_tokens == 30_000


def test_absolute_ceiling_wins_when_fill_is_below_threshold(caplog) -> None:
    tracker = _tracker(threshold=0.80, baseline_tokens=30_000, absolute_ceiling=0.70)

    with caplog.at_level(logging.WARNING, logger="animaworks.context_tracker"):
        assert tracker.update_from_usage({"input_tokens": 150_000}) is True

    assert tracker.fill_ratio < tracker.threshold
    assert "rule=ceiling" in caplog.text


def test_measurement_does_not_reseed_explicit_baseline() -> None:
    tracker = _tracker(baseline_tokens=30_000, absolute_ceiling=0.99)

    tracker.update_from_usage({"input_tokens": 40_000})
    tracker.update_from_usage({"input_tokens": 50_000})

    assert tracker.baseline_tokens == 30_000
