"""Unit tests for the HTTP vector API ⇔ MemoryService conversion."""

from __future__ import annotations

import pytest

from core.memory.rag.vector_ops import (
    _PATH_TO_METHOD,
    UnsupportedVectorPath,
    request_payload,
    to_owner_interaction,
)


def test_all_supported_endpoints_map_to_memory_methods() -> None:
    for path, method in _PATH_TO_METHOD.items():
        parsed_method, params = to_owner_interaction(path, {"anima_name": "sakura", "collection": "k"})
        assert parsed_method == method
        assert params == {"collection": "k"}


def test_anima_name_is_routed_away_not_part_of_params() -> None:
    method, params = to_owner_interaction("/query", {"anima_name": "sakura", "embedding": [0.1]})
    assert method == "memory.query"
    assert params == {"embedding": [0.1]}


def test_request_payload_removes_anima_name_only() -> None:
    assert request_payload({"anima_name": "sakura", "collection": "k", "ids": ["a"]}) == {
        "collection": "k",
        "ids": ["a"],
    }
    # No anima_name in the input should be a no-op.
    assert request_payload({"collection": "k"}) == {"collection": "k"}


def test_worker_only_endpoints_have_no_memory_equivalent() -> None:
    for path in ("/reset-store", "/verify-repair", "/quick-check"):
        with pytest.raises(UnsupportedVectorPath):
            to_owner_interaction(path, {})
