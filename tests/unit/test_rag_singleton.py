"""Unit tests for core/memory/rag/singleton.py — RAG component singletons."""
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import sys
import threading
import time
import types
from unittest.mock import MagicMock, patch

import pytest

# ── Helpers ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_singletons(monkeypatch):
    """Reset singletons before and after each test for isolation.

    Also clears ANIMAWORKS_VECTOR_URL / ANIMAWORKS_EMBED_URL so that
    tests always exercise the local (ChromaVectorStore / SentenceTransformer)
    code-paths regardless of the host environment.
    """
    monkeypatch.delenv("ANIMAWORKS_VECTOR_URL", raising=False)
    monkeypatch.delenv("ANIMAWORKS_EMBED_URL", raising=False)

    from core.memory.rag.singleton import _reset_for_testing

    _reset_for_testing()
    yield
    _reset_for_testing()


@pytest.fixture
def mock_sentence_transformers():
    """Inject a mock sentence_transformers module into sys.modules.

    This allows patching SentenceTransformer even when the real
    sentence_transformers package is not installed.
    """
    mock_cls = MagicMock()
    mock_module = types.ModuleType("sentence_transformers")
    mock_module.SentenceTransformer = mock_cls  # type: ignore[attr-defined]

    already_present = "sentence_transformers" in sys.modules
    original = sys.modules.get("sentence_transformers")
    sys.modules["sentence_transformers"] = mock_module
    yield mock_cls
    if already_present:
        sys.modules["sentence_transformers"] = original  # type: ignore[assignment]
    else:
        sys.modules.pop("sentence_transformers", None)


# ── get_vector_store ──────────────────────────────────────────────


class TestGetVectorStore:
    def test_returns_same_instance(self):
        """get_vector_store() should return the same instance on repeated calls."""
        mock_store = MagicMock()
        with patch(
            "core.memory.rag.store.ChromaVectorStore",
            return_value=mock_store,
        ):
            from core.memory.rag.singleton import get_vector_store

            store1 = get_vector_store()
            store2 = get_vector_store()

        assert store1 is store2
        assert store1 is mock_store

    def test_creates_only_once(self):
        """ChromaVectorStore constructor should be called exactly once."""
        mock_cls = MagicMock()
        with patch(
            "core.memory.rag.store.ChromaVectorStore",
            mock_cls,
        ):
            from core.memory.rag.singleton import get_vector_store

            get_vector_store()
            get_vector_store()
            get_vector_store()

        mock_cls.assert_called_once()

    def test_per_anima_init_failure_persists_repair_signal(self, data_dir):
        """A per-anima latch must remain observable outside the worker process."""
        anima_state = data_dir / "animas" / "sora" / "state"
        anima_state.mkdir(parents=True)

        from core.memory.rag.repair import _reset_for_testing as reset_repair
        from core.memory.rag.singleton import (
            get_vector_store,
            list_vector_store_init_failed_animas,
        )

        reset_repair()
        with patch(
            "core.memory.rag.store.create_chroma_vector_store",
            side_effect=RuntimeError("no such table: tenants"),
        ):
            assert get_vector_store("sora") is None

        state = json.loads((anima_state / "rag_repair.json").read_text(encoding="utf-8"))
        assert state["status"] == "requested"
        assert state["reason"] == "store_init_failed"
        assert state["recent_signals"][-1]["reason"] == "store_init_failed"
        assert list_vector_store_init_failed_animas() == ["sora"]


# ── get_embedding_model ──────────────────────────────────────────


