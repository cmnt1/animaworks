# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Tests for privacy-preserving enclave fields in the system status API."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.config import invalidate_cache
from server.routes import system as system_routes
from tests.helpers.filesystem import DEFAULT_TEST_CONFIG


def _write_config(data_dir: Path) -> None:
    config: dict[str, Any] = dict(DEFAULT_TEST_CONFIG)
    config["enclave"] = {
        "enabled": True,
        "name": "isolated",
        "socket_path": "/run/animaworks-enclave/isolated.sock",
        "socket_group": "animaworks-enclave",
    }
    config["enclaves"] = {
        "saas-data": {
            "socket_path": "/run/animaworks-enclave/saas-data.sock",
            "allowed_animas": ["host-assistant"],
        }
    }
    (data_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
    invalidate_cache()


def _make_app() -> FastAPI:
    app = FastAPI()
    app.state.anima_names = []
    supervisor = MagicMock()
    supervisor.get_all_status.return_value = {}
    supervisor.is_scheduler_running.return_value = False
    app.state.supervisor = supervisor
    app.include_router(system_routes.create_system_router(), prefix="/api")
    return app


async def test_system_status_contains_enclave_metadata_only(
    data_dir: Path,
    monkeypatch,
) -> None:
    _write_config(data_dir)
    today = datetime.now(UTC).strftime("%Y%m%d")
    audit_dir = data_dir / "enclave" / "audit" / "egress"
    audit_dir.mkdir(parents=True)
    secret_body = "private-question-and-answer-body"
    (audit_dir / f"{today}.jsonl").write_text(
        json.dumps({"blocked": False, "input_facts": [{"fact": secret_body}]})
        + "\n"
        + json.dumps({"blocked": True, "output_facts": None})
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        system_routes,
        "check_gateway_health",
        lambda path: path.endswith("isolated.sock"),
    )
    monkeypatch.setattr(system_routes, "_gpu_status", lambda: {"embedding_device": "cpu"})

    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/system/status")

    payload = response.json()
    assert payload["enclave"] == {
        "enabled": True,
        "name": "isolated",
        "socket_ok": True,
        "today": {"ok": 1, "blocked": 1},
    }
    assert payload["enclaves"] == {"saas-data": {"reachable": False}}
    assert secret_body not in response.text
