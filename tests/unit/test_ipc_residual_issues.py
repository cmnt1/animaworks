"""Tests for IPC streaming residual issues — setting_sources and vector clients.

Problem A: ClaudeAgentOptions.setting_sources=[] disables CLI hook loading
Problem B: get_vector_store(anima_name) selects per-anima remote clients
"""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Problem A: setting_sources=[] ──────────────────────────────────


class TestSettingSourcesDisabled:
    """Verify ClaudeAgentOptions receives setting_sources=[] to block CLI hooks."""

    def test_execute_passes_empty_setting_sources(self):
        """_build_sdk_options() should include setting_sources=[] for ClaudeAgentOptions."""
        import inspect

        from core.execution.engines.claude.agent_sdk import AgentSDKExecutor

        # Options construction is extracted to _build_sdk_options()
        source = inspect.getsource(AgentSDKExecutor._build_sdk_options)
        assert "setting_sources=[]" in source, "_build_sdk_options() must pass setting_sources=[] to ClaudeAgentOptions"

    def test_execute_streaming_passes_empty_setting_sources(self):
        """execute_streaming() uses _build_sdk_options which includes setting_sources=[]."""
        import inspect

        from core.execution.engines.claude.agent_sdk import AgentSDKExecutor

        # Verify execute() and execute_streaming() both call _build_sdk_options
        exec_source = inspect.getsource(AgentSDKExecutor.execute)
        stream_source = inspect.getsource(AgentSDKExecutor.execute_streaming)
        assert "_build_sdk_options" in exec_source, "execute() must call _build_sdk_options()"
        assert "_build_sdk_options" in stream_source, "execute_streaming() must call _build_sdk_options()"


# ── Problem B: Per-anima vector-client isolation ───────────────────


@pytest.fixture(autouse=True)
def _reset_vector_stores():
    """Reset singleton stores before and after each test."""
    from core.memory.rag.singleton import _reset_for_testing

    _reset_for_testing()
    yield
    _reset_for_testing()


