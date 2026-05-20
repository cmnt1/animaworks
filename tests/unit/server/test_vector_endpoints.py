# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for server vector endpoints (ChromaDB process separation)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.memory.rag.vector_worker_client import VectorWorkerResponse, VectorWorkerUnavailable
from server.routes.internal import create_internal_router


def _make_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(create_internal_router(), prefix="/api")
    return app


class _FakeVectorWorker:
    enabled = True
    fallback_direct = True
    native_crash_detected = False

    def __init__(self, response: VectorWorkerResponse | None = None, exc: Exception | None = None) -> None:
        self.response = response or VectorWorkerResponse(status_code=200, data={"results": []})
        self.exc = exc
        self.calls: list[tuple[str, dict]] = []

    async def post(self, path: str, payload: dict):
        self.calls.append((path, payload))
        if self.exc:
            raise self.exc
        return self.response


# ── test_vector_query ─────────────────────────────────────────────


async def test_vector_query():
    """POST to /api/internal/vector/query with valid body. Mock get_vector_store. Assert response has results."""
    mock_store = MagicMock()
    mock_store.query.return_value = []
    from core.memory.rag.store import Document, SearchResult

    mock_store.query.return_value = [
        SearchResult(document=Document(id="doc1", content="hello", metadata={"k": "v"}), score=0.9),
    ]

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/query",
                json={
                    "collection": "rin_knowledge",
                    "embedding": [0.1, 0.2],
                    "top_k": 5,
                },
            )

    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert len(data["results"]) == 1
    assert data["results"][0]["id"] == "doc1"
    assert data["results"][0]["content"] == "hello"
    assert data["results"][0]["score"] == 0.9
    mock_store.query.assert_called_once_with("rin_knowledge", [0.1, 0.2], 5, None)


async def test_vector_query_uses_worker_when_available():
    """Server proxies vector requests to the isolated worker before touching Chroma locally."""
    worker = _FakeVectorWorker(
        VectorWorkerResponse(
            status_code=200,
            data={"results": [{"id": "docw", "content": "worker", "score": 1.0, "metadata": {}}]},
        )
    )
    app = _make_test_app()
    app.state.vector_worker = worker
    transport = ASGITransport(app=app)

    with patch("core.memory.rag.singleton.get_vector_store") as get_store:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/query",
                json={
                    "anima_name": "rin",
                    "collection": "rin_knowledge",
                    "embedding": [0.1, 0.2],
                    "top_k": 5,
                },
            )

    assert resp.status_code == 200
    assert resp.json()["results"][0]["id"] == "docw"
    assert worker.calls == [
        (
            "/query",
            {
                "anima_name": "rin",
                "collection": "rin_knowledge",
                "embedding": [0.1, 0.2],
                "top_k": 5,
                "filter_metadata": None,
            },
        )
    ]
    get_store.assert_not_called()


async def test_vector_query_falls_back_when_worker_unavailable():
    worker = _FakeVectorWorker(exc=VectorWorkerUnavailable("down"))
    mock_store = MagicMock()
    mock_store.query.return_value = []

    app = _make_test_app()
    app.state.vector_worker = worker
    transport = ASGITransport(app=app)
    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/query",
                json={"collection": "rin_knowledge", "embedding": [0.1]},
            )

    assert resp.status_code == 200
    assert resp.json() == {"results": []}
    mock_store.query.assert_called_once()


async def test_vector_query_no_fallback_returns_503_when_worker_unavailable():
    worker = _FakeVectorWorker(exc=VectorWorkerUnavailable("down"))
    worker.fallback_direct = False
    app = _make_test_app()
    app.state.vector_worker = worker
    transport = ASGITransport(app=app)

    with patch("core.memory.rag.singleton.get_vector_store") as get_store:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/query",
                json={"collection": "rin_knowledge", "embedding": [0.1]},
            )

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Vector worker unavailable"
    get_store.assert_not_called()


async def test_vector_query_does_not_fallback_after_native_worker_crash():
    worker = _FakeVectorWorker(exc=VectorWorkerUnavailable("native crash"))
    worker.fallback_direct = True
    worker.native_crash_detected = True
    app = _make_test_app()
    app.state.vector_worker = worker
    transport = ASGITransport(app=app)

    with patch("core.memory.rag.singleton.get_vector_store") as get_store:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/query",
                json={"collection": "rin_knowledge", "embedding": [0.1]},
            )

    assert resp.status_code == 503
    get_store.assert_not_called()


# ── test_vector_query_no_store ────────────────────────────────────


async def test_vector_query_no_store():
    """Mock get_vector_store to return None. Assert response is {"results": []}."""
    with patch("core.memory.rag.singleton.get_vector_store", return_value=None):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/query",
                json={"collection": "col", "embedding": [0.1], "top_k": 5},
            )

    assert resp.status_code == 200
    assert resp.json() == {"results": []}


# ── test_vector_upsert ───────────────────────────────────────────


async def test_vector_upsert():
    """POST to /api/internal/vector/upsert. Mock store. Assert store.upsert was called with Document objects."""
    mock_store = MagicMock()

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/upsert",
                json={
                    "collection": "rin_knowledge",
                    "documents": [
                        {"id": "d1", "content": "c1", "embedding": [0.1, 0.2], "metadata": {"k": "v"}},
                    ],
                },
            )

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    mock_store.upsert.assert_called_once()
    call_args = mock_store.upsert.call_args
    assert call_args[0][0] == "rin_knowledge"
    docs = call_args[0][1]
    assert len(docs) == 1
    assert docs[0].id == "d1"
    assert docs[0].content == "c1"
    assert docs[0].embedding == [0.1, 0.2]
    assert docs[0].metadata == {"k": "v"}


