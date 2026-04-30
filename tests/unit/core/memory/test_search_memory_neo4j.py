"""Tests for Issue #15 — search_memory Neo4j backend integration.

Covers:
- Neo4j scope routing (_should_use_neo4j)
- Scope mapping (knowledge→fact, episodes→episode, etc.)
- Legacy-only scopes (common_knowledge, skills, activity_log)
- Fallback on Neo4j failure
- Output formatting compatibility
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from core.memory.backend.base import RetrievedMemory


# ── Fixtures ─────────────────────────────────────────────


@pytest.fixture
def mock_memory():
    mem = MagicMock()
    mem.search_memory_text = MagicMock(return_value=[])
    return mem


def _make_handler_mixin(mock_memory, backend_class_name="Neo4jGraphBackend"):
    """Create a minimal MemoryToolsMixin-like object for testing."""
    from core.tooling.handler_memory import MemoryToolsMixin

    class FakeHandler(MemoryToolsMixin):
        _anima_name = "test"
        _anima_dir = "/tmp/test"
        _context_window = 128_000
        _read_paths: set[str] = set()

        def _anima_search_hint(self, query):
            return None

    handler = FakeHandler.__new__(FakeHandler)
    handler._memory = mock_memory
    handler._anima_name = "test"
    handler._anima_dir = "/tmp/test"
    handler._context_window = 128_000
    handler._read_paths = set()

    mock_backend = AsyncMock()
    mock_backend.__class__.__name__ = backend_class_name
    type(mock_memory).memory_backend = PropertyMock(return_value=mock_backend)

    return handler, mock_backend


# ── TestShouldUseNeo4j ───────────────────────────────────


class TestShouldUseNeo4j:
    def test_returns_true_for_neo4j_backend(self, mock_memory) -> None:
        handler, _ = _make_handler_mixin(mock_memory, "Neo4jGraphBackend")
        assert handler._should_use_neo4j("knowledge") is True

    def test_returns_false_for_legacy_backend(self, mock_memory) -> None:
        handler, _ = _make_handler_mixin(mock_memory, "LegacyRAGBackend")
        assert handler._should_use_neo4j("knowledge") is False

    def test_returns_false_for_activity_log(self, mock_memory) -> None:
        handler, _ = _make_handler_mixin(mock_memory, "Neo4jGraphBackend")
        assert handler._should_use_neo4j("activity_log") is False

    def test_returns_false_for_common_knowledge(self, mock_memory) -> None:
        handler, _ = _make_handler_mixin(mock_memory, "Neo4jGraphBackend")
        assert handler._should_use_neo4j("common_knowledge") is False

    def test_returns_false_for_skills(self, mock_memory) -> None:
        handler, _ = _make_handler_mixin(mock_memory, "Neo4jGraphBackend")
        assert handler._should_use_neo4j("skills") is False

    def test_returns_false_on_backend_error(self, mock_memory) -> None:
        handler, _ = _make_handler_mixin(mock_memory, "Neo4jGraphBackend")
        type(mock_memory).memory_backend = PropertyMock(side_effect=RuntimeError("fail"))
        assert handler._should_use_neo4j("all") is False


# ── TestNeo4jScopeMap ────────────────────────────────────


class TestNeo4jScopeMap:
    def test_knowledge_maps_to_fact(self) -> None:
        from core.tooling.handler_memory import MemoryToolsMixin

        assert MemoryToolsMixin._NEO4J_SCOPE_MAP["knowledge"] == "fact"

    def test_episodes_maps_to_episode(self) -> None:
        from core.tooling.handler_memory import MemoryToolsMixin

        assert MemoryToolsMixin._NEO4J_SCOPE_MAP["episodes"] == "episode"

    def test_procedures_maps_to_fact(self) -> None:
        from core.tooling.handler_memory import MemoryToolsMixin

        assert MemoryToolsMixin._NEO4J_SCOPE_MAP["procedures"] == "fact"

    def test_all_maps_to_all(self) -> None:
        from core.tooling.handler_memory import MemoryToolsMixin

        assert MemoryToolsMixin._NEO4J_SCOPE_MAP["all"] == "all"


# ── TestSearchViaNeo4j ───────────────────────────────────


class TestSearchViaNeo4j:
    def test_returns_formatted_results(self, mock_memory) -> None:
        handler, mock_backend = _make_handler_mixin(mock_memory)
        mock_backend.retrieve = AsyncMock(
            return_value=[
                RetrievedMemory(
                    content="Alice → Bob: works together",
                    score=0.95,
                    source="fact:uuid-1",
                    metadata={},
                ),
            ]
        )

        result = handler._search_via_neo4j("Alice", "knowledge", 0)
        assert result is not None
        assert "Alice → Bob" in result
        assert "score=0.95" in result
        assert "graph" in result

    def test_returns_empty_string_on_no_results(self, mock_memory) -> None:
        handler, mock_backend = _make_handler_mixin(mock_memory)
        mock_backend.retrieve = AsyncMock(return_value=[])

        result = handler._search_via_neo4j("nothing", "all", 0)
        assert result == ""

    def test_returns_none_on_failure(self, mock_memory) -> None:
        handler, mock_backend = _make_handler_mixin(mock_memory)
        mock_backend.retrieve = AsyncMock(side_effect=RuntimeError("Neo4j down"))

        result = handler._search_via_neo4j("query", "all", 0)
        assert result is None

    def test_offset_skips_results(self, mock_memory) -> None:
        handler, mock_backend = _make_handler_mixin(mock_memory)
        mock_backend.retrieve = AsyncMock(
            return_value=[
                RetrievedMemory(content="result1", score=0.9, source="fact:1"),
                RetrievedMemory(content="result2", score=0.8, source="fact:2"),
                RetrievedMemory(content="result3", score=0.7, source="fact:3"),
            ]
        )

        result = handler._search_via_neo4j("query", "all", 1)
        assert result is not None
        assert "result1" not in result
        assert "result2" in result


# ── TestHandleSearchMemoryIntegration ────────────────────


class TestHandleSearchMemoryIntegration:
    def test_neo4j_path_used_when_available(self, mock_memory) -> None:
        handler, mock_backend = _make_handler_mixin(mock_memory)
        mock_backend.retrieve = AsyncMock(
            return_value=[
                RetrievedMemory(content="graph result", score=0.9, source="fact:1"),
            ]
        )

        result = handler._handle_search_memory({"query": "test", "scope": "knowledge"})
        assert "graph result" in result
        mock_memory.search_memory_text.assert_not_called()

    def test_legacy_path_for_activity_log(self, mock_memory) -> None:
        handler, _ = _make_handler_mixin(mock_memory)
        mock_memory.search_memory_text.return_value = [
            {"content": "legacy result", "source_file": "log.jsonl", "score": 0.5, "search_method": "bm25"}
        ]

        result = handler._handle_search_memory({"query": "test", "scope": "activity_log"})
        mock_memory.search_memory_text.assert_called_once()

    def test_fallback_to_legacy_on_neo4j_failure(self, mock_memory) -> None:
        handler, mock_backend = _make_handler_mixin(mock_memory)
        mock_backend.retrieve = AsyncMock(side_effect=RuntimeError("crash"))
        mock_memory.search_memory_text.return_value = [
            {"content": "fallback", "source_file": "kb.md", "score": 0.5, "search_method": "vector"}
        ]

        result = handler._handle_search_memory({"query": "test", "scope": "knowledge"})
        mock_memory.search_memory_text.assert_called_once()

    def test_legacy_backend_never_routes_to_neo4j(self, mock_memory) -> None:
        handler, _ = _make_handler_mixin(mock_memory, "LegacyRAGBackend")
        mock_memory.search_memory_text.return_value = []

        handler._handle_search_memory({"query": "test", "scope": "all"})
        mock_memory.search_memory_text.assert_called_once()