class TestGetAnimaVectordbDir:
    """Verify get_anima_vectordb_dir returns correct path."""

    def test_returns_correct_path(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        from core.paths import get_anima_vectordb_dir

        result = get_anima_vectordb_dir("yuki")
        assert result == tmp_path / "animas" / "yuki" / "vectordb"

    def test_different_animas_different_dirs(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        from core.paths import get_anima_vectordb_dir

        d1 = get_anima_vectordb_dir("yuki")
        d2 = get_anima_vectordb_dir("sakura")
        assert d1 != d2
        assert "yuki" in str(d1)
        assert "sakura" in str(d2)


class TestPerAnimaVectorStore:
    """Verify cached vector clients use configured remote owner access."""

    def test_different_animas_get_different_clients(self):
        from core.memory.rag.endpoints import RagEndpoints, configure_endpoints
        from core.memory.rag.http_store import HttpVectorStore
        from core.memory.rag.vector_registry import get_vector_store

        configure_endpoints(RagEndpoints(vector_url="http://localhost:18500/vector"))
        a = get_vector_store("anima_a")
        b = get_vector_store("anima_b")

        assert isinstance(a, HttpVectorStore)
        assert isinstance(b, HttpVectorStore)
        assert a is not b
        assert a._anima_name == "anima_a"
        assert b._anima_name == "anima_b"

    def test_same_anima_returns_same_client(self):
        from core.memory.rag.endpoints import RagEndpoints, configure_endpoints
        from core.memory.rag.vector_registry import get_vector_store

        configure_endpoints(RagEndpoints(vector_url="http://localhost:18500/vector"))
        first = get_vector_store("yuki")
        second = get_vector_store("yuki")

        assert first is second

    def test_missing_endpoint_does_not_open_native_store(self):
        from core.memory.rag.endpoints import RagEndpoints, configure_endpoints
        from core.memory.rag.vector_registry import get_vector_store

        configure_endpoints(RagEndpoints())
        with patch("core.memory.rag.store.create_chroma_vector_store") as create_store:
            assert get_vector_store("yuki") is None
        create_store.assert_not_called()

    def test_none_or_empty_anima_returns_none(self):
        from core.memory.rag.endpoints import RagEndpoints, configure_endpoints
        from core.memory.rag.vector_registry import get_vector_store

        configure_endpoints(RagEndpoints(vector_url="http://localhost:18500/vector"))

        assert get_vector_store(None) is None
        assert get_vector_store("") is None

    def test_reset_clears_all_clients(self):
        from core.memory.rag.endpoints import RagEndpoints, configure_endpoints
        from core.memory.rag.singleton import _reset_for_testing
        from core.memory.rag.vector_registry import get_vector_store

        configure_endpoints(RagEndpoints(vector_url="http://localhost:18500/vector"))
        first = get_vector_store("a")
        get_vector_store("b")
        _reset_for_testing()
        configure_endpoints(RagEndpoints(vector_url="http://localhost:18500/vector"))
        recreated = get_vector_store("a")

        assert first is not recreated

    def test_thread_safety_per_anima(self):
        from core.memory.rag.endpoints import RagEndpoints, configure_endpoints
        from core.memory.rag.http_store import HttpVectorStore
        from core.memory.rag.vector_registry import get_vector_store

        configure_endpoints(RagEndpoints(vector_url="http://localhost:18500/vector"))
        results = []
        errors = []

        def worker():
            try:
                results.append(get_vector_store("thread_test"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        assert not errors
        assert len(results) == 10
        assert isinstance(results[0], HttpVectorStore)
        assert all(store is results[0] for store in results)


class TestCallersSendAnimaName:
    """Verify all production callers pass anima_name to get_vector_store."""

    def test_forgetting_passes_anima_name(self):
        """ForgettingEngine._get_vector_store passes self.anima_name."""
        from core.memory.maintenance.forgetting import ForgettingEngine

        engine = ForgettingEngine.__new__(ForgettingEngine)
        engine.anima_name = "yuki"

        with patch("core.memory.rag.vector_registry.get_vector_store") as mock_gvs:
            mock_gvs.return_value = MagicMock()
            engine._get_vector_store()
            mock_gvs.assert_called_once_with("yuki")

    def test_consolidation_passes_anima_name(self, tmp_path: Path):
        """ConsolidationEngine uses get_vector_store(self.anima_name) when no rag_store."""
        anima_dir = tmp_path / "animas" / "sakura"
        (anima_dir / "knowledge").mkdir(parents=True)
        (anima_dir / "knowledge" / "test.md").write_text("test", encoding="utf-8")

        from core.memory.maintenance.consolidation import ConsolidationEngine

        engine = ConsolidationEngine(anima_dir, "sakura")

        with (
            patch("core.memory.rag.MemoryIndexer") as MockIndexer,
            patch("core.memory.rag.vector_registry.get_vector_store") as mock_gvs,
        ):
            mock_gvs.return_value = MagicMock()
            MockIndexer.return_value = MagicMock()
            engine._update_rag_index(["test.md"])
            mock_gvs.assert_called_once_with("sakura")

    def test_priming_passes_anima_name(self):
        """PrimingEngine uses get_vector_store(anima_name) via RetrieverCache."""
        import inspect

        from core.memory.priming.utils import RetrieverCache

        # get_or_create only takes the lock; the store lookup moved into
        # _get_or_create_locked.
        source = inspect.getsource(RetrieverCache._get_or_create_locked)
        assert "get_vector_store(anima_name)" in source

    def test_distillation_passes_anima_name(self):
        """ProceduralDistiller uses get_vector_store(self.anima_name)."""
        import inspect

        from core.memory.maintenance.distillation import ProceduralDistiller

        source = inspect.getsource(ProceduralDistiller._check_rag_duplicate)
        assert "get_vector_store(self.anima_name)" in source
