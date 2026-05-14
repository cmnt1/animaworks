# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""E2E tests for semantic workspace replay API."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from tests.e2e.test_replay_feature_e2e import _create_app, _setup_anima, _write_activity


async def test_semantic_replay_api_returns_projected_events(tmp_path: Path) -> None:
    """Semantic replay returns meaningful events instead of raw tool_result rows."""
    animas_dir = tmp_path / "animas"
    _setup_anima(animas_dir, "sumire")
    now = datetime.now(UTC)
    entries = [
        {
            "ts": (now - timedelta(minutes=4)).isoformat(),
            "type": "message_received",
            "summary": "Please review implementation",
            "content": "Please review implementation",
            "from": "admin",
            "meta": {"from_type": "human", "task_id": "task-42"},
        },
        {
            "ts": (now - timedelta(minutes=3)).isoformat(),
            "type": "tool_use",
            "summary": "Implementation review requested",
            "tool": "delegate_task",
            "to": "rin",
            "meta": {"tool_use_id": "tu-42", "task_id": "task-42"},
        },
        {
            "ts": (now - timedelta(minutes=2)).isoformat(),
            "type": "tool_result",
            "content": "queued",
            "tool": "delegate_task",
            "meta": {"tool_use_id": "tu-42"},
        },
        {
            "ts": (now - timedelta(minutes=1)).isoformat(),
            "type": "response_sent",
            "summary": "Review has been delegated",
            "content": "Review has been delegated",
        },
    ]
    _write_activity(animas_dir, "sumire", entries)
    app = _create_app(tmp_path, anima_names=["sumire"])
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/activity/recent?hours=12&limit=10&offset=0&replay=true&grouped=true&semantic=true"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["raw_total"] == 4
    assert data["total_groups"] == 1
    assert data["total"] >= 3
    assert data["has_more"] is False

    required = {
        "id",
        "ts",
        "actor",
        "target",
        "kind",
        "label",
        "summary",
        "importance",
        "group_id",
        "group_type",
        "status",
        "source_event_ids",
        "raw_event_count",
        "line_type",
        "channel",
        "tool",
        "debug",
    }
    for event in data["events"]:
        assert set(event) == required
        assert event["group_id"] == "task:task-42"
        assert event["kind"] != "tool_result"

    delegation = next(event for event in data["events"] if event["kind"] == "delegation")
    assert delegation["tool"] == "delegate_task"
    assert delegation["target"] == "rin"
    assert len(delegation["source_event_ids"]) == 2
    assert delegation["debug"]["suppressed_count"] == 1
    assert "tool_result" in delegation["debug"]["source_types"]


async def test_semantic_replay_api_rejects_invalid_modes(tmp_path: Path) -> None:
    """semantic=true is valid only for replay grouped mode."""
    _setup_anima(tmp_path / "animas", "sumire")
    app = _create_app(tmp_path, anima_names=["sumire"])
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        no_group = await client.get("/api/activity/recent?replay=true&semantic=true")
        no_replay = await client.get("/api/activity/recent?grouped=true&semantic=true")

    assert no_group.status_code == 400
    assert no_group.json()["error"] == "semantic replay requires grouped=true"
    assert no_replay.status_code == 400
    assert no_replay.json()["error"] == "semantic replay requires replay=true"
