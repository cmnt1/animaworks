from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from core.memory.rag.store import ChromaVectorStore, Document


@pytest.mark.parametrize(
    ("public_method", "once_method", "args", "expected"),
    [
        ("create_collection", "_create_collection_once", ("sakura_knowledge",), False),
        ("delete_collection", "_delete_collection_once", ("sakura_knowledge",), False),
        ("list_collections", "_list_collections_once", (), None),
        ("upsert", "_upsert_once", ("sakura_knowledge", [Document("id", "text")]), False),
        ("query", "_query_once", ("sakura_knowledge", [0.1]), []),
        ("delete_documents", "_delete_documents_once", ("sakura_knowledge", ["id"]), False),
        ("update_metadata", "_update_metadata_once", ("sakura_knowledge", ["id"], [{}]), False),
        ("get_by_metadata", "_get_by_metadata_once", ("sakura_knowledge", {}, 20), []),
        ("get_all", "_get_all_once", ("sakura_knowledge", 100_000), []),
        ("count", "_count_once", ("sakura_knowledge",), None),
        ("get_by_ids", "_get_by_ids_once", ("sakura_knowledge", ["id"]), []),
    ],
)
def test_public_method_reports_chroma_failure(
    tmp_path: Path,
    public_method: str,
    once_method: str,
    args: tuple,
    expected,
) -> None:
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    store.persist_dir = tmp_path
    store.anima_name = "sakura"
    report_error = MagicMock()
    setattr(store, once_method, MagicMock(side_effect=RuntimeError("database disk image is malformed")))
    store._report_chroma_error = report_error

    result = getattr(store, public_method)(*args)

    assert result == expected
    report_error.assert_called_once_with(
        args[0] if args else "<list_collections>", report_error.call_args.args[1], public_method
    )


def test_get_all_does_not_pass_an_empty_where_filter() -> None:
    store = ChromaVectorStore.__new__(ChromaVectorStore)
    collection = MagicMock()
    collection.get.return_value = {
        "ids": ["doc-1"],
        "documents": ["body"],
        "metadatas": [{"kind": "knowledge"}],
    }
    store.client = MagicMock()
    store.client.get_collection.return_value = collection

    results = store._get_all_once("sakura_knowledge", 100_000)

    assert [result.document.id for result in results] == ["doc-1"]
    collection.get.assert_called_once_with(limit=100_000, include=["documents", "metadatas"])
