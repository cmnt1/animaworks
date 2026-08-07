"""Unit tests for POST /api/internal/rerank endpoint."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


def _make_test_app():
    """Create a minimal FastAPI app with internal routes."""
    from fastapi import FastAPI

    from server.routes.internal import create_internal_router

    app = FastAPI()
    app.state.shared_dir = Path("/tmp/test-shared")
    app.include_router(create_internal_router(), prefix="/api")
    return app


@pytest.fixture
def app():
    return _make_test_app()


class TestInternalRerank:
    @pytest.mark.anyio
    async def test_returns_scores(self, app):
        """Valid request returns scores for each document."""
        mock_reranker = MagicMock()
        mock_reranker.score_sync.return_value = [0.1, 0.9, 0.5]

        with patch(
            "core.memory.retrieval.reranker.get_reranker",
            return_value=mock_reranker,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/internal/rerank",
                    json={
                        "query": "hello",
                        "documents": ["a", "b", "c"],
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["scores"] == pytest.approx([0.1, 0.9, 0.5])
        mock_reranker.score_sync.assert_called_once_with("hello", ["a", "b", "c"])

    @pytest.mark.anyio
    async def test_empty_documents_returns_empty(self, app):
        """Empty documents list returns empty scores without loading model."""
        with patch("core.memory.retrieval.reranker.get_reranker") as mock_get:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/internal/rerank",
                    json={"query": "q", "documents": []},
                )

        assert resp.status_code == 200
        assert resp.json() == {"scores": []}
        mock_get.assert_not_called()

    @pytest.mark.anyio
    async def test_rejects_over_1000_documents(self, app):
        """Requests with >1000 documents should be rejected."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            resp = await client.post(
                "/api/internal/rerank",
                json={
                    "query": "q",
                    "documents": [f"doc_{i}" for i in range(1001)],
                },
            )

        assert resp.status_code == 400
        assert "Max 1000" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_exactly_1000_documents_accepted(self, app):
        """Exactly 1000 documents should be accepted."""
        mock_reranker = MagicMock()
        mock_reranker.score_sync.return_value = [0.1] * 1000

        with patch(
            "core.memory.retrieval.reranker.get_reranker",
            return_value=mock_reranker,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/internal/rerank",
                    json={
                        "query": "q",
                        "documents": [f"d{i}" for i in range(1000)],
                    },
                )

        assert resp.status_code == 200
        assert len(resp.json()["scores"]) == 1000

    @pytest.mark.anyio
    async def test_unavailable_returns_503(self, app):
        """Model failure must be an explicit error, not empty success."""
        mock_reranker = MagicMock()
        mock_reranker.score_sync.return_value = None

        with patch(
            "core.memory.retrieval.reranker.get_reranker",
            return_value=mock_reranker,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/internal/rerank",
                    json={"query": "q", "documents": ["a"]},
                )

        assert resp.status_code == 503
        assert "unavailable" in resp.json()["detail"].lower()

    @pytest.mark.anyio
    async def test_top_k_adds_results(self, app):
        """Optional top_k returns ranked index+score alongside full scores."""
        mock_reranker = MagicMock()
        mock_reranker.score_sync.return_value = [0.1, 0.9, 0.5]

        with patch(
            "core.memory.retrieval.reranker.get_reranker",
            return_value=mock_reranker,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                resp = await client.post(
                    "/api/internal/rerank",
                    json={
                        "query": "q",
                        "documents": ["a", "b", "c"],
                        "top_k": 2,
                    },
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["scores"] == pytest.approx([0.1, 0.9, 0.5])
        assert data["results"] == [
            {"index": 1, "score": pytest.approx(0.9)},
            {"index": 2, "score": pytest.approx(0.5)},
        ]
