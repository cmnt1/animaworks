from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.general_db import SnsSearchStore
from server.routes.sns_search import create_sns_search_router


def _client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
    app = FastAPI()
    db_path = tmp_path / "general_db.sqlite3"
    app.include_router(create_sns_search_router(lambda: SnsSearchStore(db_path)), prefix="/api")
    return TestClient(app)


class TestSnsSearchRoutes:
    def test_crud_flow(self, tmp_path, monkeypatch):
        client = _client(tmp_path, monkeypatch)

        res = client.get("/api/sns-search")
        assert res.status_code == 200
        assert res.json() == {"items": []}

        res = client.post(
            "/api/sns-search",
            json={"Division": "Finance", "Words": "$NVDA OR NVIDIA"},
        )
        assert res.status_code == 200
        created = res.json()["item"]
        assert created["ID_Sns_Search"] == 1
        assert created["Division"] == "Finance"

        res = client.put(
            "/api/sns-search/1",
            json={"Division": "Trading", "Words": "$BTC OR bitcoin"},
        )
        assert res.status_code == 200
        assert res.json()["item"]["Division"] == "Trading"

        res = client.get("/api/sns-search")
        assert res.status_code == 200
        assert res.json()["items"][0]["Words"] == "$BTC OR bitcoin"

        res = client.delete("/api/sns-search/1")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    def test_missing_entry_returns_404(self, tmp_path, monkeypatch):
        client = _client(tmp_path, monkeypatch)
        res = client.delete("/api/sns-search/999")
        assert res.status_code == 404