class TestGetEmbeddingModel:
    def test_returns_same_instance(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """get_embedding_model() should return the same instance on repeated calls."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        from core.memory.rag.singleton import get_embedding_model

        model1 = get_embedding_model()
        model2 = get_embedding_model()

        assert model1 is model2
        assert model1 is mock_model

    def test_creates_only_once(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """SentenceTransformer constructor should be called exactly once."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        from core.memory.rag.singleton import get_embedding_model

        get_embedding_model()
        get_embedding_model()
        get_embedding_model()

        mock_sentence_transformers.assert_called_once()

    def test_device_flap_does_not_reload(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """A flapping resolve_device() must not discard and reload the model.

        Regression test for the 2026-07-17 OOM incident: repeated
        cuda<->cpu probe flips reloaded the SentenceTransformer on every
        call, ratcheting RSS up by ~0.5GB per reload.
        """
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        from core.memory.rag.singleton import get_embedding_model

        with patch("core.gpu.resolve_device", side_effect=["cpu", "cuda", "cpu", "cuda"]):
            model1 = get_embedding_model()
            model2 = get_embedding_model()
            model3 = get_embedding_model()

        assert model1 is model2 is model3
        mock_sentence_transformers.assert_called_once()

    def test_creates_cache_dir(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """get_embedding_model() should create the models cache directory."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        from core.memory.rag.singleton import get_embedding_model

        get_embedding_model()

        assert (tmp_path / "models").is_dir()

    def test_reads_model_from_config(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """get_embedding_model() with no args should read model from config."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        with patch(
            "core.memory.rag.singleton._get_configured_model_name",
            return_value="cl-nagoya/ruri-small",
        ):
            from core.memory.rag.singleton import get_embedding_model

            get_embedding_model()

        mock_sentence_transformers.assert_called_once_with(
            "cl-nagoya/ruri-small",
            cache_folder=str(tmp_path / "models"),
            device="cpu",
        )

    def test_explicit_model_name_overrides_config(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """Explicit model_name parameter should override config value."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        with patch(
            "core.memory.rag.singleton._get_configured_model_name",
            return_value="intfloat/multilingual-e5-small",
        ):
            from core.memory.rag.singleton import get_embedding_model

            get_embedding_model("pkshatech/RoSEtta-base-ja")

        mock_sentence_transformers.assert_called_once_with(
            "pkshatech/RoSEtta-base-ja",
            cache_folder=str(tmp_path / "models"),
            device="cpu",
        )

    def test_model_switch_reloads(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """Requesting a different model name should discard cache and reload."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        model_a = MagicMock(name="model_a")
        model_b = MagicMock(name="model_b")
        mock_sentence_transformers.side_effect = [model_a, model_b]

        from core.memory.rag.singleton import get_embedding_model

        result_a = get_embedding_model("model-a")
        result_b = get_embedding_model("model-b")

        assert result_a is model_a
        assert result_b is model_b
        assert mock_sentence_transformers.call_count == 2

    def test_same_model_does_not_reload(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """Requesting the same model name should return cached instance."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        from core.memory.rag.singleton import get_embedding_model

        m1 = get_embedding_model("model-x")
        m2 = get_embedding_model("model-x")

        assert m1 is m2
        mock_sentence_transformers.assert_called_once()

# ── get_embedding_dimension ──────────────────────────────────────


class TestGetEmbeddingDimension:
    def test_returns_model_dimension(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """get_embedding_dimension() should return model's embedding dimension."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_model.get_sentence_embedding_dimension.return_value = 768
        mock_sentence_transformers.return_value = mock_model

        from core.memory.rag.singleton import get_embedding_dimension

        dim = get_embedding_dimension()
        assert dim == 768
        mock_model.get_sentence_embedding_dimension.assert_called_once()


# ── get_embedding_model_name ─────────────────────────────────────


class TestGetEmbeddingModelName:
    def test_returns_loaded_model_name(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """After loading, get_embedding_model_name() returns the loaded model name."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        from core.memory.rag.singleton import (
            get_embedding_model,
            get_embedding_model_name,
        )

        get_embedding_model("cl-nagoya/ruri-small")
        assert get_embedding_model_name() == "cl-nagoya/ruri-small"

    def test_returns_config_when_not_loaded(self):
        """Before loading, get_embedding_model_name() falls back to config."""
        with patch(
            "core.memory.rag.singleton._get_configured_model_name",
            return_value="custom/model",
        ):
            from core.memory.rag.singleton import get_embedding_model_name

            assert get_embedding_model_name() == "custom/model"


# ── _get_configured_model_name ───────────────────────────────────


class TestGetConfiguredModelName:
    def test_reads_from_config(self, tmp_path, monkeypatch):
        """Should read rag.embedding_model from config.json."""
        import json

        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps({
                "rag": {"embedding_model": "cl-nagoya/ruri-small"},
            }),
            encoding="utf-8",
        )
        # Invalidate config cache
        from core.config import invalidate_cache
        invalidate_cache()

        from core.memory.rag.singleton import _get_configured_model_name

        result = _get_configured_model_name()
        assert result == "cl-nagoya/ruri-small"

    def test_fallback_on_missing_config(self, tmp_path, monkeypatch):
        """Should fall back to default when config is unavailable."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        # No config.json exists → load_config returns defaults
        from core.config import invalidate_cache
        invalidate_cache()

        from core.memory.rag.singleton import _get_configured_model_name

        result = _get_configured_model_name()
        assert result == "intfloat/multilingual-e5-small"


# ── _reset_for_testing ───────────────────────────────────────────


class TestResetForTesting:
    def test_reset_clears_singletons(self, tmp_path, monkeypatch):
        """_reset_for_testing() should allow re-creation of singletons."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_store_1 = MagicMock()
        mock_store_2 = MagicMock()

        from core.memory.rag.singleton import (
            _reset_for_testing,
            get_vector_store,
        )

        with patch(
            "core.memory.rag.store.ChromaVectorStore",
            return_value=mock_store_1,
        ):
            store1 = get_vector_store()

        _reset_for_testing()

        with patch(
            "core.memory.rag.store.ChromaVectorStore",
            return_value=mock_store_2,
        ):
            store2 = get_vector_store()

        assert store1 is not store2
        assert store1 is mock_store_1
        assert store2 is mock_store_2

    def test_reset_clears_model_name(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """_reset_for_testing() should clear _embedding_model_name."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        import core.memory.rag.singleton as singleton_mod
        from core.memory.rag.singleton import (
            _reset_for_testing,
            get_embedding_model,
        )

        get_embedding_model("test-model")
        assert singleton_mod._embedding_model_name == "test-model"

        _reset_for_testing()
        assert singleton_mod._embedding_model_name is None


# ── Vector-store lifecycle ───────────────────────────────────────


def test_reset_waits_for_in_flight_operation_and_reopens_store(monkeypatch):
    """A reset must not close a handle until its active worker operation ends."""
    from core.memory.rag import singleton, vector_worker

    monkeypatch.setenv("ANIMAWORKS_ALLOW_DIRECT_CHROMA", "1")
    singleton._reset_for_testing()

    operation_started = threading.Event()
    release_operation = threading.Event()
    store_closed = threading.Event()
    call_order: list[str] = []

    class BlockingStore:
        def close(self) -> None:
            call_order.append("close")
            store_closed.set()

    old_store = BlockingStore()
    singleton._vector_stores["sora"] = old_store

    def action(store):
        assert store is old_store
        operation_started.set()
        assert release_operation.wait(timeout=2)
        call_order.append("operation-finished")
        return "first-result"

    result: list[object] = []
    operation_thread = threading.Thread(
        target=lambda: result.append(vector_worker._call_vector_store("sora", action)),
    )
    operation_thread.start()
    assert operation_started.wait(timeout=2)

    reset_thread = threading.Thread(target=lambda: singleton.reset_vector_store("sora"))
    reset_thread.start()
    assert not store_closed.wait(timeout=0.1)

    release_operation.set()
    operation_thread.join(timeout=2)
    reset_thread.join(timeout=2)

    assert not operation_thread.is_alive()
    assert not reset_thread.is_alive()
    assert result == ["first-result"]
    assert store_closed.is_set()
    assert call_order == ["operation-finished", "close"]

    reopened_store = MagicMock()
    with patch("core.memory.rag.store.ChromaVectorStore", return_value=reopened_store):
        assert vector_worker._call_vector_store("sora", lambda store: store) is reopened_store


def test_in_flight_self_heal_can_upgrade_to_reset_without_deadlock(monkeypatch):
    """An operation-triggered reset upgrades its own shared gate immediately."""
    from core.memory.rag import singleton, vector_worker

    monkeypatch.setenv("ANIMAWORKS_ALLOW_DIRECT_CHROMA", "1")
    singleton._reset_for_testing()
    store = MagicMock()
    singleton._vector_stores["sora"] = store

    def reset_during_action(active_store):
        assert active_store is store
        singleton.reset_vector_store("sora")
        return "recovered"

    started = time.monotonic()
    result = vector_worker._call_vector_store("sora", reset_during_action)

    assert result == "recovered"
    assert time.monotonic() - started < 1.0
    store.close.assert_called_once()


def test_timed_out_close_waits_for_reader_drain_and_blocks_new_operations(monkeypatch):
    """A timed-out reset condemns the old handle without closing active readers."""
    from core.memory.rag import singleton, vector_worker

    monkeypatch.setenv("ANIMAWORKS_ALLOW_DIRECT_CHROMA", "1")
    monkeypatch.setattr(singleton, "_VECTOR_STORE_CLOSE_TIMEOUT_SECONDS", 0.05)
    singleton._reset_for_testing()

    operation_started = threading.Event()
    release_operation = threading.Event()
    close_started = threading.Event()
    release_close = threading.Event()
    late_operation_started = threading.Event()

    class BlockingCloseStore:
        def close(self) -> None:
            close_started.set()
            assert release_close.wait(timeout=2)

    old_store = BlockingCloseStore()
    singleton._vector_stores["sora"] = old_store

    active = threading.Thread(
        target=lambda: vector_worker._call_vector_store(
            "sora",
            lambda _store: (
                operation_started.set(),
                release_operation.wait(timeout=2),
            ),
        ),
    )
    active.start()
    assert operation_started.wait(timeout=2)

    reset = threading.Thread(target=lambda: singleton.reset_vector_store("sora"))
    reset.start()
    time.sleep(0.1)
    assert reset.is_alive()
    assert not close_started.is_set()

    reopened_store = MagicMock()
    with patch("core.memory.rag.store.ChromaVectorStore", return_value=reopened_store):
        late = threading.Thread(
            target=lambda: vector_worker._call_vector_store(
                "sora",
                lambda _store: late_operation_started.set(),
            ),
        )
        late.start()
        assert not late_operation_started.wait(timeout=0.1)

        release_operation.set()
        assert close_started.wait(timeout=2)
        assert not late_operation_started.is_set()
        release_close.set()
        assert late_operation_started.wait(timeout=2)
        reset.join(timeout=2)
        late.join(timeout=2)

    active.join(timeout=2)

    assert not reset.is_alive()
    assert not late.is_alive()
    assert not active.is_alive()


# ── Thread safety ────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_get_vector_store(self):
        """Multiple threads calling get_vector_store() concurrently
        should all receive the same instance."""
        mock_store = MagicMock()
        results: list[object] = []
        errors: list[Exception] = []

        with patch(
            "core.memory.rag.store.ChromaVectorStore",
            return_value=mock_store,
        ):
            from core.memory.rag.singleton import get_vector_store

            def worker():
                try:
                    store = get_vector_store()
                    results.append(store)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=5)

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 10
        assert all(r is mock_store for r in results)

    def test_concurrent_get_embedding_model(
        self, tmp_path, monkeypatch, mock_sentence_transformers
    ):
        """Multiple threads calling get_embedding_model() concurrently
        should all receive the same instance."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        results: list[object] = []
        errors: list[Exception] = []

        from core.memory.rag.singleton import get_embedding_model

        def worker():
            try:
                model = get_embedding_model()
                results.append(model)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert not errors, f"Thread errors: {errors}"
        assert len(results) == 10
        assert all(r is mock_model for r in results)


# ── MemoryIndexer integration ────────────────────────────────────


class TestMemoryIndexerEmbeddingInjection:
    def test_accepts_external_embedding_model(self, tmp_path):
        """MemoryIndexer should accept an externally provided embedding_model."""
        mock_store = MagicMock()
        mock_model = MagicMock()

        anima_dir = tmp_path / "test-anima"
        anima_dir.mkdir(parents=True)

        from core.memory.rag.indexer import MemoryIndexer

        indexer = MemoryIndexer(
            vector_store=mock_store,
            anima_name="test-anima",
            anima_dir=anima_dir,
            embedding_model=mock_model,
        )

        assert indexer.embedding_model is mock_model

    def test_skips_init_when_model_provided(self, tmp_path):
        """When embedding_model is provided, _init_embedding_model() should not be called."""
        mock_store = MagicMock()
        mock_model = MagicMock()

        anima_dir = tmp_path / "test-anima"
        anima_dir.mkdir(parents=True)

        with patch(
            "core.memory.rag.indexer.MemoryIndexer._init_embedding_model"
        ) as mock_init:
            from core.memory.rag.indexer import MemoryIndexer

            MemoryIndexer(
                vector_store=mock_store,
                anima_name="test-anima",
                anima_dir=anima_dir,
                embedding_model=mock_model,
            )

            mock_init.assert_not_called()

    def test_calls_singleton_when_no_model_provided(self, tmp_path, monkeypatch):
        """When no embedding_model is provided, _init_embedding_model() should
        use the singleton get_embedding_model()."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_store = MagicMock()
        mock_model = MagicMock()

        anima_dir = tmp_path / "test-anima"
        anima_dir.mkdir(parents=True)

        with patch(
            "core.memory.rag.singleton.get_embedding_model",
            return_value=mock_model,
        ) as mock_get:
            from core.memory.rag.indexer import MemoryIndexer

            indexer = MemoryIndexer(
                vector_store=mock_store,
                anima_name="test-anima",
                anima_dir=anima_dir,
            )

            mock_get.assert_called_once()
            assert indexer.embedding_model is mock_model

    def test_embedding_model_name_default_is_none(self, tmp_path):
        """MemoryIndexer with no embedding_model_name should pass None to singleton."""
        mock_store = MagicMock()
        mock_model = MagicMock()

        anima_dir = tmp_path / "test-anima"
        anima_dir.mkdir(parents=True)

        with patch(
            "core.memory.rag.singleton.get_embedding_model",
            return_value=mock_model,
        ) as mock_get:
            from core.memory.rag.indexer import MemoryIndexer

            MemoryIndexer(
                vector_store=mock_store,
                anima_name="test-anima",
                anima_dir=anima_dir,
            )

            # Should be called with None (config-resolved)
            mock_get.assert_called_once_with(None)
