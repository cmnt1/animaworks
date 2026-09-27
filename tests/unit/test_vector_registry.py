"""Unit tests for remote vector client selection and caching."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pytest

from core.memory.rag.endpoints import RagEndpoints, configure_endpoints
from core.memory.rag.http_store import HttpVectorStore
from core.memory.rag.vector_registry import (
    _reset_for_testing,
    configure_owner_vector_access,
    configure_server_vector_access,
    get_vector_store,
)


@pytest.fixture(autouse=True)
def _reset_registry():
    _reset_for_testing()
    yield
    _reset_for_testing()


def test_vector_url_returns_cached_http_store() -> None:
    configure_endpoints(RagEndpoints(vector_url="http://localhost:18500/api/internal/vector"))

    store = get_vector_store("sakura")

    assert isinstance(store, HttpVectorStore)
    assert store._anima_name == "sakura"
    assert store._base_url == "http://localhost:18500/api/internal/vector"
    assert get_vector_store("sakura") is store


def test_concurrent_calls_share_cached_http_store() -> None:
    configure_endpoints(RagEndpoints(vector_url="http://localhost:18500/vector"))

    with ThreadPoolExecutor(max_workers=8) as executor:
        stores = list(executor.map(lambda _index: get_vector_store("sakura"), range(8)))

    assert isinstance(stores[0], HttpVectorStore)
    assert all(store is stores[0] for store in stores)


def test_http_store_cache_is_keyed_by_base_url() -> None:
    configure_endpoints(RagEndpoints(vector_url="http://localhost:1111/vector"))
    first = get_vector_store("sakura")
    configure_endpoints(RagEndpoints(vector_url="http://localhost:2222/vector"))
    second = get_vector_store("sakura")

    assert isinstance(first, HttpVectorStore)
    assert isinstance(second, HttpVectorStore)
    assert first is not second
    assert first._base_url == "http://localhost:1111/vector"
    assert second._base_url == "http://localhost:2222/vector"


def test_owner_transport_takes_priority_and_rejects_other_animas() -> None:
    transport = MagicMock(return_value={"collections": []})
    configure_owner_vector_access(transport, anima_name="sakura")
    configure_endpoints(RagEndpoints(vector_url="http://localhost:18500/vector"))

    store = get_vector_store("sakura")

    assert isinstance(store, HttpVectorStore)
    assert store.list_collections() == []
    transport.assert_called_once()
    assert get_vector_store("other") is None


def test_server_transport_is_used_when_configured() -> None:
    send_request = MagicMock()
    configure_server_vector_access(send_request, object())

    store = get_vector_store("sakura")

    assert isinstance(store, HttpVectorStore)
    assert get_vector_store("sakura") is store


def test_missing_backend_does_not_open_native_chroma() -> None:
    configure_endpoints(RagEndpoints())

    assert get_vector_store("sakura") is None


def test_empty_anima_name_returns_none() -> None:
    configure_endpoints(RagEndpoints(vector_url="http://localhost:18500/vector"))

    assert get_vector_store(None) is None
    assert get_vector_store("") is None
