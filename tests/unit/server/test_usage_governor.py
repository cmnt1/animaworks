from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server import usage_governor
from server.usage_governor import DEFAULT_POLICY, UsageGovernor, _evaluate_time_proportional


def _write_status(animas_dir, name: str, credential: str) -> None:
    anima_dir = animas_dir / name
    anima_dir.mkdir(parents=True, exist_ok=True)
    (anima_dir / "status.json").write_text(
        json.dumps({"credential": credential}),
        encoding="utf-8",
    )


def test_time_proportional_room_uses_usage_remaining_over_time_remaining(monkeypatch):
    monkeypatch.setattr(usage_governor.time, "time", lambda: 1000.0)
    window_data = {
        "remaining": 37.5,
        "resets_at": 1050.0,
        "window_seconds": 100,
    }
    config = {
        "mode": "time_proportional",
        "throttle_rules": [
            {"room_under": 1, "activity_level": 100},
            {"room_under": 0.9, "activity_level": 90},
            {"room_under": 0.8, "activity_level": 80},
        ],
    }

    level, reason = _evaluate_time_proportional(
        37.5,
        window_data,
        config,
        "openai",
        "5h",
    )

    assert level == 80
    assert "room 0.75 < 0.8" in reason


def test_time_proportional_room_ratio_can_boost(monkeypatch):
    monkeypatch.setattr(usage_governor.time, "time", lambda: 1000.0)
    window_data = {
        "remaining": 70,
        "resets_at": 1020.0,
        "window_seconds": 100,
    }
    config = {
        "mode": "time_proportional",
        "throttle_rules": [
            {"room_under": 4, "activity_level": 400},
            {"room_under": 3, "activity_level": 300},
            {"room_under": 2, "activity_level": 200},
        ],
    }

    level, reason = _evaluate_time_proportional(
        70,
        window_data,
        config,
        "claude",
        "five_hour",
    )

    assert level == 400
    assert "room 3.50 < 4" in reason


def test_time_proportional_handles_zero_time_remaining_without_dividing(monkeypatch):
    monkeypatch.setattr(usage_governor.time, "time", lambda: 1000.0)
    window_data = {
        "remaining": 20,
        "resets_at": 1000.0,
        "window_seconds": 100,
    }
    config = {
        "mode": "time_proportional",
        "throttle_rules": [{"room_under": 4, "activity_level": 500}],
    }

    level, reason = _evaluate_time_proportional(
        20,
        window_data,
        config,
        "claude",
        "five_hour",
    )

    assert level is None
    assert reason == ""


def test_time_proportional_caps_activity_level_at_400(monkeypatch):
    monkeypatch.setattr(usage_governor.time, "time", lambda: 1000.0)
    window_data = {
        "remaining": 70,
        "resets_at": 1020.0,
        "window_seconds": 100,
    }
    config = {
        "mode": "time_proportional",
        "throttle_rules": [{"room_under": 4, "activity_level": 500}],
    }

    level, reason = _evaluate_time_proportional(
        70,
        window_data,
        config,
        "claude",
        "five_hour",
    )

    assert level == 400
    assert "activity 400%" in reason


@pytest.mark.asyncio
async def test_tick_keeps_suspended_anima_when_usage_fetch_fails(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    animas_dir = tmp_path / "animas"
    _write_status(animas_dir, "alice", "anthropic")

    supervisor = SimpleNamespace(
        processes={},
        start_anima=AsyncMock(),
        stop_anima=AsyncMock(),
    )
    app = SimpleNamespace(state=SimpleNamespace(supervisor=supervisor))
    governor = UsageGovernor(app, data_dir, animas_dir)
    governor.state.suspended_animas = ["alice"]
    governor.state.since = "2026-03-25T18:00:00+0900"

    monkeypatch.setattr(
        "server.routes.usage_routes._fetch_claude_usage",
        lambda **kwargs: {"error": "unauthorized", "message": "expired"},
    )
    monkeypatch.setattr(
        "server.routes.usage_routes._fetch_openai_usage",
        lambda **kwargs: {"provider": "openai"},
    )

    await governor._tick(DEFAULT_POLICY)

    assert governor.state.suspended_animas == ["alice"]
    assert "claude usage unavailable" in governor.state.reason
    supervisor.start_anima.assert_not_called()
    supervisor.stop_anima.assert_not_called()


@pytest.mark.asyncio
async def test_tick_only_keeps_suspended_animas_for_provider_with_fetch_failure(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    animas_dir = tmp_path / "animas"
    _write_status(animas_dir, "alice", "anthropic")
    _write_status(animas_dir, "bob", "openai")

    supervisor = SimpleNamespace(
        processes={},
        start_anima=AsyncMock(),
        stop_anima=AsyncMock(),
    )
    app = SimpleNamespace(state=SimpleNamespace(supervisor=supervisor))
    governor = UsageGovernor(app, data_dir, animas_dir)
    governor.state.suspended_animas = ["alice", "bob"]

    monkeypatch.setattr(
        "server.routes.usage_routes._fetch_claude_usage",
        lambda **kwargs: {"error": "rate_limited", "message": "retry shortly"},
    )
    monkeypatch.setattr(
        "server.routes.usage_routes._fetch_openai_usage",
        lambda **kwargs: {
            "provider": "openai",
            "5h": {
                "remaining": 80,
                "resets_at": 4102444800,
                "window_seconds": 18000,
            },
            "Week": {
                "remaining": 85,
                "resets_at": 4102444800,
                "window_seconds": 604800,
            },
        },
    )

    await governor._tick(DEFAULT_POLICY)

    assert governor.state.suspended_animas == ["alice"]
    supervisor.start_anima.assert_awaited_once_with("bob")
    supervisor.stop_anima.assert_not_called()