# ── test_vector_upsert_no_store ───────────────────────────────────


async def test_vector_upsert_no_store():
    """Mock store None → 503."""
    with patch("core.memory.rag.singleton.get_vector_store", return_value=None):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/upsert",
                json={"collection": "col", "documents": [{"id": "d1", "content": "c1"}]},
            )

    assert resp.status_code == 503
    assert resp.json()["detail"] == "Vector store unavailable"


# ── test_vector_upsert_store_failure ──────────────────────────────


async def test_vector_upsert_store_failure_returns_500():
    """Store false return must not be hidden behind HTTP 200."""
    mock_store = MagicMock()
    mock_store.upsert.return_value = False

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/upsert",
                json={
                    "collection": "rin_knowledge",
                    "documents": [
                        {"id": "d1", "content": "c1", "embedding": [0.1, 0.2], "metadata": {"k": "v"}},
                    ],
                },
            )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Vector upsert failed"


# ── test_vector_update_metadata ───────────────────────────────────


async def test_vector_update_metadata():
    """POST to /api/internal/vector/update-metadata. Mock store. Assert store.update_metadata called."""
    mock_store = MagicMock()

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/update-metadata",
                json={
                    "collection": "col",
                    "ids": ["id1", "id2"],
                    "metadatas": [{"k1": "v1"}, {"k2": "v2"}],
                },
            )

    assert resp.status_code == 200
    mock_store.update_metadata.assert_called_once_with("col", ["id1", "id2"], [{"k1": "v1"}, {"k2": "v2"}])


async def test_vector_update_metadata_store_failure_returns_500():
    mock_store = MagicMock()
    mock_store.update_metadata.return_value = False

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/update-metadata",
                json={
                    "collection": "col",
                    "ids": ["id1"],
                    "metadatas": [{"k1": "v1"}],
                },
            )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Vector update-metadata failed"


# ── test_vector_delete_documents ──────────────────────────────────


async def test_vector_delete_documents():
    """POST to /api/internal/vector/delete-documents. Mock store. Assert store.delete_documents called."""
    mock_store = MagicMock()

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/delete-documents",
                json={"collection": "col", "ids": ["id1", "id2"]},
            )

    assert resp.status_code == 200
    mock_store.delete_documents.assert_called_once_with("col", ["id1", "id2"])


async def test_vector_delete_documents_store_failure_returns_500():
    mock_store = MagicMock()
    mock_store.delete_documents.return_value = False

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/delete-documents",
                json={"collection": "col", "ids": ["id1"]},
            )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Vector delete-documents failed"


# ── test_vector_get_by_metadata ───────────────────────────────────


async def test_vector_get_by_metadata():
    """POST with where filter. Assert results."""
    from core.memory.rag.store import Document, SearchResult

    mock_store = MagicMock()
    mock_store.get_by_metadata.return_value = [
        SearchResult(document=Document(id="doc1", content="hello", metadata={"type": "knowledge"}), score=1.0),
    ]

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/get-by-metadata",
                json={"collection": "col", "where": {"type": "knowledge"}, "limit": 10},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["results"][0]["id"] == "doc1"
    assert data["results"][0]["content"] == "hello"
    mock_store.get_by_metadata.assert_called_once_with("col", {"type": "knowledge"}, 10)


# ── test_vector_get_by_ids ───────────────────────────────────────


async def test_vector_get_by_ids():
    """POST with ids. Assert documents in response."""
    from core.memory.rag.store import Document

    mock_store = MagicMock()
    mock_store.get_by_ids.return_value = [
        Document(id="doc1", content="hello", metadata={"key": "val"}),
    ]

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/get-by-ids",
                json={"collection": "col", "ids": ["doc1"]},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["documents"][0]["id"] == "doc1"
    assert data["documents"][0]["content"] == "hello"
    assert data["documents"][0]["metadata"] == {"key": "val"}


# ── test_vector_create_collection ─────────────────────────────────


async def test_vector_create_collection():
    """POST to create-collection. Assert store.create_collection called."""
    mock_store = MagicMock()

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/create-collection",
                json={"collection": "new_col"},
            )

    assert resp.status_code == 200
    mock_store.create_collection.assert_called_once_with("new_col")


async def test_vector_create_collection_store_failure_returns_500():
    mock_store = MagicMock()
    mock_store.create_collection.return_value = False

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/create-collection",
                json={"collection": "new_col"},
            )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Vector create-collection failed"


async def test_vector_delete_collection_store_failure_returns_500():
    mock_store = MagicMock()
    mock_store.delete_collection.return_value = False

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/delete-collection",
                json={"collection": "old_col"},
            )

    assert resp.status_code == 500
    assert resp.json()["detail"] == "Vector delete-collection failed"


# ── test_vector_list_collections ──────────────────────────────────


async def test_vector_list_collections():
    """POST to list-collections. Assert collections list returned."""
    mock_store = MagicMock()
    mock_store.list_collections.return_value = ["col1", "col2"]

    with patch("core.memory.rag.singleton.get_vector_store", return_value=mock_store):
        app = _make_test_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/internal/vector/list-collections",
                json={},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["collections"] == ["col1", "col2"]
