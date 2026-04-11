"""Unit tests for manual consolidation API endpoints."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

JST = timezone(timedelta(hours=9))


@pytest.fixture()
def status_dir(tmp_path):
    """Patch _status_path for all tests."""
    status_file = tmp_path / "shared" / "system" / "consolidation_status.json"
    with patch("core.lifecycle.system_status._status_path", return_value=status_file):
        yield status_file


@pytest.fixture()
def client(status_dir):
    """Create a test client with a mocked supervisor."""
    from server.routes.system import create_system_router

    app = FastAPI()
    router = create_system_router()
    app.include_router(router, prefix="/api")

    # Mock supervisor
    supervisor = MagicMock()
    supervisor.get_system_consolidation_status = MagicMock(return_value={
        "daily": {"last_status": "never", "running": False, "missed": True},
        "weekly": {"last_status": "never", "running": False, "missed": False},
        "monthly": {"last_status": "never", "running": False, "missed": False},
    })
    supervisor.run_system_consolidation_now = AsyncMock(return_value={"started": True})
    supervisor.run_missed_system_consolidations = AsyncMock(return_value={"ran": ["daily"]})

    app.state.supervisor = supervisor

    return TestClient(app)


class TestConsolidationStatusEndpoint:
    def test_returns_status(self, client):
        resp = client.get("/api/system/consolidation/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "daily" in data
        assert "weekly" in data
        assert "monthly" in data


class TestRunEndpoint:
    def test_starts_job(self, client):
        resp = client.post("/api/system/consolidation/daily/run")
        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] is True
        assert data["job_type"] == "daily"

    def test_invalid_job_type(self, client):
        resp = client.post("/api/system/consolidation/invalid/run")
        assert resp.status_code == 400

    def test_409_when_running(self, client, status_dir):
        from core.lifecycle.system_status import mark_started

        mark_started("daily")

        resp = client.post("/api/system/consolidation/daily/run")
        assert resp.status_code == 409
        assert "already_running" in resp.json()["error"]


class TestCatchupEndpoint:
    def test_starts_catchup(self, client):
        resp = client.post("/api/system/consolidation/catchup")
        assert resp.status_code == 200
        assert resp.json()["started"] is True

    def test_409_when_job_running(self, client, status_dir):
        from core.lifecycle.system_status import mark_started

        mark_started("weekly")

        resp = client.post("/api/system/consolidation/catchup")
        assert resp.status_code == 409
