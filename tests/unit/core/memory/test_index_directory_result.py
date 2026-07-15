from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from core.memory.rag.indexer import MemoryIndexer, _IndexFileOutcome


def test_index_directory_returns_structured_counts_and_summary(tmp_path: Path, caplog) -> None:
    for name in ("indexed.md", "failed.md", "unchanged.md", "skipped.md"):
        (tmp_path / name).write_text(f"# {name}", encoding="utf-8")

    indexer = object.__new__(MemoryIndexer)
    indexer.collection_prefix = "sora"
    outcomes = {
        "indexed.md": _IndexFileOutcome("indexed"),
        "failed.md": _IndexFileOutcome("failed", transient=True),
        "unchanged.md": _IndexFileOutcome("unchanged"),
        "skipped.md": _IndexFileOutcome("skipped"),
    }

    def index_file(file_path: Path, _memory_type: str, force: bool = False) -> int:
        del force
        indexer._last_index_file_outcome = outcomes[file_path.name]
        return 4 if file_path.name == "indexed.md" else 0

    indexer.index_file = index_file  # type: ignore[method-assign]

    with caplog.at_level(logging.INFO, logger="animaworks.rag.indexer"):
        result = indexer.index_directory(tmp_path, "knowledge")

    assert result.chunks_indexed == 4
    assert result.files_indexed == 1
    assert result.files_failed == 1
    assert result.files_unchanged == 1
    assert result.files_skipped == 1
    assert result.transient_failures == 1
    assert result.transient is True
    assert result.failed_sources == ("failed.md",)
    assert any(
        "collection=sora_knowledge" in record.getMessage()
        and "failed_sources=['failed.md']" in record.getMessage()
        and "transient=True" in record.getMessage()
        for record in caplog.records
    )


def test_transient_upsert_failure_is_debug_only(tmp_path: Path, caplog) -> None:
    from core.memory.rag.indexer_delete import upsert_file_documents

    store = SimpleNamespace(
        create_collection=lambda _name: True,
        get_by_metadata=lambda *_args, **_kwargs: [],
        upsert=lambda *_args, **_kwargs: False,
        is_transient_write_failure=lambda _name: True,
    )
    indexer = SimpleNamespace(
        vector_store=store,
        _record_upsert_failure=lambda *_args: None,
    )

    with caplog.at_level(logging.DEBUG, logger="animaworks.rag.indexer"):
        assert upsert_file_documents(indexer, "sora_knowledge", "knowledge/a.md", tmp_path / "a.md", []) is False

    matching = [record for record in caplog.records if "Upsert failed" in record.getMessage()]
    assert len(matching) == 1
    assert matching[0].levelno == logging.DEBUG
