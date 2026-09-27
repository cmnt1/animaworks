from __future__ import annotations

import asyncio
from typing import Any

import pytest

from core.memory.rag.vector_client import VectorStoreRetryableError
from core.memory.rag.vector_ops import (
    _PATH_TO_METHOD,
    UnsupportedVectorPath,
    bridge_transport,
    request_payload,
    to_owner_interaction,
)
from core.supervisor.memory_service import MemoryServiceUnavailable


def test_all_supported_endpoints_map_to_memory_methods() -> None:
    for path, expected_method in _PATH_TO_METHOD.items():
        method, params = to_owner_interaction(path, {"anima_name": "sora", "collection": "k"})
        assert method == expected_method
        assert params == {"collection": "k"}


def test_request_payload_removes_routing_name_only() -> None:
    assert request_payload({"anima_name": "sora", "collection": "k", "ids": ["a"]}) == {
        "collection": "k",
        "ids": ["a"],
    }
    assert request_payload({"collection": "k"}) == {"collection": "k"}


def test_unsupported_vector_paths_have_no_memory_equivalent() -> None:
    for path in ("/reset-store", "/verify-repair", "/quick-check"):
        with pytest.raises(UnsupportedVectorPath):
            to_owner_interaction(path, {})


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["negative_response", "unavailable", "send_exception"])
async def test_bridge_transport_converts_failures_to_retryable(
    failure: str,
) -> None:
    async def handler(_method: str, _params: dict[str, Any]) -> dict[str, Any]:
        if failure == "negative_response":
            return {"ok": False, "error": "not ready"}
        if failure == "unavailable":
            raise MemoryServiceUnavailable("not ready")
        raise RuntimeError("IPC disconnected")

    transport = bridge_transport(handler, asyncio.get_running_loop())
    with pytest.raises(VectorStoreRetryableError):
        await asyncio.to_thread(transport, "/query", {"anima_name": "sora"})


@pytest.mark.asyncio
async def test_bridge_transport_rejects_calls_on_loop_thread() -> None:
    async def handler(_method: str, _params: dict[str, Any]) -> dict[str, Any]:
        return {"results": []}

    transport = bridge_transport(handler, asyncio.get_running_loop())
    with pytest.raises(RuntimeError, match="event loop"):
        transport("/query", {"anima_name": "sora"})


@pytest.mark.asyncio
async def test_bridge_transport_maps_path_and_payload() -> None:
    received: list[tuple[str, dict[str, Any]]] = []

    async def handler(method: str, params: dict[str, Any]) -> dict[str, Any]:
        received.append((method, params))
        return {"collections": []}

    transport = bridge_transport(handler, asyncio.get_running_loop())
    assert await asyncio.to_thread(
        transport,
        "/list-collections",
        {"anima_name": "sora", "unused": 1},
    ) == {"collections": []}
    assert received == [("memory.list_collections", {"unused": 1})]
