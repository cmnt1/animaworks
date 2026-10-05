"""Unit tests for hot-reload API endpoints."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os

from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.routes.system import create_system_router


def _create_test_app(reload_manager=None, supervisor=None) -> FastAPI:
    """Create a minimal FastAPI app with the system router."""
    app = FastAPI()

    # Set required state attributes
    app.state.anima_names = ["sakura"]
    app.state.animas_dir = MagicMock()
    app.state.shared_dir = MagicMock()
    app.state.ws_manager = MagicMock(active_connections=[])
    app.state.stream_registry = MagicMock()

    if supervisor is None:
        supervisor = MagicMock()
        supervisor.get_all_status.return_value = {}
        supervisor.is_scheduler_running.return_value = False
        supervisor.scheduler = None
    app.state.supervisor = supervisor

    if reload_manager is not None:
        app.state.reload_manager = reload_manager

    router = create_system_router()
    app.include_router(router, prefix="/api")
    return app


class TestRemovedSystemRoutes:
    def test_removed_cost_task_summary_and_duplicate_reload_routes_return_404(self):
        app = _create_test_app()
        client = TestClient(app)
        responses = [
            client.get("/api/system/cost"),
            client.get("/api/tasks/summary"),
            client.post("/api/system/hot-reload"),
            client.post("/api/system/hot-reload/animas"),
        ]
        assert [response.status_code for response in responses] == [404, 404, 404, 404]


class TestInternalSupervisorShutdownEndpoint:
    def test_mismatched_pid_does_not_stop_runners(self):
        supervisor = MagicMock(shutdown_all=AsyncMock())
        app = _create_test_app(supervisor=supervisor)
        client = TestClient(app)
        response = client.post("/api/system/internal/shutdown-supervisor", json={"expected_pid": os.getpid() + 1})
        assert response.status_code == 409
        supervisor.shutdown_all.assert_not_awaited()

    def test_remote_client_does_not_stop_runners(self):
        supervisor = MagicMock(shutdown_all=AsyncMock())
        app = _create_test_app(supervisor=supervisor)
        client = TestClient(app, client=("203.0.113.1", 12345))
        response = client.post("/api/system/internal/shutdown-supervisor", json={"expected_pid": os.getpid()})
        assert response.status_code == 403
        supervisor.shutdown_all.assert_not_awaited()

    def test_calls_supervisor_shutdown_all(self):
        supervisor = MagicMock()
        supervisor.processes = {"sakura": object(), "kanna": object()}
        supervisor.get_all_status.return_value = {}
        supervisor.is_scheduler_running.return_value = False
        supervisor.scheduler = None
        supervisor.shutdown_all = AsyncMock()
        app = _create_test_app(supervisor=supervisor)
        client = TestClient(app)

        resp = client.post("/api/system/internal/shutdown-supervisor")

        assert resp.status_code == 200
        assert resp.json() == {"status": "ok", "processes_before_shutdown": 2}
        supervisor.shutdown_all.assert_awaited_once()

    def test_returns_503_when_supervisor_missing(self):
        app = _create_test_app(supervisor=MagicMock())
        app.state.supervisor = None
        client = TestClient(app)

        resp = client.post("/api/system/internal/shutdown-supervisor")

        assert resp.status_code == 503
        assert resp.json()["status"] == "unavailable"


class TestHotReloadSlackEndpoint:
    """Tests for POST /api/system/hot-reload/slack."""

    def test_returns_503_when_no_reload_manager(self):
        app = _create_test_app()
        client = TestClient(app)
        resp = client.post("/api/system/hot-reload/slack")
        assert resp.status_code == 503

    def test_calls_reload_slack(self):
        mock_mgr = AsyncMock()
        mock_mgr.reload_slack.return_value = {
            "status": "ok", "added": [], "removed": [],
        }
        app = _create_test_app(reload_manager=mock_mgr)
        client = TestClient(app)
        resp = client.post("/api/system/hot-reload/slack")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        mock_mgr.reload_slack.assert_awaited_once()


class TestHotReloadCredentialsEndpoint:
    """Tests for POST /api/system/hot-reload/credentials."""

    def test_returns_503_when_no_reload_manager(self):
        app = _create_test_app()
        client = TestClient(app)
        resp = client.post("/api/system/hot-reload/credentials")
        assert resp.status_code == 503

    def test_calls_reload_credentials(self):
        mock_mgr = AsyncMock()
        mock_mgr.reload_credentials.return_value = {
            "status": "ok", "slack": {"status": "ok"},
        }
        app = _create_test_app(reload_manager=mock_mgr)
        client = TestClient(app)
        resp = client.post("/api/system/hot-reload/credentials")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["slack"]["status"] == "ok"
        mock_mgr.reload_credentials.assert_awaited_once()
