from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from server.routes.internal import create_internal_router


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint,body,method,params",
    [
        (
            "query",
            {"collection": "c", "embedding": [0.1], "top_k": 2},
            "memory.query",
            {"collection": "c", "embedding": [0.1], "top_k": 2, "filter_metadata": None},
        ),
        ("upsert", {"collection": "c", "documents": []}, "memory.upsert", {"collection": "c", "documents": []}),
        (
            "update-metadata",
            {"collection": "c", "ids": ["id"], "metadatas": [{"k": "v"}]},
            "memory.update_metadata",
            {"collection": "c", "ids": ["id"], "metadatas": [{"k": "v"}]},
        ),
        (
            "delete-documents",
            {"collection": "c", "ids": ["id"]},
            "memory.delete_documents",
            {"collection": "c", "ids": ["id"]},
        ),
        (
            "get-by-metadata",
            {"collection": "c"},
            "memory.get_by_metadata",
            {"collection": "c", "where": {}, "limit": 20},
        ),
        (
            "get-by-ids",
            {"collection": "c", "ids": ["id"]},
            "memory.get_by_ids",
            {"collection": "c", "ids": ["id"]},
        ),
        ("create-collection", {"collection": "c"}, "memory.create_collection", {"collection": "c"}),
        ("delete-collection", {"collection": "c"}, "memory.delete_collection", {"collection": "c"}),
        ("list-collections", {}, "memory.list_collections_checked", {}),
    ],
)
async def test_vector_endpoints_forward_to_anima_root(endpoint, body, method, params) -> None:
    supervisor = SimpleNamespace(send_request=AsyncMock(return_value={"ok": True}))
    app = FastAPI()
    app.state.supervisor = supervisor
    app.include_router(create_internal_router(), prefix="/api")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/internal/vector/{endpoint}",
            json={"anima_name": "rin", **body},
        )

    assert response.status_code == 200
    supervisor.send_request.assert_awaited_once_with(
        "rin",
        "memory",
        {"method": method, "params": params},
        timeout=120.0,
    )


@pytest.mark.asyncio
async def test_worker_only_vector_routes_are_not_registered() -> None:
    app = FastAPI()
    app.include_router(create_internal_router(), prefix="/api")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        quick_check = await client.post("/api/internal/vector/quick-check", json={})
        reset_store = await client.post("/api/internal/vector/reset-store", json={})

    assert quick_check.status_code == 404
    assert reset_store.status_code == 404
