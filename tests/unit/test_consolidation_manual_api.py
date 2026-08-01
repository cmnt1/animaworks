"""Unit tests for manual consolidation API endpoints."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

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
    supervisor.start_system_consolidation = MagicMock(
        return_value={"started": True, "job_type": "daily"},
    )
    supervisor.start_missed_system_consolidations = MagicMock(
        return_value={"started": True},
    )

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


class TestConsolidationModelEndpoint:
    def test_updates_configured_model(self, client):
        config = SimpleNamespace(
            consolidation=SimpleNamespace(llm_model="old/model", llm_credential="")
        )
        with (
            patch("core.config.models.load_config", return_value=config),
            patch("core.config.models.save_config") as save_config,
        ):
            resp = client.put(
                "/api/system/consolidation/model",
                json={"model": "google/gemini-2.5-flash", "credential": "google"},
            )

        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "model": "google/gemini-2.5-flash",
            "credential": "google",
        }
        assert config.consolidation.llm_model == "google/gemini-2.5-flash"
        assert config.consolidation.llm_credential == "google"
        save_config.assert_called_once_with(config)

    def test_rejects_empty_model(self, client):
        resp = client.put(
            "/api/system/consolidation/model",
            json={"model": "   ", "credential": "codex"},
        )

        assert resp.status_code == 400


class TestRunEndpoint:
    def test_starts_job(self, client):
        resp = client.post("/api/system/consolidation/daily/run")
        assert resp.status_code == 200
        data = resp.json()
        assert data["started"] is True
        assert data["job_type"] == "daily"
        client.app.state.supervisor.start_system_consolidation.assert_called_once_with("daily")

    def test_invalid_job_type(self, client):
        resp = client.post("/api/system/consolidation/invalid/run")
        assert resp.status_code == 400

    def test_409_when_running(self, client):
        client.app.state.supervisor.start_system_consolidation.return_value = {
            "error": "already_running",
            "job_type": "daily",
        }

        resp = client.post("/api/system/consolidation/daily/run")
        assert resp.status_code == 409
        assert "already_running" in resp.json()["error"]


class TestCatchupEndpoint:
    def test_starts_catchup(self, client):
        resp = client.post("/api/system/consolidation/catchup")
        assert resp.status_code == 200
        assert resp.json()["started"] is True
        client.app.state.supervisor.start_missed_system_consolidations.assert_called_once_with()

    def test_409_when_job_running(self, client):
        client.app.state.supervisor.start_missed_system_consolidations.return_value = {
            "error": "already_running",
            "job_type": "weekly",
        }

        resp = client.post("/api/system/consolidation/catchup")
        assert resp.status_code == 409


class TestShortcutEndpoint:
    def test_redirects_to_scheduler(self, client):
        resp = client.get(
            "/api/system/consolidation/daily/run",
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/#/scheduler"
