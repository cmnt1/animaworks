from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config.models import AnimaWorksConfig, PhoneConfig
from server.routes.internal import create_internal_router


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(create_internal_router(), prefix="/api")
    return app


def test_internal_phone_alert_starts_only_for_configured_anima(monkeypatch) -> None:
    config = AnimaWorksConfig(phone=PhoneConfig(enabled=True, anima="aoi"))
    start_alert = AsyncMock(return_value="alert-id")
    monkeypatch.setattr("core.config.load_config", lambda: config)
    monkeypatch.setattr("core.phone.alert.start_alert", start_alert)

    with TestClient(_app()) as client:
        response = client.post(
            "/api/internal/phone/alert",
            json={"anima": "aoi", "subject": "Outage", "body": "API is down"},
        )
        other = client.post(
            "/api/internal/phone/alert",
            json={"anima": "rin", "subject": "Outage", "body": "API is down"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "calling"}
    start_alert.assert_awaited_once_with("aoi", "Outage", "API is down", phone_config=config.phone)
    assert other.status_code == 200
    assert other.json()["status"] == "skipped"


def test_internal_phone_alert_skips_when_phone_is_disabled(monkeypatch) -> None:
    config = AnimaWorksConfig(phone=PhoneConfig(enabled=False))
    start_alert = AsyncMock()
    monkeypatch.setattr("core.config.load_config", lambda: config)
    monkeypatch.setattr("core.phone.alert.start_alert", start_alert)

    with TestClient(_app()) as client:
        response = client.post(
            "/api/internal/phone/alert",
            json={"anima": "aoi", "subject": "Outage", "body": "API is down"},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "skipped", "reason": "phone channel is disabled"}
    start_alert.assert_not_awaited()
