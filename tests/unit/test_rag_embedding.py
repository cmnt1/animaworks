"""Unit tests for the split embedding model registry."""

from __future__ import annotations

import json
import sys
import threading
import types
from unittest.mock import MagicMock, patch

import pytest


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


class TestGetEmbeddingModel:
    def test_returns_same_instance(self, tmp_path, monkeypatch, mock_sentence_transformers):
        """get_embedding_model() should return the same instance on repeated calls."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        from core.memory.rag.embedding import get_embedding_model

        model1 = get_embedding_model()
        model2 = get_embedding_model()

        assert model1 is model2
        assert model1 is mock_model

    def test_creates_only_once(self, tmp_path, monkeypatch, mock_sentence_transformers):
        """SentenceTransformer constructor should be called exactly once."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        from core.memory.rag.embedding import get_embedding_model

        get_embedding_model()
        get_embedding_model()
        get_embedding_model()

        mock_sentence_transformers.assert_called_once()

    def test_device_flap_does_not_reload(self, tmp_path, monkeypatch, mock_sentence_transformers):
        """A flapping resolve_device() must not discard and reload the model.

        Regression test for the 2026-07-17 OOM incident: repeated
        cuda<->cpu probe flips reloaded the SentenceTransformer on every
        call, ratcheting RSS up by ~0.5GB per reload.
        """
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        from core.memory.rag.embedding import get_embedding_model

        with patch("core.infra.gpu.resolve_device", side_effect=["cpu", "cuda", "cpu", "cuda"]):
            model1 = get_embedding_model()
            model2 = get_embedding_model()
            model3 = get_embedding_model()

        assert model1 is model2 is model3
        mock_sentence_transformers.assert_called_once()

    def test_creates_cache_dir(self, tmp_path, monkeypatch, mock_sentence_transformers):
        """get_embedding_model() should create the models cache directory."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        from core.memory.rag.embedding import get_embedding_model

        get_embedding_model()

        assert (tmp_path / "models").is_dir()

    def test_reads_model_from_config(self, tmp_path, monkeypatch, mock_sentence_transformers):
        """get_embedding_model() with no args should read model from config."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        with patch(
            "core.memory.rag.embedding._get_configured_model_name",
            return_value="cl-nagoya/ruri-small",
        ):
            from core.memory.rag.embedding import get_embedding_model

            get_embedding_model()

        mock_sentence_transformers.assert_called_once_with(
            "cl-nagoya/ruri-small",
            cache_folder=str(tmp_path / "models"),
            device="cpu",
        )

    def test_explicit_model_name_overrides_config(self, tmp_path, monkeypatch, mock_sentence_transformers):
        """Explicit model_name parameter should override config value."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        with patch(
            "core.memory.rag.embedding._get_configured_model_name",
            return_value="intfloat/multilingual-e5-small",
        ):
            from core.memory.rag.embedding import get_embedding_model

            get_embedding_model("pkshatech/RoSEtta-base-ja")

        mock_sentence_transformers.assert_called_once_with(
            "pkshatech/RoSEtta-base-ja",
            cache_folder=str(tmp_path / "models"),
            device="cpu",
        )

    def test_model_switch_reloads(self, tmp_path, monkeypatch, mock_sentence_transformers):
        """Requesting a different model name should discard cache and reload."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        model_a = MagicMock(name="model_a")
        model_b = MagicMock(name="model_b")
        mock_sentence_transformers.side_effect = [model_a, model_b]

        from core.memory.rag.embedding import get_embedding_model

        result_a = get_embedding_model("model-a")
        result_b = get_embedding_model("model-b")

        assert result_a is model_a
        assert result_b is model_b
        assert mock_sentence_transformers.call_count == 2

    def test_same_model_does_not_reload(self, tmp_path, monkeypatch, mock_sentence_transformers):
        """Requesting the same model name should return cached instance."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        from core.memory.rag.embedding import get_embedding_model

        m1 = get_embedding_model("model-x")
        m2 = get_embedding_model("model-x")

        assert m1 is m2
        mock_sentence_transformers.assert_called_once()


class TestGetEmbeddingModelName:
    def test_returns_loaded_model_name(self, tmp_path, monkeypatch, mock_sentence_transformers):
        """After loading, get_embedding_model_name() returns the loaded model name."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        from core.memory.rag.embedding import (
            get_embedding_model,
            get_embedding_model_name,
        )

        get_embedding_model("cl-nagoya/ruri-small")
        assert get_embedding_model_name() == "cl-nagoya/ruri-small"

    def test_returns_config_when_not_loaded(self):
        """Before loading, get_embedding_model_name() falls back to config."""
        with patch(
            "core.memory.rag.embedding._get_configured_model_name",
            return_value="custom/model",
        ):
            from core.memory.rag.embedding import get_embedding_model_name

            assert get_embedding_model_name() == "custom/model"


class TestGetConfiguredModelName:
    def test_reads_from_config(self, tmp_path, monkeypatch):
        """Should read rag.embedding_model from config.json."""

        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "rag": {"embedding_model": "cl-nagoya/ruri-small"},
                }
            ),
            encoding="utf-8",
        )
        # Invalidate config cache
        from core.config import invalidate_cache

        invalidate_cache()

        from core.memory.rag.embedding import _get_configured_model_name

        result = _get_configured_model_name()
        assert result == "cl-nagoya/ruri-small"

    def test_fallback_on_missing_config(self, tmp_path, monkeypatch):
        """Should fall back to default when config is unavailable."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))
        # No config.json exists → load_config returns defaults
        from core.config import invalidate_cache

        invalidate_cache()

        from core.memory.rag.embedding import _get_configured_model_name

        result = _get_configured_model_name()
        assert result == "intfloat/multilingual-e5-small"


class TestResetForTesting:
    def test_reset_clears_model_name(self, tmp_path, monkeypatch, mock_sentence_transformers):
        """_reset_for_testing() should clear _embedding_model_name."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        import core.memory.rag.embedding as singleton_mod
        from core.memory.rag.embedding import get_embedding_model
        from core.memory.rag.singleton import _reset_for_testing

        get_embedding_model("test-model")
        assert singleton_mod._embedding_model_name == "test-model"

        _reset_for_testing()
        assert singleton_mod._embedding_model_name is None


class TestThreadSafety:
    def test_concurrent_get_embedding_model(self, tmp_path, monkeypatch, mock_sentence_transformers):
        """Multiple threads calling get_embedding_model() concurrently
        should all receive the same instance."""
        monkeypatch.setenv("ANIMAWORKS_DATA_DIR", str(tmp_path))

        mock_model = MagicMock()
        mock_sentence_transformers.return_value = mock_model

        results: list[object] = []
        errors: list[Exception] = []

        from core.memory.rag.embedding import get_embedding_model

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
