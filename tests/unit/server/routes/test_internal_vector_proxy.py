from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from server.routes.internal import create_internal_router


@pytest.fixture(autouse=True)
def english_diagnostics(monkeypatch):
    monkeypatch.setattr("core.paths._get_locale", lambda: "en")


@pytest.mark.asyncio
async def test_vector_proxy_requires_anima_name() -> None:
    app = FastAPI()
    app.state.supervisor = SimpleNamespace(send_request=AsyncMock())
    app.include_router(create_internal_router(), prefix="/api")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/internal/vector/list-collections", json={})

    assert response.status_code == 422
    app.state.supervisor.send_request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,payload,method,expected_params",
    [
        (
            "query",
            {"collection": "sakura_knowledge", "embedding": [0.1], "top_k": 1},
            "memory.query",
            {"collection": "sakura_knowledge", "embedding": [0.1], "top_k": 1, "filter_metadata": None},
        ),
        (
            "upsert",
            {"collection": "sakura_knowledge", "documents": []},
            "memory.upsert",
            {"collection": "sakura_knowledge", "documents": []},
        ),
    ],
)
async def test_valid_anima_forwards_to_root(endpoint, payload, method, expected_params) -> None:
    supervisor = SimpleNamespace(send_request=AsyncMock(return_value={"ok": True, "result": []}))
    app = FastAPI()
    app.state.supervisor = supervisor
    app.include_router(create_internal_router(), prefix="/api")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/internal/vector/{endpoint}",
            json={"anima_name": "sakura", **payload},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True, "result": []}
    supervisor.send_request.assert_awaited_once_with(
        "sakura",
        "memory",
        {"method": method, "params": expected_params},
        timeout=120.0,
    )


@pytest.mark.asyncio
async def test_root_unavailable_returns_503_and_retry_after() -> None:
    app = FastAPI()
    app.include_router(create_internal_router(), prefix="/api")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/internal/vector/list-collections",
            json={"anima_name": "sakura"},
        )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "1"
    assert response.json() == {"detail": "Root memory service unavailable", "retry_after_ms": 250}


@pytest.mark.asyncio
async def test_invalid_anima_name_returns_422() -> None:
    supervisor = SimpleNamespace(send_request=AsyncMock())
    app = FastAPI()
    app.state.supervisor = supervisor
    app.include_router(create_internal_router(), prefix="/api")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/internal/vector/list-collections",
            json={"anima_name": "../other"},
        )

    assert response.status_code == 422
    supervisor.send_request.assert_not_awaited()
