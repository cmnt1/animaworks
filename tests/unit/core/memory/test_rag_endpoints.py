from __future__ import annotations

import os

from core.memory.rag.endpoints import RagEndpoints, configure_endpoints, get_endpoints


def test_from_env_reads_and_caches_rag_urls(monkeypatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_VECTOR_URL", "http://vector.example/api/vector")
    monkeypatch.setenv("ANIMAWORKS_EMBED_URL", "http://vector.example/api/embed")
    monkeypatch.setenv("ANIMAWORKS_RERANK_URL", "http://vector.example/api/rerank")
    configure_endpoints(None)

    expected = RagEndpoints(
        vector_url="http://vector.example/api/vector",
        embed_url="http://vector.example/api/embed",
        rerank_url="http://vector.example/api/rerank",
    )
    assert RagEndpoints.from_env() == expected
    assert get_endpoints() == expected

    monkeypatch.setenv("ANIMAWORKS_VECTOR_URL", "http://changed.example/vector")
    assert get_endpoints() == expected
    configure_endpoints(None)


def test_configure_endpoints_overrides_environment_without_writing(monkeypatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_VECTOR_URL", "http://env.example/vector")
    monkeypatch.setenv("ANIMAWORKS_EMBED_URL", "http://env.example/embed")
    monkeypatch.setenv("ANIMAWORKS_RERANK_URL", "http://env.example/rerank")
    before = os.environ.copy()
    configured = RagEndpoints.for_server(18500)

    configure_endpoints(configured)
    try:
        assert get_endpoints() == configured
        assert os.environ == before
    finally:
        configure_endpoints(None)


def test_child_env_exports_configured_urls() -> None:
    from core.memory.rag.endpoints import child_env

    endpoints = RagEndpoints.for_server(18500)
    assert child_env(endpoints) == {
        "ANIMAWORKS_VECTOR_URL": "http://127.0.0.1:18500/api/internal/vector",
        "ANIMAWORKS_EMBED_URL": "http://127.0.0.1:18500/api/internal/embed",
        "ANIMAWORKS_RERANK_URL": "http://127.0.0.1:18500/api/internal/rerank",
    }
