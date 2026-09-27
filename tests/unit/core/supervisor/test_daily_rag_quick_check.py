from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.supervisor._mgr_scheduler import SchedulerMixin


class _DailyIndexingHarness(SchedulerMixin):
    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self.send_request = MagicMock()

    def _get_data_dir(self) -> Path:
        return self._data_dir

    def _iter_consolidation_targets(self):
        yield "sora", self._data_dir / "animas" / "sora"

    async def _broadcast_event(self, *_args, **_kwargs) -> None:
        return None


@pytest.mark.asyncio
async def test_daily_indexing_uses_configured_vector_store(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    anima_dir = data_dir / "animas" / "sora"
    (anima_dir / "knowledge").mkdir(parents=True)
    (data_dir / "shared" / "common_knowledge").mkdir(parents=True)
    store = MagicMock()
    indexers = []

    class FakeIndexer:
        def __init__(self, vector_store, *_args, **_kwargs):
            self.vector_store = vector_store
            indexers.append(self)

        def index_directory(self, *_args, **_kwargs):
            return SimpleNamespace(chunks_indexed=0, files_failed=0)

    get_store = MagicMock(return_value=store)
    monkeypatch.setattr("core.memory.rag.MemoryIndexer", FakeIndexer)
    monkeypatch.setattr("core.memory.rag.singleton.get_embedding_model_name", lambda: "model")
    monkeypatch.setattr("core.memory.rag.repair.is_repair_locked", lambda _anima_name: False)
    monkeypatch.setattr(
        "core.memory.retrieval.bm25.rebuild_longterm_bm25_index", lambda _path: SimpleNamespace(documents=0)
    )
    monkeypatch.setattr("core.memory.facts.entity_index.rebuild_entity_collection", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("core.memory.rag.graph.rebuild_graph_cache", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("core.memory.rag.singleton.get_vector_store", get_store)

    harness = _DailyIndexingHarness(data_dir)
    await harness._run_daily_indexing()

    get_store.assert_called_once_with("sora")
    assert indexers
    assert all(indexer.vector_store is store for indexer in indexers)
