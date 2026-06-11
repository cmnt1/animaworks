from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.memory.rag.singleton import generate_embeddings, thread_safe_encode


def _rag_config(*, enabled: bool) -> SimpleNamespace:
    return SimpleNamespace(
        rag=SimpleNamespace(
            embedding_e5_prefix_enabled=enabled,
            embedding_query_prefix="query: ",
            embedding_document_prefix="passage: ",
        )
    )


def test_thread_safe_encode_applies_configured_e5_prefixes() -> None:
    model = MagicMock()
    model.encode.side_effect = [[[1.0]], [[2.0]]]

    with (
        patch("core.memory.rag.singleton.get_embedding_model", return_value=model),
        patch("core.config.load_config", return_value=_rag_config(enabled=True)),
    ):
        assert thread_safe_encode(["hello"], purpose="query") == [[1.0]]
        assert thread_safe_encode(["hello"], purpose="document") == [[2.0]]

    assert model.encode.call_args_list[0].args[0] == ["query: hello"]
    assert model.encode.call_args_list[1].args[0] == ["passage: hello"]


def test_thread_safe_encode_preserves_legacy_no_prefix_default() -> None:
    model = MagicMock()
    model.encode.return_value = [[1.0]]

    with (
        patch("core.memory.rag.singleton.get_embedding_model", return_value=model),
        patch("core.config.load_config", return_value=_rag_config(enabled=False)),
    ):
        assert thread_safe_encode(["hello"], purpose="query") == [[1.0]]

    assert model.encode.call_args.args[0] == ["hello"]


def test_generate_embeddings_http_sends_embedding_purpose(monkeypatch) -> None:
    monkeypatch.setenv("ANIMAWORKS_EMBED_URL", "http://127.0.0.1:18500/api/internal/embed")
    response = MagicMock()
    response.json.return_value = {"embeddings": [[1.0]]}

    with patch("httpx.post", return_value=response) as post:
        assert generate_embeddings(["hello"], purpose="query") == [[1.0]]

    response.raise_for_status.assert_called_once()
    assert post.call_args.kwargs["json"] == {"texts": ["hello"], "purpose": "query"}
