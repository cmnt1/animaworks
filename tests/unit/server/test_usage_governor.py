from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from server import usage_governor
from server.usage_governor import DEFAULT_POLICY, UsageGovernor, _classify_animas, _evaluate_time_proportional


def _write_status(
    animas_dir,
    name: str,
    credential: str,
    *,
    background_credential: str | None = None,
    background_model: str | None = None,
) -> None:
    anima_dir = animas_dir / name
    anima_dir.mkdir(parents=True, exist_ok=True)
    data = {"credential": credential}
    if background_credential is not None:
        data["background_credential"] = background_credential
    if background_model is not None:
        data["background_model"] = background_model
    (anima_dir / "status.json").write_text(json.dumps(data), encoding="utf-8")


def _write_config(data_dir, anima_names: list[str]) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "config.json").write_text(
        json.dumps({"animas": {name: {} for name in anima_names}}),
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


def test_opencode_go_month_uses_time_proportional_policy(monkeypatch):
    monkeypatch.setattr(usage_governor.time, "time", lambda: 1000.0)
    window_data = {
        "remaining": 7,
        "resets_at": 1020.0,
        "window_seconds": 100,
    }

    level, reason = _evaluate_time_proportional(
        7,
        window_data,
        DEFAULT_POLICY["providers"]["opencode_go"]["Month"],
        "opencode_go",
        "Month",
    )

    assert level == 40
    assert "opencode_go.Month remaining 7% vs time 20%" in reason
    assert "activity 40%" in reason


def test_classify_animas_maps_opencode_go(tmp_path):
    animas_dir = tmp_path / "animas"
    _write_status(animas_dir, "go-anima", "opencode-go")

    groups = _classify_animas(animas_dir, ["go-anima"])

    assert groups == {"opencode_go": ["go-anima"]}


def test_classify_animas_includes_front_and_background_providers(tmp_path):
    animas_dir = tmp_path / "animas"
    _write_status(
        animas_dir,
        "mixed-anima",
        "anthropic",
        background_credential="opencode-go",
        background_model="opencode-go/deepseek-v4-flash",
    )

    groups = _classify_animas(animas_dir, ["mixed-anima"])

    assert groups == {
        "claude": ["mixed-anima"],
        "opencode_go": ["mixed-anima"],
    }


def test_get_all_anima_names_ignores_names_outside_config_registry(tmp_path):
    data_dir = tmp_path / "data"
    animas_dir = tmp_path / "animas"
    _write_config(data_dir, ["bob"])
    _write_status(animas_dir, "alice", "anthropic")
    _write_status(animas_dir, "bob", "anthropic")

    supervisor = SimpleNamespace(processes={"alice": object(), "bob": object()})
    app = SimpleNamespace(state=SimpleNamespace(supervisor=supervisor))
    governor = UsageGovernor(app, data_dir, animas_dir)
    governor.state.suspended_animas = ["alice", "bob"]

    assert governor._get_all_anima_names() == ["bob"]


@pytest.mark.asyncio
async def test_apply_suspensions_prunes_unknown_anima_without_stopping_or_notifying(tmp_path):
    data_dir = tmp_path / "data"
    animas_dir = tmp_path / "animas"
    _write_config(data_dir, ["bob"])
    _write_status(animas_dir, "alice", "anthropic")
    _write_status(animas_dir, "bob", "anthropic")

    supervisor = SimpleNamespace(
        processes={"alice": object()},
        start_anima=AsyncMock(),
        stop_anima=AsyncMock(),
    )
    app = SimpleNamespace(state=SimpleNamespace(supervisor=supervisor))
    governor = UsageGovernor(app, data_dir, animas_dir)
    governor.state.suspended_animas = ["alice"]
    governor._notify_supervisor = AsyncMock()  # type: ignore[method-assign]

    await governor._apply_suspensions({"alice"})

    assert governor.state.suspended_animas == []
    supervisor.start_anima.assert_not_called()
    supervisor.stop_anima.assert_not_called()
    governor._notify_supervisor.assert_not_called()


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
    monkeypatch.setattr(
        "server.routes.usage_routes._fetch_opencode_go_usage",
        lambda **kwargs: {"provider": "opencode_go"},
    )

    await governor._tick(DEFAULT_POLICY)

    assert governor.state.suspended_animas == ["alice"]
    assert "claude usage unavailable" in governor.state.reason
    supervisor.start_anima.assert_not_called()
    supervisor.stop_anima.assert_not_called()


@pytest.mark.asyncio
async def test_tick_suspends_anima_when_background_provider_hits_threshold(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    animas_dir = tmp_path / "animas"
    _write_status(
        animas_dir,
        "alice",
        "anthropic",
        background_credential="opencode-go",
        background_model="opencode-go/deepseek-v4-flash",
    )

    supervisor = SimpleNamespace(
        processes={"alice": object()},
        start_anima=AsyncMock(),
        stop_anima=AsyncMock(),
    )
    app = SimpleNamespace(state=SimpleNamespace(supervisor=supervisor))
    governor = UsageGovernor(app, data_dir, animas_dir)
    governor._notify_supervisor = AsyncMock()  # type: ignore[method-assign]

    monkeypatch.setattr(
        "server.routes.usage_routes._fetch_claude_usage",
        lambda **kwargs: {
            "provider": "claude",
            "five_hour": {
                "remaining": 80,
                "resets_at": 4102444800,
                "window_seconds": 18000,
            },
            "seven_day": {
                "remaining": 80,
                "resets_at": 4102444800,
                "window_seconds": 604800,
            },
        },
    )
    monkeypatch.setattr(
        "server.routes.usage_routes._fetch_openai_usage",
        lambda **kwargs: {"provider": "openai"},
    )
    monkeypatch.setattr(
        "server.routes.usage_routes._fetch_nanogpt_usage",
        lambda **kwargs: {"provider": "nanogpt"},
    )
    monkeypatch.setattr(
        "server.routes.usage_routes._fetch_opencode_go_usage",
        lambda **kwargs: {
            "provider": "opencode_go",
            "5h": {
                "remaining": 80,
                "resets_at": 4102444800,
                "window_seconds": 18000,
            },
            "Week": {
                "remaining": 80,
                "resets_at": 4102444800,
                "window_seconds": 604800,
            },
            "Month": {
                "remaining": 10,
                "resets_at": 4102444800,
                "window_seconds": 2592000,
            },
        },
    )

    await governor._tick(DEFAULT_POLICY)

    assert governor.state.suspended_animas == ["alice"]
    supervisor.stop_anima.assert_awaited_once_with("alice")
    governor._notify_supervisor.assert_awaited_once()


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
    monkeypatch.setattr(
        "server.routes.usage_routes._fetch_opencode_go_usage",
        lambda **kwargs: {"provider": "opencode_go"},
    )

    await governor._tick(DEFAULT_POLICY)

    assert governor.state.suspended_animas == ["alice"]
    supervisor.start_anima.assert_awaited_once_with("bob")
    supervisor.stop_anima.assert_not_called()
