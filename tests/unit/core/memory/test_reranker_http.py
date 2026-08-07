"""Unit tests for CrossEncoderReranker HTTP/local routing."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_reranker():
    from core.memory.retrieval.reranker import _reset_for_testing

    _reset_for_testing()
    yield
    _reset_for_testing()


@pytest.fixture
def mock_cross_encoder(monkeypatch):
    """Inject a mock sentence_transformers.CrossEncoder."""
    import types

    mock_cls = MagicMock()
    mock_module = types.ModuleType("sentence_transformers")
    mock_module.CrossEncoder = mock_cls  # type: ignore[attr-defined]

    already_present = "sentence_transformers" in sys.modules
    original = sys.modules.get("sentence_transformers")
    sys.modules["sentence_transformers"] = mock_module
    yield mock_cls
    if already_present:
        sys.modules["sentence_transformers"] = original  # type: ignore[assignment]
    else:
        sys.modules.pop("sentence_transformers", None)


class TestRerankerLocal:
    def test_local_mode_scores_and_reranks(self, monkeypatch, mock_cross_encoder):
        """Without ANIMAWORKS_RERANK_URL, local CrossEncoder is used."""
        monkeypatch.delenv("ANIMAWORKS_RERANK_URL", raising=False)

        mock_model = MagicMock()
        mock_model.predict.return_value = [0.1, 0.9, 0.5]
        mock_cross_encoder.return_value = mock_model

        from core.memory.retrieval.reranker import CrossEncoderReranker

        reranker = CrossEncoderReranker()
        result = reranker.rerank_sync(
            "query",
            [{"content": "a"}, {"content": "b"}, {"content": "c"}],
            top_k=3,
        )

        assert [r["content"] for r in result] == ["b", "c", "a"]
        assert result[0]["ce_score"] == pytest.approx(0.9)
        mock_cross_encoder.assert_called_once()
        mock_model.predict.assert_called_once()


class TestRerankerHTTP:
    def test_http_mode_calls_endpoint(self, monkeypatch):
        """When ANIMAWORKS_RERANK_URL is set, scoring uses HTTP."""
        monkeypatch.setenv(
            "ANIMAWORKS_RERANK_URL",
            "http://127.0.0.1:18500/api/internal/rerank",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"scores": [0.2, 0.8]}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response) as mock_post:
            from core.memory.retrieval.reranker import CrossEncoderReranker

            reranker = CrossEncoderReranker()
            result = reranker.rerank_sync(
                "query",
                [{"content": "low"}, {"content": "high"}],
                top_k=2,
            )

        assert [r["content"] for r in result] == ["high", "low"]
        mock_post.assert_called_once_with(
            "http://127.0.0.1:18500/api/internal/rerank",
            json={"query": "query", "documents": ["low", "high"]},
            timeout=180.0,
        )

    def test_http_mode_does_not_import_sentence_transformers(self, monkeypatch):
        """With RERANK_URL set, sentence_transformers must not enter sys.modules."""
        monkeypatch.setenv(
            "ANIMAWORKS_RERANK_URL",
            "http://127.0.0.1:18500/api/internal/rerank",
        )

        # Ensure a clean slate: remove any prior import from other tests.
        st_was_present = "sentence_transformers" in sys.modules
        st_original = sys.modules.pop("sentence_transformers", None)

        mock_response = MagicMock()
        mock_response.json.return_value = {"scores": [0.5, 0.6, 0.7]}
        mock_response.raise_for_status = MagicMock()

        try:
            with patch("httpx.post", return_value=mock_response):
                from core.memory.retrieval.reranker import CrossEncoderReranker

                reranker = CrossEncoderReranker()
                result = reranker.rerank_sync(
                    "q",
                    [{"content": "a"}, {"content": "b"}, {"content": "c"}],
                    top_k=3,
                )

            assert len(result) == 3
            assert "sentence_transformers" not in sys.modules
        finally:
            if st_was_present and st_original is not None:
                sys.modules["sentence_transformers"] = st_original

    def test_http_failure_skips_rerank_keeps_order(self, monkeypatch):
        """HTTP failure skips rerank (original order) — no local model fallback."""
        import httpx

        monkeypatch.setenv("ANIMAWORKS_RERANK_URL", "http://localhost/rerank")

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "503",
            request=MagicMock(),
            response=MagicMock(),
        )

        items = [
            {"content": "first", "id": 1},
            {"content": "second", "id": 2},
            {"content": "third", "id": 3},
        ]

        st_was_present = "sentence_transformers" in sys.modules
        st_original = sys.modules.pop("sentence_transformers", None)

        try:
            with patch("httpx.post", return_value=mock_response):
                from core.memory.retrieval.reranker import CrossEncoderReranker

                reranker = CrossEncoderReranker()
                result = reranker.rerank_sync("q", items, top_k=3)

            # Original order preserved; no ce_score (skip path)
            assert [r["content"] for r in result] == ["first", "second", "third"]
            assert all("ce_score" not in r for r in result)
            assert "sentence_transformers" not in sys.modules
        finally:
            if st_was_present and st_original is not None:
                sys.modules["sentence_transformers"] = st_original

    def test_http_connection_error_skips(self, monkeypatch):
        """Network errors also skip without local fallback."""
        import httpx

        monkeypatch.setenv("ANIMAWORKS_RERANK_URL", "http://localhost/rerank")

        with patch(
            "httpx.post",
            side_effect=httpx.ConnectError("refused"),
        ):
            from core.memory.retrieval.reranker import CrossEncoderReranker

            reranker = CrossEncoderReranker()
            result = reranker.rerank_sync(
                "q",
                [{"content": "a"}, {"content": "b"}],
                top_k=2,
            )

        assert [r["content"] for r in result] == ["a", "b"]

    def test_http_batches_large_requests(self, monkeypatch):
        """Requests over batch limit should be split."""
        monkeypatch.setenv("ANIMAWORKS_RERANK_URL", "http://localhost/rerank")

        batch1 = MagicMock()
        batch1.json.return_value = {"scores": [float(i) for i in range(1000)]}
        batch1.raise_for_status = MagicMock()

        batch2 = MagicMock()
        batch2.json.return_value = {"scores": [1000.0, 1001.0]}
        batch2.raise_for_status = MagicMock()

        items = [{"content": f"d{i}"} for i in range(1002)]

        with patch("httpx.post", side_effect=[batch1, batch2]) as mock_post:
            from core.memory.retrieval.reranker import CrossEncoderReranker

            reranker = CrossEncoderReranker()
            result = reranker.rerank_sync("q", items, top_k=3, min_candidates=2)

        assert mock_post.call_count == 2
        # Highest scores are 1001 and 1000 (from batch2)
        assert result[0]["content"] == "d1001"
        assert result[1]["content"] == "d1000"

    def test_empty_items_skip_http(self, monkeypatch):
        """Empty items return immediately without HTTP call."""
        monkeypatch.setenv("ANIMAWORKS_RERANK_URL", "http://localhost/rerank")

        with patch("httpx.post") as mock_post:
            from core.memory.retrieval.reranker import CrossEncoderReranker

            reranker = CrossEncoderReranker()
            result = reranker.rerank_sync("q", [], top_k=5)

        assert result == []
        mock_post.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_rerank_uses_http(self, monkeypatch):
        """Async path also respects ANIMAWORKS_RERANK_URL."""
        monkeypatch.setenv("ANIMAWORKS_RERANK_URL", "http://localhost/rerank")

        mock_response = MagicMock()
        mock_response.json.return_value = {"scores": [0.3, 0.7]}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_response):
            from core.memory.retrieval.reranker import CrossEncoderReranker

            reranker = CrossEncoderReranker()
            result = await reranker.rerank(
                "q",
                [{"fact": "a"}, {"fact": "b"}],
                top_k=2,
            )

        assert [r["fact"] for r in result] == ["b", "a"]
