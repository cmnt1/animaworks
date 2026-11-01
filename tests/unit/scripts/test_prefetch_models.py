from __future__ import annotations

import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def test_prefetch_uses_runtime_models_and_configured_cache(tmp_path, monkeypatch):
    from core.memory.retrieval.reranker import _DEFAULT_MODEL

    embedding = Mock()
    reranker = Mock()
    monkeypatch.setitem(
        sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=embedding, CrossEncoder=reranker)
    )
    monkeypatch.setattr(
        "core.config.load_config", lambda: SimpleNamespace(rag=SimpleNamespace(embedding_model="test/embedding"))
    )
    monkeypatch.setenv("ANIMAWORKS_MODEL_CACHE_DIR", str(tmp_path))

    script = Path(__file__).resolve().parents[3] / "scripts" / "ci" / "prefetch_models.py"
    runpy.run_path(str(script), run_name="__main__")

    embedding.assert_called_once_with("test/embedding", device="cpu", cache_folder=str(tmp_path))
    reranker.assert_called_once_with(_DEFAULT_MODEL, device="cpu")
